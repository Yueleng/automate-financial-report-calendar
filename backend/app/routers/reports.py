"""Read-only endpoints serving the CSV data store."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from ..core import build_calendar, event_uid
from ..deps import get_store
from ..schemas import Report, ReportsResponse
from ..store import ReportStore

router = APIRouter(tags=["reports"])


@router.get("/reports", response_model=ReportsResponse)
def list_reports(
    # Inject the singleton ReportStore instance (from deps.py).
    store: Annotated[ReportStore, Depends(get_store)],
    start: date | None = None,
    end: date | None = None,
    symbol: Annotated[list[str] | None, Query()] = None,
) -> ReportsResponse:
    """Return events from financial_reports.csv, optionally filtered.

    ``start``/``end`` are inclusive bounds on ``report_date``; ``symbol`` may be
    repeated (``?symbol=NVDA&symbol=MSFT``).
    """
    symbols = {s.strip().upper() for s in symbol} if symbol else None
    reports = [
        Report(
            id=event_uid(event),
            symbol=event.symbol,
            name=event.name,
            report_date=event.report_date,
            fiscal_date_ending=date.fromisoformat(event.fiscal_date_ending),
            estimate=event.estimate,
            currency=event.currency,
            rescheduled_to=event.rescheduled_to,
        )
        for event in store.read_events()
        if (start is None or event.report_date >= start)
        and (end is None or event.report_date <= end)
        and (symbols is None or event.symbol in symbols)
    ]
    return ReportsResponse(updated_at=store.updated_at(), reports=reports)


@router.get("/calendar.ics", response_class=Response)
def calendar_ics(store: Annotated[ReportStore, Depends(get_store)]) -> Response:
    """The same iCalendar feed the CLI produces, built from the CSV store."""
    contents = build_calendar(store.read_events(), store.settings.calendar_name)
    return Response(
        content=contents,
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": 'inline; filename="financial-reports.ics"'},
    )
