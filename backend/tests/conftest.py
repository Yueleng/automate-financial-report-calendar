"""Test database fixtures. Needs Postgres: set TEST_DATABASE_URL to a throwaway database.

All tables are truncated before every test, so never point this at real data.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text

DEFAULT_TEST_URL = "postgresql+psycopg://fin:fin@localhost:5433/fin_test"
TABLES = "report_attachments, watchlist_items, earnings_events, provider_snapshots, job_runs"


@pytest.fixture(scope="session")
def database_url() -> str:
    return os.environ.get("TEST_DATABASE_URL", DEFAULT_TEST_URL)


@pytest.fixture(scope="session")
def migrated_engine(database_url: str) -> Engine:
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    command.upgrade(config, "head")
    engine = create_engine(database_url)
    yield engine
    engine.dispose()


@pytest.fixture(autouse=True)
def clean_db(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {TABLES} RESTART IDENTITY"))

