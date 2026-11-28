"""Pydantic request/response models (mirrored in frontend/src/lib/api.ts)."""

from __future__ import annotations

from datetime import date, datetime

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class Attachment(BaseModel):
    id: str
    event_id: str
    filename: str
    content_type: str
    size_bytes: int
    uploaded_at: datetime


class Report(BaseModel):
    id: str
    symbol: str
    name: str
    report_date: date
    fiscal_date_ending: date
    estimate: str
    currency: str
    source: Literal["alpha_vantage", "manual"] = "alpha_vantage"
    rescheduled_to: date | None = None
    status: Literal["active", "rescheduled"] = "active"
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None
    attachments: list[Attachment] = Field(default_factory=list)


class ManualReportPayload(BaseModel):
    symbol: str = Field(min_length=1, max_length=15, pattern=r"^[A-Za-z0-9.\-]+$")
    report_date: date
    fiscal_date_ending: date
    estimate: str = Field(default="", max_length=32)
    currency: str = Field(default="USD", max_length=10)
    force: bool = False

    @field_validator("symbol")
    @classmethod
    def _upper_symbol(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("estimate")
    @classmethod
    def _strip_estimate(cls, value: str) -> str:
        return value.strip()

    @field_validator("currency")
    @classmethod
    def _upper_currency(cls, value: str) -> str:
        return value.strip().upper()

    @model_validator(mode="after")
    def _check_fiscal_before_report(self) -> "ManualReportPayload":
        if self.fiscal_date_ending > self.report_date:
            raise ValueError("Fiscal period end date cannot be after the report date.")
        return self


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
