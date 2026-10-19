"""FastAPI application entrypoint.

Run with a single worker (the refresh scheduler lives in-process)::

    uvicorn app.main:app --reload --port 8000
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import Settings
from .jobs import Fetcher, RefreshService
from .routers import jobs, reports, watchlist
from .store import ReportStore


def create_app(settings: Settings | None = None, fetcher: Fetcher | None = None) -> FastAPI:
    # Called directly on the class
    settings = settings or Settings.from_env()
    # instantiate ReportStore with settings
    store = ReportStore(settings)
    # instantiate RefreshService with settings and store
    refresh = RefreshService(settings, store, fetcher=fetcher)

    # @asynccontextmanager - Context manager for managing the application lifecycle.
    # lifespan is called automatically when the application starts and stops.
    # It is used to start and stop the background scheduler.
    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if settings.scheduler_enabled:
            refresh.start_scheduler()
        try:
            yield
        finally:
            refresh.shutdown_scheduler()

    app = FastAPI(title="Financial Reports API", version="1.0.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.store = store
    app.state.refresh = refresh

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health", tags=["health"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(reports.router, prefix="/api")
    app.include_router(watchlist.router, prefix="/api")
    app.include_router(jobs.router, prefix="/api")
    return app


logging.basicConfig(level=logging.INFO)
app = create_app()
