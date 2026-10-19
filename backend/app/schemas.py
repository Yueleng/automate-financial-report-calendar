"""Pydantic request/response models (mirrored in frontend/src/lib/api.ts)."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator


class Report(BaseModel):
    id: str
    symbol: str
    name: str
    report_date: date
    fiscal_date_ending: date
    estimate: str
    currency: str
    rescheduled_to: date | None = None


class ReportsResponse(BaseModel):
    updated_at: datetime | None
    reports: list[Report]


class WatchlistItem(BaseModel):
    symbol: str = Field(min_length=1, max_length=15, pattern=r"^[A-Za-z0-9.\-]+$")
    name: str = Field(default="", max_length=100)

    @field_validator("symbol")
    @classmethod
    def _upper(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("name")
    @classmethod
    def _strip(cls, value: str) -> str:
        return value.strip()


class WatchlistResponse(BaseModel):
    items: list[WatchlistItem]
    # False when there was no cached provider data to re-filter, meaning newly
    # added symbols will only get events after the next refresh.
    refiltered: bool = True


class JobStatusResponse(BaseModel):
    running: bool
    trigger: str | None
    last_run_at: datetime | None
    last_success_at: datetime | None
    last_error: str | None
    event_count: int | None
    matched_symbols: list[str]
    missing_symbols: list[str]
    next_run_at: datetime | None
    cooldown_until: datetime | None
    updated_at: datetime | None
