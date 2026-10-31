"""API tests: no network, temp CSV files, injectable Alpha Vantage fetcher."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings
from app.jobs import Fetcher
from app.main import create_app

# Test file header
HEADER = "symbol,name,reportDate,fiscalDateEnding,estimate,currency,timeOfTheDay"
# Test raw data
RAW_V1 = "\n".join(
    [
        HEADER,
        "NVDA,NVIDIA CORP,2026-10-28,2026-09-30,1.25,USD,post-market",
        "MSFT,MICROSOFT CORP,2026-10-21,2026-09-30,3.10,USD,post-market",
        "AAPL,APPLE INC,2026-10-30,2026-09-30,1.50,USD,post-market",
        "ZZZZ,NOT WATCHED,2026-10-30,2026-09-30,0.10,USD,post-market",
    ]
)
# NVDA moved from Oct 28 to Oct 29 for the same fiscal quarter.
RAW_V2 = RAW_V1.replace("NVDA,NVIDIA CORP,2026-10-28", "NVDA,NVIDIA CORP,2026-10-29")


class FakeFetcher:
    def __init__(self, *bodies: str) -> None:
        self.bodies = list(bodies)
        self.calls = 0

    def __call__(self, api_key: str, horizon: str) -> str:
        self.calls += 1
        return self.bodies.pop(0) if len(self.bodies) > 1 else self.bodies[0]


def make_client(tmp_path: Path, fetcher: Fetcher, cooldown: int = 0) -> TestClient:
    watchlist = tmp_path / "watchlist.csv"
    watchlist.write_text("symbol,name\nNVDA,NVIDIA\nMSFT,Microsoft\n", encoding="utf-8")
    settings = Settings(
        alphavantage_api_key="test-key",
        watchlist_path=watchlist,
        data_dir=tmp_path / "data",
        refresh_cooldown_seconds=cooldown,
        scheduler_enabled=False,
    )
    app = create_app(settings, fetcher=fetcher)
    app.state.refresh.today = lambda: date(2026, 10, 1)
    return TestClient(app)


@pytest.fixture
def fetcher() -> FakeFetcher:
    return FakeFetcher(RAW_V1, RAW_V2)


def test_reports_empty_before_first_refresh(tmp_path: Path, fetcher: FakeFetcher) -> None:
    client = make_client(tmp_path, fetcher)
    body = client.get("/api/reports").json()
    assert body == {"updated_at": None, "reports": []}


def test_refresh_writes_csv_and_serves_watchlist_events(tmp_path: Path, fetcher: FakeFetcher) -> None:
    client = make_client(tmp_path, fetcher)
    response = client.post("/api/jobs/refresh")
    assert response.status_code == 202

    status = client.get("/api/jobs/status").json()
    assert status["running"] is False
    assert status["last_error"] is None
    assert status["event_count"] == 2
    assert (tmp_path / "data" / "financial_reports.csv").exists()
    assert (tmp_path / "data" / "earnings_raw.csv").exists()

    body = client.get("/api/reports").json()
    assert body["updated_at"] is not None
    assert [(r["symbol"], r["report_date"]) for r in body["reports"]] == [
        ("MSFT", "2026-10-21"),
        ("NVDA", "2026-10-28"),
    ]
    # Watchlist name wins over the provider's upper-case name.
    assert body["reports"][1]["name"] == "NVIDIA"


def test_reports_filters(tmp_path: Path, fetcher: FakeFetcher) -> None:
    client = make_client(tmp_path, fetcher)
    client.post("/api/jobs/refresh")
    by_symbol = client.get("/api/reports", params={"symbol": "nvda"}).json()["reports"]
    assert [r["symbol"] for r in by_symbol] == ["NVDA"]
    by_range = client.get("/api/reports", params={"start": "2026-10-25", "end": "2026-10-31"}).json()
    assert [r["symbol"] for r in by_range["reports"]] == ["NVDA"]


def test_reschedule_is_retained_via_csv_across_refreshes(tmp_path: Path, fetcher: FakeFetcher) -> None:
    client = make_client(tmp_path, fetcher)
    client.post("/api/jobs/refresh")
    client.post("/api/jobs/refresh")

    nvda = [r for r in client.get("/api/reports").json()["reports"] if r["symbol"] == "NVDA"]
    assert [(r["report_date"], r["rescheduled_to"]) for r in nvda] == [
        ("2026-10-28", "2026-10-29"),
        ("2026-10-29", None),
    ]
    assert "rescheduled to Oct 29" in client.get("/api/calendar.ics").text


def test_calendar_ics(tmp_path: Path, fetcher: FakeFetcher) -> None:
    client = make_client(tmp_path, fetcher)
    client.post("/api/jobs/refresh")
    response = client.get("/api/calendar.ics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/calendar")
    assert response.text.count("BEGIN:VEVENT") == 2


def test_refresh_cooldown_returns_429(tmp_path: Path, fetcher: FakeFetcher) -> None:
    client = make_client(tmp_path, fetcher, cooldown=300)
    assert client.post("/api/jobs/refresh").status_code == 202
    second = client.post("/api/jobs/refresh")
    assert second.status_code == 429
    assert int(second.headers["retry-after"]) > 0
    assert fetcher.calls == 1


def test_refresh_while_running_returns_409(tmp_path: Path, fetcher: FakeFetcher) -> None:
    client = make_client(tmp_path, fetcher)
    app = cast(FastAPI, client.app)
    refresh = app.state.refresh
    refresh.try_begin("test", enforce_cooldown=False)
    try:
        assert client.post("/api/jobs/refresh").status_code == 409
    finally:
        refresh.run_claimed()


def test_refresh_failure_is_reported(tmp_path: Path) -> None:
    def failing(api_key: str, horizon: str) -> str:
        raise RuntimeError("provider down")

    client = make_client(tmp_path, failing)
    client.post("/api/jobs/refresh")
    status = client.get("/api/jobs/status").json()
    assert status["last_error"] == "provider down"
    assert status["last_success_at"] is None


def test_watchlist_add_and_remove_refilters_without_fetch(tmp_path: Path, fetcher: FakeFetcher) -> None:
    client = make_client(tmp_path, fetcher)
    client.post("/api/jobs/refresh")
    assert fetcher.calls == 1

    added = client.post("/api/watchlist", json={"symbol": "aapl", "name": "Apple"})
    assert added.status_code == 201
    assert added.json()["refiltered"] is True
    symbols = {r["symbol"] for r in client.get("/api/reports").json()["reports"]}
    assert symbols == {"NVDA", "MSFT", "AAPL"}

    removed = client.delete("/api/watchlist/MSFT")
    assert removed.status_code == 200
    symbols = {r["symbol"] for r in client.get("/api/reports").json()["reports"]}
    assert symbols == {"NVDA", "AAPL"}
    assert fetcher.calls == 1

    assert (tmp_path / "watchlist.csv").read_text(encoding="utf-8") == "symbol,name\nNVDA,NVIDIA\nAAPL,Apple\n"


def test_watchlist_validation(tmp_path: Path, fetcher: FakeFetcher) -> None:
    client = make_client(tmp_path, fetcher)
    assert client.post("/api/watchlist", json={"symbol": "NVDA"}).status_code == 409
    assert client.post("/api/watchlist", json={"symbol": "bad symbol!"}).status_code == 422
    assert client.delete("/api/watchlist/NOPE").status_code == 404
    assert client.put("/api/watchlist", json=[]).status_code == 400


def test_watchlist_replace(tmp_path: Path, fetcher: FakeFetcher) -> None:
    client = make_client(tmp_path, fetcher)
    response = client.put("/api/watchlist", json=[{"symbol": "msft", "name": "Microsoft"}])
    assert response.status_code == 200
    assert response.json()["items"] == [{"symbol": "MSFT", "name": "Microsoft"}]
    # No raw cache yet -> caller is told new symbols need a refresh.
    assert response.json()["refiltered"] is False
