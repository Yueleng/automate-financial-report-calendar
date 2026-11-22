"""Binary object storage backends for uploaded PDF attachments.

Supports local filesystem storage (default for development) and AWS S3 (or any
S3-compatible object store such as Cloudflare R2 / MinIO).
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Protocol

from .config import Settings

CHUNK_SIZE = 64 * 1024


class StorageBackend(Protocol):
    def save(self, key: str, data: bytes, content_type: str = "application/pdf") -> None:
        """Persist raw bytes under ``key``."""

    def open_stream(self, key: str) -> tuple[Iterator[bytes], int | None]:
        """Return ``(byte_chunks, content_length)`` for ``key``.

        Raises ``FileNotFoundError`` if the object does not exist.
        """

    def delete(self, key: str) -> None:
        """Remove ``key`` if it exists (idempotent)."""


class LocalStorage:
    """Stores files on the local filesystem under ``base_dir``."""

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir.resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _resolve(self, key: str) -> Path:
        clean_key = key.lstrip("/")
        target = (self.base_dir / clean_key).resolve()
        if self.base_dir not in target.parents:
            raise ValueError(f"Invalid storage key: {key!r}")
        return target

    def save(self, key: str, data: bytes, content_type: str = "application/pdf") -> None:
        target = self._resolve(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        # Write to a temp file in the same directory then atomically replace.
        fd, tmp_path = tempfile.mkstemp(dir=target.parent, prefix=".upload-", suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
            os.replace(tmp_path, target)
        except BaseException:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

    def open_stream(self, key: str) -> tuple[Iterator[bytes], int | None]:
        target = self._resolve(key)
        if not target.is_file():
            raise FileNotFoundError(key)
        size = target.stat().st_size

        def _chunks() -> Iterator[bytes]:
            with target.open("rb") as handle:
                while chunk := handle.read(CHUNK_SIZE):
                    yield chunk

        return _chunks(), size

    def delete(self, key: str) -> None:
        target = self._resolve(key)
        try:
            target.unlink()
        except FileNotFoundError:
            pass


class S3Storage:
    """Stores files in an AWS S3 (or S3-compatible) bucket."""

    def __init__(
        self,
        bucket: str,
        region: str = "us-east-1",
        prefix: str = "attachments",
        endpoint_url: str | None = None,
    ) -> None:
        if not bucket:
            raise ValueError("S3_BUCKET must be configured when STORAGE_BACKEND=s3")
        import boto3

        self.bucket = bucket
        self.prefix = prefix.strip("/")
        self._client = boto3.client("s3", region_name=region, endpoint_url=endpoint_url or None)

    def _full_key(self, key: str) -> str:
        clean = key.lstrip("/")
        return f"{self.prefix}/{clean}" if self.prefix else clean

    def save(self, key: str, data: bytes, content_type: str = "application/pdf") -> None:
        self._client.put_object(
            Bucket=self.bucket,
            Key=self._full_key(key),
            Body=data,
            ContentType=content_type,
        )

    def open_stream(self, key: str) -> tuple[Iterator[bytes], int | None]:
        from botocore.exceptions import ClientError

        try:
            response = self._client.get_object(Bucket=self.bucket, Key=self._full_key(key))
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code")
            if code in {"NoSuchKey", "404", "NotFound"}:
                raise FileNotFoundError(key) from exc
            raise

        body = response["Body"]
        content_length = response.get("ContentLength")

        def _chunks() -> Iterator[bytes]:
            try:
                yield from body.iter_chunks(chunk_size=CHUNK_SIZE)
            finally:
                body.close()

        return _chunks(), content_length

    def delete(self, key: str) -> None:
        self._client.delete_object(Bucket=self.bucket, Key=self._full_key(key))


def make_storage(settings: Settings) -> StorageBackend:
    backend = settings.storage_backend.lower()
    if backend == "local":
        return LocalStorage(settings.local_storage_dir)
    if backend == "s3":
        return S3Storage(
            bucket=settings.s3_bucket,
            region=settings.s3_region,
            prefix=settings.s3_prefix,
            endpoint_url=settings.s3_endpoint_url,
        )
    raise ValueError(f"Unsupported STORAGE_BACKEND: {settings.storage_backend!r} (expected 'local' or 's3')")
