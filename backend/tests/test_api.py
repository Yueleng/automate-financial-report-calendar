"""API tests: real Postgres (see conftest.py), injectable Alpha Vantage fetcher, no network."""

from __future__ import annotations

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


def make_settings(database_url: str, cooldown: int = 0) -> Settings:
    return Settings(
        alphavantage_api_key="test-key",
        database_url=database_url,
        refresh_cooldown_seconds=cooldown,
        scheduler_enabled=False,
    )


def make_client(database_url: str, fetcher: Fetcher, cooldown: int = 0, watchlist: bool = True) -> TestClient:
    app = create_app(make_settings(database_url, cooldown), fetcher=fetcher)
    client = TestClient(app)
    if watchlist:
        response = client.put(
            "/api/watchlist",
            json=[{"symbol": "NVDA", "name": "NVIDIA"}, {"symbol": "MSFT", "name": "Microsoft"}],
        )
        assert response.status_code == 200
    return client


@pytest.fixture
def fetcher() -> FakeFetcher:
    return FakeFetcher(RAW_V1, RAW_V2)


def test_reports_empty_before_first_refresh(database_url: str, fetcher: FakeFetcher) -> None:
    client = make_client(database_url, fetcher)
    body = client.get("/api/reports").json()
    assert body == {"updated_at": None, "reports": []}


def test_refresh_stores_and_serves_watchlist_events(database_url: str, fetcher: FakeFetcher) -> None:
    client = make_client(database_url, fetcher)
    response = client.post("/api/jobs/refresh")
    assert response.status_code == 202

    status = client.get("/api/jobs/status").json()
    assert status["running"] is False
    assert status["last_error"] is None
    assert status["event_count"] == 2

    body = client.get("/api/reports").json()
    assert body["updated_at"] is not None
    assert [(r["symbol"], r["report_date"]) for r in body["reports"]] == [
        ("MSFT", "2026-10-21"),
        ("NVDA", "2026-10-28"),
    ]
    # Watchlist name wins over the provider's upper-case name.
    assert body["reports"][1]["name"] == "NVIDIA"


def test_reports_filters(database_url: str, fetcher: FakeFetcher) -> None:
    client = make_client(database_url, fetcher)
    client.post("/api/jobs/refresh")
    by_symbol = client.get("/api/reports", params={"symbol": "nvda"}).json()["reports"]
    assert [r["symbol"] for r in by_symbol] == ["NVDA"]
    by_range = client.get("/api/reports", params={"start": "2026-10-25", "end": "2026-10-31"}).json()
    assert [r["symbol"] for r in by_range["reports"]] == ["NVDA"]


def test_reschedule_is_retained_across_refreshes(database_url: str, fetcher: FakeFetcher) -> None:
    client = make_client(database_url, fetcher)
    client.post("/api/jobs/refresh")
    client.post("/api/jobs/refresh")

    nvda = [r for r in client.get("/api/reports").json()["reports"] if r["symbol"] == "NVDA"]
    assert [(r["report_date"], r["rescheduled_to"]) for r in nvda] == [
        ("2026-10-28", "2026-10-29"),
        ("2026-10-29", None),
    ]
    assert "rescheduled to Oct 29" in client.get("/api/calendar.ics").text


def test_calendar_ics(database_url: str, fetcher: FakeFetcher) -> None:
    client = make_client(database_url, fetcher)
    client.post("/api/jobs/refresh")
    response = client.get("/api/calendar.ics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/calendar")
    assert response.text.count("BEGIN:VEVENT") == 2


def test_refresh_cooldown_returns_429(database_url: str, fetcher: FakeFetcher) -> None:
    client = make_client(database_url, fetcher, cooldown=300)
    assert client.post("/api/jobs/refresh").status_code == 202
    second = client.post("/api/jobs/refresh")
    assert second.status_code == 429
    assert int(second.headers["retry-after"]) > 0
    assert fetcher.calls == 1


