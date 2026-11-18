"""ORM models (schema is managed by Alembic migrations)."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import ARRAY, BigInteger, Boolean, Date, DateTime, Index, Integer, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class WatchlistItem(Base):
    __tablename__ = "watchlist_items"

    symbol: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EarningsEventRow(Base):
    """A persistent earnings event. Rows are never deleted by refreshes."""

    __tablename__ = "earnings_events"
    __table_args__ = (
        UniqueConstraint("symbol", "fiscal_date_ending", "report_date"),
        Index("ix_earnings_events_report_date", "report_date"),
        Index("ix_earnings_events_symbol_report_date", "symbol", "report_date"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)  # event_uid()
    symbol: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    report_date: Mapped[date] = mapped_column(Date)
    fiscal_date_ending: Mapped[date] = mapped_column(Date)
    estimate: Mapped[str] = mapped_column(Text, default="")
    currency: Mapped[str] = mapped_column(Text, default="")
    # Non-null marks a reschedule notice kept at the old date.
    rescheduled_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ProviderSnapshot(Base):
    """Raw Alpha Vantage response; the latest one is reused when the watchlist changes."""

    __tablename__ = "provider_snapshots"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    horizon: Mapped[str] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text)


class JobRun(Base):
    __tablename__ = "job_runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    trigger: Mapped[str] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    success: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    event_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    matched_symbols: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    missing_symbols: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)

