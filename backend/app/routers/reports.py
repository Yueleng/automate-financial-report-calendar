"""Read-only endpoints serving persisted earnings events."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from ..db import get_session
from ..domain import build_calendar
from ..repositories import EventRepo, row_to_event
from ..schemas import Attachment, Report, ReportsResponse

router = APIRouter(tags=["reports"])

DbSession = Annotated[Session, Depends(get_session)]


@router.get("/reports", response_model=ReportsResponse)
def list_reports(
    session: DbSession,
    start: date | None = None,
    end: date | None = None,
    symbol: Annotated[list[str] | None, Query()] = None,
    include_unwatched: bool = False,
) -> ReportsResponse:
    """Return stored events (past and future), optionally filtered.

    start/end are inclusive bounds on report_date; symbol may be
    repeated. Events of symbols no longer on the watchlist are hidden unless
    include_unwatched is true.
    """
    symbols = {s.strip().upper() for s in symbol} if symbol else None
    repo = EventRepo(session)
    rows = repo.query(start, end, symbols, include_unwatched)
    reports = [
        Report(
            id=row.id,
            symbol=row.symbol,
            name=row.name,
            report_date=row.report_date,
            fiscal_date_ending=row.fiscal_date_ending,
            estimate=row.estimate,
            currency=row.currency,
            rescheduled_to=row.rescheduled_to,
            status="rescheduled" if row.rescheduled_to else "active",
            first_seen_at=row.first_seen_at,
            last_seen_at=row.last_seen_at,
            attachments=[
                Attachment(
                    id=att.id,
                    event_id=att.event_id,
                    filename=att.filename,
                    content_type=att.content_type,
                    size_bytes=att.size_bytes,
                    uploaded_at=att.uploaded_at,
                )
                for att in row.attachments
            ],
        )
        for row in rows
    ]
    return ReportsResponse(updated_at=repo.last_updated(), reports=reports)


@router.get("/calendar.ics", response_class=Response)
def calendar_ics(request: Request, session: DbSession) -> Response:
    """iCalendar feed of all watched events, built from the database."""
    events = [row_to_event(row) for row in EventRepo(session).query()]
    contents = build_calendar(events, request.app.state.settings.calendar_name)
    return Response(
        content=contents,
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": 'inline; filename="financial-reports.ics"'},
    )
