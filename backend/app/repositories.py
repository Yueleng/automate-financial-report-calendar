"""Database access: watchlist, events, provider snapshots and job runs."""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .domain import Company, EarningsEvent, event_uid
from .models import EarningsEventRow, JobRun, ProviderSnapshot, WatchlistItem


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class WatchlistRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

    def read(self) -> dict[str, Company]:
        """Read all watchlist items and return as a dict of symbol -> Company."""
        rows = self.session.scalars(select(WatchlistItem).order_by(WatchlistItem.symbol))
        return {r.symbol: Company(symbol=r.symbol, name=r.name) for r in rows}

    def add(self, company: Company) -> None:
        """Add a company to the watchlist"""
        self.session.add(WatchlistItem(symbol=company.symbol, name=company.name))
        self.session.flush()

    def remove(self, symbol: str) -> None:
        """Remove a company from the watchlist by symbol"""
        self.session.execute(delete(WatchlistItem).where(WatchlistItem.symbol == symbol))

    def replace(self, companies: list[Company]) -> None:
        """Make the table equal to ``companies``, upserting names."""
        wanted = {c.symbol: c for c in companies}
        self.session.execute(delete(WatchlistItem).where(WatchlistItem.symbol.not_in(list(wanted) or [""])))
        existing = {r.symbol: r for r in self.session.scalars(select(WatchlistItem))}
        for symbol, company in wanted.items():
            if symbol in existing:
                existing[symbol].name = company.name
            else:
                self.session.add(WatchlistItem(symbol=symbol, name=company.name))
        self.session.flush()

    def upsert_many(self, companies: list[Company]) -> None:
        """Make the table union of the existing companies and the given companies"""
        existing = {r.symbol: r for r in self.session.scalars(select(WatchlistItem))}
        for company in companies:
            if company.symbol in existing:
                existing[company.symbol].name = company.name
            else:
                self.session.add(WatchlistItem(symbol=company.symbol, name=company.name))
        self.session.flush()


def row_to_event(row: EarningsEventRow) -> EarningsEvent:
    return EarningsEvent(
        symbol=row.symbol,
        name=row.name,
        report_date=row.report_date,
        fiscal_date_ending=row.fiscal_date_ending.isoformat(),
        estimate=row.estimate,
        currency=row.currency,
        rescheduled_to=row.rescheduled_to,
    )


class EventRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

    def query(
        self,
        start: date | None = None,
        end: date | None = None,
        symbols: set[str] | None = None,
        include_unwatched: bool = False,
    ) -> list[EarningsEventRow]:
        stmt = select(EarningsEventRow)
        if start is not None:
            stmt = stmt.where(EarningsEventRow.report_date >= start)
        if end is not None:
            stmt = stmt.where(EarningsEventRow.report_date <= end)
        if symbols is not None:
            stmt = stmt.where(EarningsEventRow.symbol.in_(symbols))
        if not include_unwatched:
            stmt = stmt.where(EarningsEventRow.symbol.in_(select(WatchlistItem.symbol)))
        stmt = stmt.order_by(
            EarningsEventRow.report_date,
            EarningsEventRow.symbol,
            EarningsEventRow.rescheduled_to.is_not(None),
        )
        return list(self.session.scalars(stmt))

    def sync(self, parsed: list[EarningsEvent], now: datetime | None = None) -> None:
        """Upsert provider rows; turn superseded dates into permanent reschedule notices.

        Rows are never deleted, so past events and notices stay available. A stored
        active row becomes a notice when the provider reports the same fiscal period
        under a different date.
        """
        now = now or utcnow()
        current_dates: dict[tuple[str, date], date] = {}
        for event in parsed:
            fiscal = date.fromisoformat(event.fiscal_date_ending)
            current_dates.setdefault((event.symbol, fiscal), event.report_date)
            uid = event_uid(event)
            row = self.session.get(EarningsEventRow, uid)
            if row is None:
                self.session.add(
                    EarningsEventRow(
                        id=uid,
                        symbol=event.symbol,
                        name=event.name,
                        report_date=event.report_date,
                        fiscal_date_ending=fiscal,
                        estimate=event.estimate,
                        currency=event.currency,
                        rescheduled_to=None,
                        first_seen_at=now,
                        last_seen_at=now,
                    )
                )
            else:
                row.name = event.name
                row.estimate = event.estimate
                row.currency = event.currency
                row.rescheduled_to = None  # the provider reports this date again
                row.last_seen_at = now
        self.session.flush()

        active_dates = {(e.symbol, date.fromisoformat(e.fiscal_date_ending), e.report_date) for e in parsed}
        stored = self.session.scalars(
            select(EarningsEventRow).where(EarningsEventRow.symbol.in_({s for s, _ in current_dates}))
        )
        # Detect superseded date and mark the old event if it was rescheduled
        for row in stored:
            key = (row.symbol, row.fiscal_date_ending)
            if key not in current_dates or (*key, row.report_date) in active_dates:
                continue
            if row.rescheduled_to is None:
                row.rescheduled_to = current_dates[key]
        self.session.flush()

    def last_updated(self) -> datetime | None:
        run = JobRepo(self.session).last_success()
        return run.finished_at if run else None


class SnapshotRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

    def latest(self) -> str | None:
        stmt = select(ProviderSnapshot.body).order_by(ProviderSnapshot.id.desc()).limit(1)
        return self.session.scalar(stmt)

    def save(self, body: str, horizon: str) -> None:
        """Keep only the newest snapshot."""
        self.session.execute(delete(ProviderSnapshot))
        self.session.add(ProviderSnapshot(fetched_at=utcnow(), horizon=horizon, body=body))
        self.session.flush()


class JobRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

    def latest(self) -> JobRun | None:
        return self.session.scalar(select(JobRun).order_by(JobRun.id.desc()).limit(1))

    def last_success(self) -> JobRun | None:
        return self.session.scalar(select(JobRun).where(JobRun.success.is_(True)).order_by(JobRun.id.desc()).limit(1))

    def start(self, trigger: str) -> JobRun:
        # Callers hold the advisory lock, so any unfinished row is a leftover of a crash.
        for stale in self.session.scalars(select(JobRun).where(JobRun.finished_at.is_(None))):
            stale.finished_at = utcnow()
            stale.success = False
            stale.error = "interrupted"
        run = JobRun(trigger=trigger, started_at=utcnow(), matched_symbols=[], missing_symbols=[])
        self.session.add(run)
        self.session.flush()
        return run

    def has_events(self) -> bool:
        return self.session.scalar(select(EarningsEventRow.id).limit(1)) is not None
