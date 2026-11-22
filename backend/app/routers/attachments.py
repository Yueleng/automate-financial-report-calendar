"""Endpoints for uploading, streaming, listing, and deleting PDF report attachments."""

from __future__ import annotations

import logging
import re
import uuid
from pathlib import PurePath
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..db import get_session
from ..deps import get_storage
from ..models import ReportAttachment
from ..repositories import AttachmentRepo
from ..schemas import Attachment
from ..storage import StorageBackend

logger = logging.getLogger(__name__)

router = APIRouter(tags=["attachments"])

DbSession = Annotated[Session, Depends(get_session)]
Storage = Annotated[StorageBackend, Depends(get_storage)]

PDF_MAGIC = b"%PDF-"
_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._ \-]+")


def _to_schema(row: ReportAttachment) -> Attachment:
    return Attachment(
        id=row.id,
        event_id=row.event_id,
        filename=row.filename,
        content_type=row.content_type,
        size_bytes=row.size_bytes,
        uploaded_at=row.uploaded_at,
    )


def _sanitize_filename(raw: str | None) -> str:
    name = PurePath(raw or "").name.strip()
    name = _SAFE_FILENAME_RE.sub("_", name).strip(" .")
    if not name:
        name = "financial-report.pdf"
    if not name.lower().endswith(".pdf"):
        name = f"{name}.pdf"
    return name[:200]


def _content_disposition_inline(filename: str) -> str:
    ascii_fallback = filename.encode("ascii", "ignore").decode("ascii").replace('"', "'") or "report.pdf"
    encoded = quote(filename, safe="")
    return f'inline; filename="{ascii_fallback}"; filename*=UTF-8\'\'{encoded}'


@router.get("/reports/{event_id}/attachments", response_model=list[Attachment])
def list_attachments(event_id: str, session: DbSession) -> list[Attachment]:
    repo = AttachmentRepo(session)
    if not repo.event_exists(event_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Earnings event not found")
    return [_to_schema(row) for row in repo.list_for_event(event_id)]


@router.post(
    "/reports/{event_id}/attachments",
    response_model=Attachment,
    status_code=status.HTTP_201_CREATED,
)
async def upload_attachment(
    event_id: str,
    request: Request,
    session: DbSession,
    storage: Storage,
    file: UploadFile = File(...),
) -> Attachment:
    repo = AttachmentRepo(session)
    if not repo.event_exists(event_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Earnings event not found")

    max_bytes: int = request.app.state.settings.max_upload_bytes
    data = await file.read(max_bytes + 1)
    await file.close()

    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty")
    if len(data) > max_bytes:
        limit_mb = max_bytes // (1024 * 1024)
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"File exceeds maximum allowed size of {limit_mb} MB",
        )
    if not data.startswith(PDF_MAGIC):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only valid PDF files are supported",
        )

    attachment_id = uuid.uuid4().hex
    filename = _sanitize_filename(file.filename)
    storage_key = f"{event_id}/{attachment_id}.pdf"

    storage.save(storage_key, data, content_type="application/pdf")
    try:
        row = repo.create(
            attachment_id=attachment_id,
            event_id=event_id,
            filename=filename,
            content_type="application/pdf",
            size_bytes=len(data),
            storage_key=storage_key,
        )
        session.commit()
    except BaseException:
        session.rollback()
        try:
            storage.delete(storage_key)
        except Exception:
            logger.warning("Failed to clean up orphaned object %s", storage_key, exc_info=True)
        raise

    return _to_schema(row)


@router.get("/attachments/{attachment_id}/file")
def stream_attachment_file(
    attachment_id: str,
    session: DbSession,
    storage: Storage,
) -> StreamingResponse:
    row = AttachmentRepo(session).get(attachment_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not found")

    try:
        chunks, content_length = storage.open_stream(row.storage_key)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stored PDF file not found") from exc

    headers = {
        "Content-Disposition": _content_disposition_inline(row.filename),
        "Cache-Control": "private, max-age=3600",
        "X-Content-Type-Options": "nosniff",
    }
    if content_length is not None:
        headers["Content-Length"] = str(content_length)

    return StreamingResponse(chunks, media_type=row.content_type or "application/pdf", headers=headers)


@router.delete("/attachments/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_attachment(
    attachment_id: str,
    session: DbSession,
    storage: Storage,
) -> Response:
    repo = AttachmentRepo(session)
    row = repo.delete(attachment_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not found")
    storage_key = row.storage_key
    session.commit()

    try:
        storage.delete(storage_key)
    except Exception:
        logger.warning("Failed to delete object %s from storage", storage_key, exc_info=True)

    return Response(status_code=status.HTTP_204_NO_CONTENT)
