"""
Refresh-job trigger and status endpoints.

A FastAPI router responsible for monitoring and triggering financial report refresh jobs.

It coordinates between the HTTP layer, the RefreshService (which handles fetching data 
from Alpha Vantage and rebuilding calendar events), and FastAPI's BackgroundTasks queue.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status

from ..deps import get_refresh
from ..jobs import RefreshCooldown, RefreshInProgress, RefreshService
from ..schemas import JobStatusResponse

# Registers all routes under the /jobs URL prefix with OpenAPI tag "jobs".
router = APIRouter(prefix="/jobs", tags=["jobs"])

# A type alias using Python's typing.Annotated and FastAPI's Depends(get_refresh) from
# deps.py. This injects the singleton RefreshService stored in request.app.state.refresh
# into endpoints cleanly.
Refresh = Annotated[RefreshService, Depends(get_refresh)]


# Translate internal domain state into the API Schema
def _status(refresh: RefreshService) -> JobStatusResponse:
    s = refresh.status
    return JobStatusResponse(
        running=s.running,
        trigger=s.trigger,
        last_run_at=s.last_run_at,
        last_success_at=s.last_success_at,
        last_error=s.last_error,
        event_count=s.event_count,
        matched_symbols=s.matched_symbols,
        missing_symbols=s.missing_symbols,
        next_run_at=refresh.next_run_at(),
        cooldown_until=refresh.cooldown_until(),
        updated_at=refresh.store.updated_at(),
    )

# Read-only status endpoint
# Usage: polled by the frontend to see whether a fresh is currently running,
#        when the next run will happen, or whether any error occurred during the
#        last execution.
@router.get("/status", response_model=JobStatusResponse)
def job_status(refresh: Refresh) -> JobStatusResponse:
    return _status(refresh)

# HTTP 202 Accepted: Indicates that the request has been accepted for background processing,
# returning immediately without making the client wait for network fetch and CSV parsing.
@router.post("/refresh", response_model=JobStatusResponse, status_code=status.HTTP_202_ACCEPTED)
def trigger_refresh(refresh: Refresh, background: BackgroundTasks) -> JobStatusResponse:
    """Start a refresh in the background; poll ``/jobs/status`` for completion."""
    try:
        # Claim the slot synchronously so concurrent clicks get 409, not a race.
        refresh.try_begin("manual", enforce_cooldown=True)
    except RefreshInProgress:
        raise HTTPException(status.HTTP_409_CONFLICT, "A refresh is already running.")
    except RefreshCooldown as error:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            str(error),
            headers={"Retry-After": str(error.retry_after)},
        )
    # Adds refresh.run_claimed to FastAPI's BackgroundTasks queue.
    # The BackgroundTasks are executed in a separate thread, allowing the
    # HTTP request to return immediately (FastAPI pattern) while the long-running
    # job runs in the background.
    background.add_task(refresh.run_claimed)
    return _status(refresh)