def test_refresh_while_running_returns_409(database_url: str, fetcher: FakeFetcher) -> None:
    client = make_client(database_url, fetcher)
    app = cast(FastAPI, client.app)
    refresh = app.state.refresh
    refresh.try_begin("test", enforce_cooldown=False)
    try:
        assert client.post("/api/jobs/refresh").status_code == 409
    finally:
        refresh.run_claimed()


def test_refresh_failure_is_reported(database_url: str) -> None:
    def failing(api_key: str, horizon: str) -> str:
        raise RuntimeError("provider down")

    client = make_client(database_url, failing)
    client.post("/api/jobs/refresh")
    status = client.get("/api/jobs/status").json()
    assert status["last_error"] == "provider down"
    assert status["last_success_at"] is None


def test_watchlist_add_and_remove_refilters_without_fetch(database_url: str, fetcher: FakeFetcher) -> None:
    client = make_client(database_url, fetcher)
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

    assert [i["symbol"] for i in client.get("/api/watchlist").json()["items"]] == ["AAPL", "NVDA"]


def test_watchlist_validation(database_url: str, fetcher: FakeFetcher) -> None:
    client = make_client(database_url, fetcher)
    assert client.post("/api/watchlist", json={"symbol": "NVDA"}).status_code == 409
    assert client.post("/api/watchlist", json={"symbol": "bad symbol!"}).status_code == 422
    assert client.delete("/api/watchlist/NOPE").status_code == 404
    assert client.put("/api/watchlist", json=[]).status_code == 400


def test_watchlist_replace(database_url: str, fetcher: FakeFetcher) -> None:
    client = make_client(database_url, fetcher)
    response = client.put("/api/watchlist", json=[{"symbol": "msft", "name": "Microsoft"}])
    assert response.status_code == 200
    assert response.json()["items"] == [{"symbol": "MSFT", "name": "Microsoft"}]
    # No raw cache yet -> caller is told new symbols need a refresh.
    assert response.json()["refiltered"] is False


RAW_V3 = "\n".join([HEADER, "MSFT,MICROSOFT CORP,2026-10-21,2026-09-30,3.10,USD,post-market"])


def test_past_events_and_reschedule_notices_survive_later_refreshes(database_url: str) -> None:
    # V1 -> V2 reschedules NVDA; V3 no longer contains any NVDA row at all.
    client = make_client(database_url, FakeFetcher(RAW_V1, RAW_V2, RAW_V3))
    for _ in range(3):
        client.post("/api/jobs/refresh")

    reports = client.get("/api/reports").json()["reports"]
    rows = [(r["symbol"], r["report_date"], r["rescheduled_to"], r["status"]) for r in reports]
    assert rows == [
        ("MSFT", "2026-10-21", None, "active"),
        ("NVDA", "2026-10-28", "2026-10-29", "rescheduled"),
        ("NVDA", "2026-10-29", None, "active"),
    ]


def test_state_persists_across_app_restart(database_url: str, fetcher: FakeFetcher) -> None:
    first = make_client(database_url, fetcher)
    first.post("/api/jobs/refresh")
    second = make_client(database_url, fetcher, watchlist=False)
    assert {i["symbol"] for i in second.get("/api/watchlist").json()["items"]} == {"NVDA", "MSFT"}
    assert len(second.get("/api/reports").json()["reports"]) == 2
    assert second.get("/api/jobs/status").json()["last_success_at"] is not None


def test_removed_symbol_events_are_kept_but_hidden(database_url: str, fetcher: FakeFetcher) -> None:
    client = make_client(database_url, fetcher)
    client.post("/api/jobs/refresh")
    client.delete("/api/watchlist/MSFT")
    assert {r["symbol"] for r in client.get("/api/reports").json()["reports"]} == {"NVDA"}
    everything = client.get("/api/reports", params={"include_unwatched": "true"}).json()["reports"]
    assert {r["symbol"] for r in everything} == {"NVDA", "MSFT"}


def test_sync_is_idempotent(database_url: str, fetcher: FakeFetcher) -> None:
    client = make_client(database_url, FakeFetcher(RAW_V1))
    client.post("/api/jobs/refresh")
    client.post("/api/jobs/refresh")
    assert len(client.get("/api/reports").json()["reports"]) == 2
