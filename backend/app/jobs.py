"""
The refresh job: Alpha Vantage -> CSV store, plus its schedule and status.

It is the heart of the background processing pipeline. It manages
few tasks:
- fetching raw financial earnings data from Alpha Vantage,
- parsing and generating calendar events for tracked companies,
- enforcing rate limiting and thread safety, and
- orchestrating APScheduler cron jobs.
"""


from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Callable

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from .config import Settings
from .core import EarningsEvent, GeneratorError, fetch_alpha_vantage_csv, generate_events
from .store import ReportStore

logger = logging.getLogger(__name__)

Fetcher = Callable[[str, str], str]

# Raised when an operation attempts to start a job while one is already running.
class RefreshInProgress(Exception):
    pass

# Raised when manual triggers are fired faster than refresh_cooldown_seconds.
# Carries retry_after so the HTTP layer can emit 429 Too Many Requests
# with a Retry-After header.
class RefreshCooldown(Exception):
    def __init__(self, retry_after: int) -> None:
        super().__init__(f"Refresh is cooling down; retry in {retry_after}s.")
        self.retry_after = retry_after

# In-memory dataclass tracking execution health, timestamps, errors, and
# symbol match statistics (which tracked symbols had upcoming earnings
# vs. which had none).
@dataclass
class JobStatus:
    running: bool = False
    trigger: str | None = None
    last_run_at: datetime | None = None
    last_success_at: datetime | None = None
    last_error: str | None = None
    event_count: int | None = None
    matched_symbols: list[str] = field(default_factory=list)
    missing_symbols: list[str] = field(default_factory=list)

#                     ┌───────────────────────────┐
#                     │ APScheduler (cron/startup)│
#                     └─────────────┬─────────────┘
#                                   │
# ┌──────────────────┐              │
# │  FastAPI Router  │──────────────┼──────────────► [RefreshService]
# │ (manual trigger) │              │                      │
# └──────────────────┘              ▼                      ▼
#                            try_begin() / lock     _refresh() / refilter()
#                                                          │
#                                   ┌──────────────────────┴──────────────────────┐
#                                   ▼                                             ▼
#                         Alpha Vantage Fetcher                           ReportStore & core.py
#                         (network outside lock)                         (event rebuild & CSV store)



