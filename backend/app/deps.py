"""FastAPI dependencies resolving shared services from ``app.state``."""

from __future__ import annotations

from fastapi import Request

from .jobs import RefreshService
from .store import ReportStore


# FastAPI's dependency injection system:
# - It retrieves the get_store() function and executes it whenever an
#   endpoint declares a dependency on get_store.
# - It calls the function with the active Request object.
# - It expects the function to return the value we want to inject.
# - It caches the return value, so the same ReportStore instance is reused for all
#   endpoints that request it within a single HTTP request.
def get_store(request: Request) -> ReportStore:
    return request.app.state.store


# FastAPI's dependency injection system:
# - It retrieves the get_refresh() function and executes it whenever an
#   endpoint declares a dependency on get_refresh.
# - It calls the function with the active Request object.
# - It expects the function to return the value we want to inject.
# - It caches the return value, so the same RefreshService instance is reused for all
#   endpoints that request it within a single HTTP request.
def get_refresh(request: Request) -> RefreshService:
    return request.app.state.refresh
