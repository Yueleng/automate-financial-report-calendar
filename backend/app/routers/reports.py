"""Endpoints serving persisted earnings events and manual historical entries."""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Annotated, Literal, cast
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.orm import Session

from ..db import get_session
from ..deps import get_storage
from ..domain import build_calendar
from ..models import EarningsEventRow
from ..repositories import EventConflict, EventRepo, WatchlistRepo, row_to_event
from ..schemas import Attachment, ManualReportPayload, Report, ReportsResponse
from ..storage import StorageBackend

logger = logging.getLogger(__name__)

router = APIRouter(tags=["reports"])

DbSession = Annotated[Session, Depends(get_session)]
Storage = Annotated[StorageBackend, Depends(get_storage)]


def _today_in_tz(tz_name: str) -> date:
    return datetime.now(ZoneInfo(tz_name)).date()


def _to_report_schema(row: EarningsEventRow) -> Report:
    source = cast(Literal["alpha_vantage", "manual"], "manual" if row.source == "manual" else "alpha_vantage")
    return Report(
        id=row.id,
        symbol=row.symbol,
        name=row.name,
        report_date=row.report_date,
        fiscal_date_ending=row.fiscal_date_ending,
        estimate=row.estimate,
        currency=row.currency,
        source=source,
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


def _format_conflict_warnings(conflicts: list[EventConflict]) -> list[dict[str, object]]:
    return [
        {
            "event_id": c.event_id,
            "symbol": c.symbol,
            "report_date": c.report_date.isoformat(),
            "fiscal_date_ending": c.fiscal_date_ending.isoformat(),
            "days_apart": c.days_apart,
            "source": c.source,
            "reason": c.reason,
        }
        for c in conflicts
    ]


def _validate_manual_event(
    *,
    request: Request,
    session: Session,
    payload: ManualReportPayload,
    exclude_event_id: str | None = None,
) -> str:
    """Validate watchlist membership, strictly-past date, and conflicts.

    Returns the company's canonical watchlist name.
    """
    watchlist = WatchlistRepo(session).read()
    company = watchlist.get(payload.symbol)
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Symbol {payload.symbol} is not in your watchlist. Add it to your watchlist first.",
        )

    today = _today_in_tz(request.app.state.settings.refresh_tz)
    if payload.report_date >= today:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Manual events can only be added for strictly past dates (before {today.isoformat()}).",
        )

    conflicts = EventRepo(session).find_conflicts(
        payload.symbol,
        payload.report_date,
        payload.fiscal_date_ending,
        exclude_event_id=exclude_event_id,
    )
    same_day = [c for c in conflicts if c.reason == "duplicate_date"]
    if same_day:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"An earnings event for {payload.symbol} already exists on {payload.report_date.isoformat()}.",
        )

    if conflicts and not payload.force:
        nearest = conflicts[0]
        if nearest.reason == "duplicate_fiscal_period":
            msg = (
                f"{payload.symbol} already has an event for fiscal period ending "
                f"{nearest.fiscal_date_ending.isoformat()} on {nearest.report_date.isoformat()}."
            )
        else:
            msg = (
                f"{payload.symbol} already has an earnings event on {nearest.report_date.isoformat()} "
                f"({nearest.days_apart} days away). Quarterly reports are typically ~90 days apart."
            )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "proximity_warning",
                "message": msg,
                "warnings": _format_conflict_warnings(conflicts),
            },
        )

    return company.name


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
    reports = [_to_report_schema(row) for row in rows]
    return ReportsResponse(updated_at=repo.last_updated(), reports=reports)


@router.post("/reports", response_model=Report, status_code=status.HTTP_201_CREATED)
def create_manual_report(
    payload: ManualReportPayload,
    request: Request,
    session: DbSession,
) -> Report:
    """Create a manual historical earnings event (strictly past dates only)."""
    company_name = _validate_manual_event(request=request, session=session, payload=payload)
    row = EventRepo(session).create_manual(
        symbol=payload.symbol,
        name=company_name,
        report_date=payload.report_date,
        fiscal_date_ending=payload.fiscal_date_ending,
        estimate=payload.estimate,
        currency=payload.currency,
    )
    session.commit()
    loaded = EventRepo(session).get(row.id)
    return _to_report_schema(loaded or row)


@router.put("/reports/{event_id}", response_model=Report)
def update_manual_report(
    event_id: str,
    payload: ManualReportPayload,
    request: Request,
    session: DbSession,
) -> Report:
    """Edit an existing manual earnings event. Provider events cannot be modified."""
    repo = EventRepo(session)
    row = repo.get(event_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Earnings event not found")
    if row.source != "manual":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only manually added events can be modified.",
        )

    company_name = _validate_manual_event(
        request=request,
        session=session,
        payload=payload,
        exclude_event_id=row.id,
    )
    repo.update_manual(
        row,
        symbol=payload.symbol,
        name=company_name,
        report_date=payload.report_date,
        fiscal_date_ending=payload.fiscal_date_ending,
        estimate=payload.estimate,
        currency=payload.currency,
    )
    session.commit()
    loaded = repo.get(row.id)
    return _to_report_schema(loaded or row)


@router.delete("/reports/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_manual_report(
    event_id: str,
    session: DbSession,
    storage: Storage,
) -> Response:
    """Delete a manual earnings event and cascade-delete its stored PDF attachments."""
    repo = EventRepo(session)
    row = repo.get(event_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Earnings event not found")
    if row.source != "manual":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only manually added events can be deleted.",
        )

    storage_keys = repo.delete_manual(row)
    session.commit()

    for key in storage_keys:
        try:
            storage.delete(key)
        except Exception:
            logger.warning("Failed to delete attachment object %s from storage", key, exc_info=True)

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/calendar.ics", response_class=Response)
def calendar_ics(request: Request, session: DbSession) -> Response:
    """iCalendar feed of provider-synced watched events (excludes manual past entries)."""
    events = [row_to_event(row) for row in EventRepo(session).query(exclude_manual=True)]
    contents = build_calendar(events, request.app.state.settings.calendar_name)
    return Response(
        content=contents,
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": 'inline; filename="financial-reports.ics"'},
    )
