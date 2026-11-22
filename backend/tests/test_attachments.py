"""Tests for PDF attachment upload, inline streaming, listing, and deletion."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.storage import LocalStorage

SAMPLE_PDF = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n"
SAMPLE_CSV = "\n".join(
    [
        "symbol,name,reportDate,fiscalDateEnding,estimate,currency,timeOfTheDay",
        "NVDA,NVIDIA CORP,2026-10-28,2026-09-30,1.25,USD,post-market",
    ]
)


def _make_client_with_storage(database_url: str, tmp_path: Path, max_upload_bytes: int = 1024 * 1024) -> TestClient:
    settings = Settings(
        alphavantage_api_key="test-key",
        database_url=database_url,
        refresh_cooldown_seconds=0,
        scheduler_enabled=False,
        storage_backend="local",
        local_storage_dir=tmp_path / "uploads",
        max_upload_bytes=max_upload_bytes,
    )
    app = create_app(
        settings,
        fetcher=lambda _key, _horizon: SAMPLE_CSV,
        storage=LocalStorage(tmp_path / "uploads"),
    )
    client = TestClient(app)
    assert client.put("/api/watchlist", json=[{"symbol": "NVDA", "name": "NVIDIA"}]).status_code == 200
    assert client.post("/api/jobs/refresh").status_code == 202
    return client


def test_upload_list_stream_and_delete_multiple_pdfs(database_url: str, tmp_path: Path) -> None:
    client = _make_client_with_storage(database_url, tmp_path)
    reports = client.get("/api/reports").json()["reports"]
    assert len(reports) == 1
    event_id = reports[0]["id"]
    assert reports[0]["attachments"] == []

    # Upload two PDFs for the same earnings event.
    up1 = client.post(
        f"/api/reports/{event_id}/attachments",
        files={"file": ("Q3-Press-Release.pdf", SAMPLE_PDF, "application/pdf")},
    )
    assert up1.status_code == 201
    att1 = up1.json()
    assert att1["filename"] == "Q3-Press-Release.pdf"
    assert att1["size_bytes"] == len(SAMPLE_PDF)
    assert att1["event_id"] == event_id

    up2 = client.post(
        f"/api/reports/{event_id}/attachments",
        files={"file": ("Q3-10Q-Filing.pdf", SAMPLE_PDF + b"extra", "application/pdf")},
    )
    assert up2.status_code == 201
    att2 = up2.json()

    # Reports endpoint includes both attachments.
    refreshed = client.get("/api/reports").json()["reports"][0]
    assert {a["id"] for a in refreshed["attachments"]} == {att1["id"], att2["id"]}

    # Direct list endpoint returns both.
    listed = client.get(f"/api/reports/{event_id}/attachments")
    assert listed.status_code == 200
    assert len(listed.json()) == 2

    # Inline streaming endpoint serves PDF bytes with Content-Disposition: inline.
    streamed = client.get(f"/api/attachments/{att1['id']}/file")
    assert streamed.status_code == 200
    assert streamed.headers["content-type"] == "application/pdf"
    assert streamed.headers["content-disposition"].startswith('inline; filename="Q3-Press-Release.pdf"')
    assert streamed.content == SAMPLE_PDF

    # Delete first attachment; second remains.
    deleted = client.delete(f"/api/attachments/{att1['id']}")
    assert deleted.status_code == 204
    assert client.get(f"/api/attachments/{att1['id']}/file").status_code == 404

    remaining = client.get(f"/api/reports/{event_id}/attachments").json()
    assert [a["id"] for a in remaining] == [att2["id"]]


def test_upload_validation_errors(database_url: str, tmp_path: Path) -> None:
    client = _make_client_with_storage(database_url, tmp_path, max_upload_bytes=100)
    event_id = client.get("/api/reports").json()["reports"][0]["id"]

    # Non-existent event -> 404
    missing = client.post(
        "/api/reports/does-not-exist/attachments",
        files={"file": ("report.pdf", SAMPLE_PDF, "application/pdf")},
    )
    assert missing.status_code == 404

    # Non-PDF bytes -> 400
    not_pdf = client.post(
        f"/api/reports/{event_id}/attachments",
        files={"file": ("notes.txt", b"hello world", "text/plain")},
    )
    assert not_pdf.status_code == 400

    # Empty file -> 400
    empty = client.post(
        f"/api/reports/{event_id}/attachments",
        files={"file": ("empty.pdf", b"", "application/pdf")},
    )
    assert empty.status_code == 400

    # Oversized file -> 413
    too_big = client.post(
        f"/api/reports/{event_id}/attachments",
        files={"file": ("huge.pdf", SAMPLE_PDF + b"x" * 200, "application/pdf")},
    )
    assert too_big.status_code == 413
