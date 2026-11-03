"""FastAPI dependencies resolving shared services from app.state."""

from __future__ import annotations

from fastapi import Request

from .jobs import RefreshService


# FastAPI's dependency injection system:
# - Executes get_refresh() when an endpoint declares Depends(get_refresh).
# - Injects the active Request object to access application state.
# - Returns the shared, application-wide RefreshService singleton stored on app.state.
# - Caches the dependency result per request (Depends default: use_cache=True).
def get_refresh(request: Request) -> RefreshService:
    return request.app.state.refresh
