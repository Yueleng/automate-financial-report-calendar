"""
The refresh job: Alpha Vantage -> Postgres, plus its schedule and status.

- fetches raw earnings data from Alpha Vantage (outside any DB transaction),
- stores the raw snapshot and upserts the watchlist's events (never deleting),
- enforces cooldown and single-run semantics with a Postgres advisory lock
  (so it holds across workers), and
- orchestrates the APScheduler cron job.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import Connection, Engine, text
from sqlalchemy.orm import Session, sessionmaker

from .config import Settings
from .domain import GeneratorError, fetch_alpha_vantage_csv, parse_events
from .models import JobRun
from .repositories import EventRepo, JobRepo, SnapshotRepo, WatchlistRepo, utcnow

logger = logging.getLogger(__name__)

Fetcher = Callable[[str, str], str]

# Arbitrary app-wide key for pg_try_advisory_lock.
ADVISORY_LOCK_KEY = 726_001


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

# Dataclass summarising execution health (derived from job_runs), timestamps, errors, and
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

#                ┌───────────────────────────┐
#                │ APScheduler (cron/startup)│
#                └─────────────┬─────────────┘
#                              │
# ┌──────────────────┐         │
# │  FastAPI Router  │─────────┴─────────► [RefreshService]
# │ (manual trigger) │                            │
# └──────────────────┘                            ▼
#                                    try_begin() / advisory lock
#                                      (pg_try_advisory_lock)
#                                                 │
#                                                 ▼
#                                             _refresh()
#                                                 │
#                                  ┌──────────────┴──────────────┐
#                                  ▼                             ▼
#                        Alpha Vantage Fetcher             DB Transaction
#                        (HTTP outside DB tx)           (SnapshotRepo.save)
#                                                                │
# ┌──────────────────┐                                           │
# │ Watchlist Router │─────────── refilter() ─────────────────►┌─┴─────────────────┐
# │   (mutations)    │        (cached snapshot,                │  sync_from_raw()  │
# └──────────────────┘         no network I/O)                 │ (WatchlistRepo &  │
#                                                              │  EventRepo.sync)  │
#                                                              └─────────┬─────────┘
#                                                                        │
#                                                                        ▼
#                                                                Postgres Database
#                                                            (snapshots, events, jobs)


def sync_from_raw(session: Session, raw: str) -> tuple[int, list[str], list[str]]:
    """Upsert events for the current watchlist from a raw provider CSV.

    Returns (event_count, matched_symbols, missing_symbols).
    """
    companies = WatchlistRepo(session).read()
    parsed = parse_events(raw, companies)
    EventRepo(session).sync(parsed)
    matched = sorted({event.symbol for event in parsed})
    return len(parsed), matched, sorted(set(companies) - set(matched))


def refilter(session: Session) -> bool:
    """Re-sync events for the current watchlist from the cached raw snapshot.

    Used after watchlist edits so no Alpha Vantage call is needed. Returns False when
    no snapshot exists yet (new symbols then appear only after a refresh).
    """
    raw = SnapshotRepo(session).latest()
    if raw is None:
        return False
    sync_from_raw(session, raw)
    return True

class RefreshService:
    def __init__(
        self,
        settings: Settings,
        engine: Engine,
        session_factory: sessionmaker[Session],
        fetcher: Fetcher | None = None,
    ) -> None:
        self.settings = settings
        self.engine = engine
        self.session_factory = session_factory
        self.fetcher = fetcher or fetch_alpha_vantage_csv
        self._lock_conn: Connection | None = None
        self._run_id: int | None = None
        self.scheduler: BackgroundScheduler | None = None

    # ----- status ----------------------------------------------------------

    def get_status(self) -> JobStatus:
        """Derive status from the persisted job runs (survives restarts)."""
        with self.session_factory() as session:
            jobs = JobRepo(session)
            latest = jobs.latest()
            success = jobs.last_success()
            if latest is None:
                return JobStatus()
            return JobStatus(
                running=latest.finished_at is None,
                trigger=latest.trigger,
                last_run_at=latest.started_at,
                last_success_at=success.finished_at if success else None,
                last_error=latest.error if latest.success is False else None,
                event_count=success.event_count if success else None,
                matched_symbols=list(success.matched_symbols) if success else [],
                missing_symbols=list(success.missing_symbols) if success else [],
            )

    # ----- triggering ------------------------------------------------------

    def try_begin(self, trigger: str, enforce_cooldown: bool) -> None:
        """Claim the run slot or raise; call run_claimed afterwards.

        Raises:
            RefreshCooldown: if enforce_cooldown and the last run was too recent.
            RefreshInProgress: if another refresh (any process) holds the advisory lock.
        """
        if enforce_cooldown:
            remaining = self._cooldown_remaining()
            if remaining > 0:
                raise RefreshCooldown(remaining)
        conn = self.engine.connect()
        if not conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": ADVISORY_LOCK_KEY}).scalar():
            conn.close()
            raise RefreshInProgress()
        self._lock_conn = conn
        with self.session_factory() as session:
            self._run_id = JobRepo(session).start(trigger).id
            session.commit()

    def run_claimed(self) -> None:
        """Execute a refresh whose slot was claimed with try_begin."""
        error: str | None = None
        result: tuple[int, list[str], list[str]] | None = None
        try:
            result = self._refresh()
        except Exception as exc:  # noqa: BLE001 - surface any failure in status
            logger.exception("Financial reports refresh failed")
            error = str(exc) or exc.__class__.__name__
        finally:
            try:
                self._finish(error, result)
            finally:
                self._release()

    def run_if_idle(self, trigger: str = "cron") -> None:
        """Entry point for scheduled runs: silently skip if one is already running."""
        try:
            self.try_begin(trigger, enforce_cooldown=False)
        except RefreshInProgress:
            logger.info("Skipping %s refresh; another refresh is running", trigger)
            return
        self.run_claimed()

    def _finish(self, error: str | None, result: tuple[int, list[str], list[str]] | None) -> None:
        with self.session_factory() as session:
            run = session.get(JobRun, self._run_id)
            if run is not None:
                run.finished_at = utcnow()
                run.success = error is None
                run.error = error
                if result is not None:
                    run.event_count, run.matched_symbols, run.missing_symbols = result
            session.commit()

    def _release(self) -> None:
        conn, self._lock_conn, self._run_id = self._lock_conn, None, None
        if conn is not None:
            try:
                conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": ADVISORY_LOCK_KEY})
            finally:
                conn.close()

    def _cooldown_remaining(self) -> int:
        with self.session_factory() as session:
            latest = JobRepo(session).latest()
        if latest is None:
            return 0
        elapsed = datetime.now(timezone.utc) - latest.started_at
        return self.settings.refresh_cooldown_seconds - int(elapsed.total_seconds())

    # ----- work ------------------------------------------------------------

    def _refresh(self) -> tuple[int, list[str], list[str]]:
        """Fetch (no transaction open), then store snapshot + events in one transaction."""
        api_key = self.settings.alphavantage_api_key
        if not api_key:
            raise GeneratorError("ALPHAVANTAGE_API_KEY is not configured.")
        raw = self.fetcher(api_key, self.settings.refresh_horizon)
        with self.session_factory() as session:
            SnapshotRepo(session).save(raw, self.settings.refresh_horizon)
            result = sync_from_raw(session, raw)
            session.commit()
        return result

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
        if self.settings.alphavantage_api_key and not self._has_events():
            """
            First start: populate the database right away instead of waiting for cron.
            If the server starts and no events are stored yet (but an API key is provided),
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
        with self.session_factory() as session:
            latest = JobRepo(session).latest()
        if latest is None:
            return None
        until = latest.started_at + timedelta(seconds=self.settings.refresh_cooldown_seconds)
        return until if until > datetime.now(timezone.utc) else None

    def _has_events(self) -> bool:
        with self.session_factory() as session:
            return JobRepo(session).has_events()