class RefreshService:
    def __init__(
        self,
        settings: Settings,
        store: ReportStore,
        fetcher: Fetcher | None = None,
        today: Callable[[], date] = date.today,
    ) -> None:
        self.settings = settings
        self.store = store
        self.fetcher = fetcher or fetch_alpha_vantage_csv
        self.today = today
        self.status = JobStatus()
        # Held for the whole duration of a refresh; acquired non-blocking so a
        # second trigger is rejected (manual) or skipped (cron) instead of queued.
        self._run_lock = threading.Lock()
        self.scheduler: BackgroundScheduler | None = None

    # ----- triggering ------------------------------------------------------

    def try_begin(self, trigger: str, enforce_cooldown: bool) -> None:
        """
        Claim the run slot or raise; call ``run_claimed`` afterwards.
        
        Args:
            trigger: ``cron`` or user-triggered (``manual``).
            enforce_cooldown: when true, skip if less than ``settings.refresh_cooldown_seconds``
                              have passed since last run. Respects only for manual runs
                              to allow back-to-back cron runs.
                              
        Raises:
            RefreshCooldown: if ``enforce_cooldown`` and not enough time has passed.
            RefreshInProgress: if another refresh is already running (for ``manual``).
        """
        if enforce_cooldown and self.status.last_run_at is not None:
            elapsed = datetime.now(timezone.utc) - self.status.last_run_at
            remaining = self.settings.refresh_cooldown_seconds - int(elapsed.total_seconds())
            if remaining > 0:
                raise RefreshCooldown(remaining)
        # Non-blocking lock acquisition (acquire(blocking=False)): Immediately raises 
        # ``RefreshInProgress`` rather than waiting in a queue or creating race conditions.
        if not self._run_lock.acquire(blocking=False):
            raise RefreshInProgress()
        self.status.running = True
        self.status.trigger = trigger
        self.status.last_run_at = datetime.now(timezone.utc)

    def run_claimed(self) -> None:
        """Execute a refresh whose slot was claimed with ``try_begin``."""
        try:
            self._refresh()
            self.status.last_success_at = datetime.now(timezone.utc)
            self.status.last_error = None
        except Exception as error:  # noqa: BLE001 - surface any failure in status
            logger.exception("Financial reports refresh failed")
            self.status.last_error = str(error) or error.__class__.__name__
        finally:
            self.status.running = False
            self._run_lock.release()

    def run_if_idle(self, trigger: str = "cron") -> None:
        """Entry point for scheduled runs: silently skip if one is already running."""
        try:
            self.try_begin(trigger, enforce_cooldown=False)
        except RefreshInProgress:
            logger.info("Skipping %s refresh; another refresh is running", trigger)
            return
        self.run_claimed()

    # ----- work ------------------------------------------------------------

    def _refresh(self) -> None:
        """
        Optimized Locking Strategy: The slow HTTP network call to Alpha Vantage 
        occurs outside self.store.lock. The store lock is only acquired during the 
        sub-millisecond file write and parsing phases. This guarantees that user 
        queries to GET /reports or GET /watchlist are not blocked while waiting 
        for external API responses.
        """
        api_key = self.settings.alphavantage_api_key
        if not api_key:
            raise GeneratorError("ALPHAVANTAGE_API_KEY is not configured.")
        # Network I/O happens outside the store lock so reads stay fast.
        raw = self.fetcher(api_key, self.settings.refresh_horizon)
        with self.store.lock:
            self.store.write_raw(raw)
            self._rebuild_from(raw)

    def refilter(self) -> bool:
        """Rebuild events for the current watchlist from the cached raw CSV.
        Used when the watchlist changes (e.g., adding or removing a stock ticker)

        Returns False when no cache exists yet; events of removed symbols are
        still dropped, but newly added symbols appear only after a refresh.

        If a raw provider CSV is cached on disk, it re-evaluates the events
        against the new watchlist without burning Alpha Vantage API call limits.

        If no raw cache exists yet, it purges removed symbols from existing events.
        """
        with self.store.lock:
            raw = self.store.read_raw()
            if raw is not None:
                self._rebuild_from(raw)
                return True
            symbols = set(self.store.read_watchlist())
            self.store.write_events([e for e in self.store.read_events() if e.symbol in symbols])
            return False

    def _rebuild_from(self, raw: str) -> list[EarningsEvent]:
        companies = self.store.read_watchlist()
        # The previous CSV plays the role the published .ics plays for the CLI:
        # it lets revised report dates be retained as reschedule notices.
        previous = self.store.read_events()
        # Passes the raw CSV, company watchlist, and previous events into the generator.
        # to detect date revisions and remove already-occurred events.
        events = generate_events(raw, companies, previous, self.today())
        # Writes the new events list into financial_reports.csv.
        self.store.write_events(events)
        # Calculate matched and missing symbols for status reporting.
        matched = sorted({event.symbol for event in events})
        self.status.event_count = len(events)
        self.status.matched_symbols = matched
        self.status.missing_symbols = sorted(set(companies) - set(matched))
        return events

    # ----- schedule --------------------------------------------------------

    def start_scheduler(self) -> None:
        scheduler = BackgroundScheduler(timezone=self.settings.refresh_tz)
        scheduler.add_job(
            self.run_if_idle,
            CronTrigger.from_crontab(self.settings.refresh_cron, timezone=self.settings.refresh_tz),
            id="refresh-financial-reports",
            kwargs={"trigger": "cron"},
            max_instances=1,
            coalesce=True,
            misfire_grace_time=3600,
        )
        if not self.settings.reports_csv.exists() and self.settings.alphavantage_api_key:
            """
            First start: populate the CSV right away instead of waiting for cron.
            If the server starts and reports.csv does not exist yet (but an API key is provided),
            it schedules a one-off run (id="initial-refresh") 1 second in the future to seed data immediately.
            """
            scheduler.add_job(
                self.run_if_idle,
                "date",
                run_date=datetime.now(timezone.utc) + timedelta(seconds=1),
                id="initial-refresh",
                kwargs={"trigger": "startup"},
            )
        scheduler.start()
        self.scheduler = scheduler

    def shutdown_scheduler(self) -> None:
        """Gracefully terminates the background thread pool when FastAPI shuts down."""
        if self.scheduler is not None:
            self.scheduler.shutdown(wait=False)
            self.scheduler = None

    def next_run_at(self) -> datetime | None:
        """Returns the next scheduled run time of the refresh job."""
        if self.scheduler is None:
            return None
        job = self.scheduler.get_job("refresh-financial-reports")
        return job.next_run_time if job else None

    def cooldown_until(self) -> datetime | None:
        """Returns the time until which refreshes are rate-limited."""
        if self.status.last_run_at is None:
            return None
        until = self.status.last_run_at + timedelta(seconds=self.settings.refresh_cooldown_seconds)
        return until if until > datetime.now(timezone.utc) else None
