"""Database access: watchlist, events, provider snapshots and job runs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
import uuid

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from .domain import Company, EarningsEvent, event_uid
from .models import EarningsEventRow, JobRun, ProviderSnapshot, ReportAttachment, WatchlistItem

PROXIMITY_WARNING_DAYS = 60


@dataclass(frozen=True)
class EventConflict:
    event_id: str
    symbol: str
    report_date: date
    fiscal_date_ending: date
    days_apart: int
    source: str
    reason: str  # "duplicate_date" | "duplicate_fiscal_period" | "proximity"


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
        source=row.source,
    )


class EventRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, event_id: str) -> EarningsEventRow | None:
        stmt = (
            select(EarningsEventRow)
            .options(selectinload(EarningsEventRow.attachments))
            .where(EarningsEventRow.id == event_id)
        )
        return self.session.scalar(stmt)

    def query(
        self,
        start: date | None = None,
        end: date | None = None,
        symbols: set[str] | None = None,
        include_unwatched: bool = False,
        exclude_manual: bool = False,
    ) -> list[EarningsEventRow]:
        stmt = select(EarningsEventRow).options(selectinload(EarningsEventRow.attachments))
        if start is not None:
            stmt = stmt.where(EarningsEventRow.report_date >= start)
        if end is not None:
            stmt = stmt.where(EarningsEventRow.report_date <= end)
        if symbols is not None:
            stmt = stmt.where(EarningsEventRow.symbol.in_(symbols))
        if not include_unwatched:
            stmt = stmt.where(EarningsEventRow.symbol.in_(select(WatchlistItem.symbol)))
        if exclude_manual:
            stmt = stmt.where(EarningsEventRow.source != "manual")
        stmt = stmt.order_by(
            EarningsEventRow.report_date,
            EarningsEventRow.symbol,
            EarningsEventRow.rescheduled_to.is_not(None),
        )
        return list(self.session.scalars(stmt))

    def find_conflicts(
        self,
        symbol: str,
        report_date: date,
        fiscal_date_ending: date,
        *,
        proximity_days: int = PROXIMITY_WARNING_DAYS,
        exclude_event_id: str | None = None,
    ) -> list[EventConflict]:
        """Find duplicate or nearby active events for the same symbol."""
        stmt = (
            select(EarningsEventRow)
            .where(EarningsEventRow.symbol == symbol)
            .where(EarningsEventRow.rescheduled_to.is_(None))
        )
        if exclude_event_id is not None:
            stmt = stmt.where(EarningsEventRow.id != exclude_event_id)

        conflicts: list[EventConflict] = []
        for row in self.session.scalars(stmt):
            days_apart = abs((row.report_date - report_date).days)
            if row.report_date == report_date:
                reason = "duplicate_date"
            elif row.fiscal_date_ending == fiscal_date_ending:
                reason = "duplicate_fiscal_period"
            elif days_apart <= proximity_days:
                reason = "proximity"
            else:
                continue
            conflicts.append(
                EventConflict(
                    event_id=row.id,
                    symbol=row.symbol,
                    report_date=row.report_date,
                    fiscal_date_ending=row.fiscal_date_ending,
                    days_apart=days_apart,
                    source=row.source,
                    reason=reason,
                )
            )
        conflicts.sort(key=lambda c: (c.reason != "duplicate_date", c.days_apart, c.report_date))
        return conflicts

    def create_manual(
        self,
        *,
        symbol: str,
        name: str,
        report_date: date,
        fiscal_date_ending: date,
        estimate: str = "",
        currency: str = "",
        now: datetime | None = None,
    ) -> EarningsEventRow:
        now = now or utcnow()
        row = EarningsEventRow(
            id=f"manual-{uuid.uuid4().hex[:16]}",
            symbol=symbol,
            name=name,
            report_date=report_date,
            fiscal_date_ending=fiscal_date_ending,
            estimate=estimate,
            currency=currency if estimate else "",
            source="manual",
            rescheduled_to=None,
            first_seen_at=now,
            last_seen_at=now,
        )
        self.session.add(row)
        self.session.flush()
        return row

    def update_manual(
        self,
        row: EarningsEventRow,
        *,
        symbol: str,
        name: str,
        report_date: date,
        fiscal_date_ending: date,
        estimate: str = "",
        currency: str = "",
        now: datetime | None = None,
    ) -> EarningsEventRow:
        row.symbol = symbol
        row.name = name
        row.report_date = report_date
        row.fiscal_date_ending = fiscal_date_ending
        row.estimate = estimate
        row.currency = currency if estimate else ""
        row.last_seen_at = now or utcnow()
        self.session.flush()
        return row

    def delete_manual(self, row: EarningsEventRow) -> list[str]:
        storage_keys = [att.storage_key for att in row.attachments]
        self.session.delete(row)
        self.session.flush()
        return storage_keys

    def sync(self, parsed: list[EarningsEvent], now: datetime | None = None) -> None:
        """Upsert provider rows; turn superseded dates into permanent reschedule notices.

        Rows are never deleted, so past events and notices stay available. A stored
        active provider row becomes a notice when the provider reports the same fiscal
        period under a different date. Manual rows are never modified by sync.
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
                        source="alpha_vantage",
                        rescheduled_to=None,
                        first_seen_at=now,
                        last_seen_at=now,
                    )
                )
            elif row.source != "manual":
                row.name = event.name
                row.estimate = event.estimate
                row.currency = event.currency
                row.rescheduled_to = None  # the provider reports this date again
                row.last_seen_at = now
        self.session.flush()

        active_dates = {(e.symbol, date.fromisoformat(e.fiscal_date_ending), e.report_date) for e in parsed}
        stored = self.session.scalars(
            select(EarningsEventRow)
            .where(EarningsEventRow.symbol.in_({s for s, _ in current_dates}))
            .where(EarningsEventRow.source != "manual")
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


class AttachmentRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

    def event_exists(self, event_id: str) -> bool:
        return self.session.get(EarningsEventRow, event_id) is not None

    def list_for_event(self, event_id: str) -> list[ReportAttachment]:
        stmt = (
            select(ReportAttachment)
            .where(ReportAttachment.event_id == event_id)
            .order_by(ReportAttachment.uploaded_at.desc())
        )
        return list(self.session.scalars(stmt))

    def get(self, attachment_id: str) -> ReportAttachment | None:
        return self.session.get(ReportAttachment, attachment_id)

    def create(
        self,
        *,
        attachment_id: str,
        event_id: str,
        filename: str,
        content_type: str,
        size_bytes: int,
        storage_key: str,
    ) -> ReportAttachment:
        row = ReportAttachment(
            id=attachment_id,
            event_id=event_id,
            filename=filename,
            content_type=content_type,
            size_bytes=size_bytes,
            storage_key=storage_key,
            uploaded_at=utcnow(),
        )
        self.session.add(row)
        self.session.flush()
        return row

    def delete(self, attachment_id: str) -> ReportAttachment | None:
        row = self.session.get(ReportAttachment, attachment_id)
        if row is None:
            return None
        self.session.delete(row)
        self.session.flush()
        return row
