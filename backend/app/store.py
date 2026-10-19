"""CSV-file persistence for watchlist and earnings data (no database).

All writes are atomic (temp file + ``os.replace``) so a concurrent reader never
observes a half-written file, and serialized through one lock shared by the
cron job, manual refresh and watchlist edits.
"""

from __future__ import annotations

import csv
import io
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path

from .config import Settings
from .core import Company, EarningsEvent, events_from_csv, events_to_csv, read_watchlist


# By writing to a temporary file first and renaming it, readers only ever see
# the complete old version or the complete new version—never an intermediate state.
def atomic_write_text(path: Path, contents: str) -> None:
    """Replace ``path`` with ``contents`` in a single filesystem operation."""
    # Ensures the directory exists: Creates any missing parent directories (parents=True) 
    # and doesn't crash if the folder is already there.
    path.parent.mkdir(parents=True, exist_ok=True)

    # dir=path.parent (Crucial): Creates the temp file on the same filesystem/partition 
    # as the target file. Atomic renames cannot cross different filesystem partitions or mount points.
    # Returns a low-level file descriptor fd and a temporary file path tmp_name.
    # The suffix ".tmp" is added to the filename. e.g., .financial_reports.csv.a1b2c3.tmp
    # The leading dot keeps it hidden on Unix systems, preventing it from appearing in standard directory listings.
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        # Opens the file descriptor fd in write mode with UTF-8 encoding and newline="".
        # The newline="" argument is crucial for CSV files to prevent empty rows from being inserted.
        # os.fdopen(fd, ...) wraps the low-level descriptor into a standard Python text stream.
        # Exiting the with block closes and flushes the file data to disk.
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as file:
            file.write(contents)
        # Atomically replaces the original file with the temporary file.
        # At the OS filesystem level, this is an instantaneous, atomic pointer update. 
        # Any reader accessing path will always see either the old file or the new file in full.
        os.replace(tmp_name, path)
    except BaseException:
        # If an error occurs (disk full, process killed, encoding failure, etc.), 
        # unlink(missing_ok=True) deletes the temporary file so leftover .tmp 
        # junk doesn't accumulate on disk.
        # raise re-raises the exception to notify the caller that the write failed.
        Path(tmp_name).unlink(missing_ok=True)
        raise


class ReportStore:
    """
    Manages persistent storage for financial report data.

    Uses file-based storage instead of a database for simplicity.
    Provides thread-safe access through a shared lock.
    """
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        # Re-entrant lock allows a thread to acquire the same lock multiple times
        # without blocking itself. This is useful for methods that may call
        # other methods within the same class that also need the lock.
        self.lock = threading.RLock()

    # ----- earnings events (financial_reports.csv) -------------------------

    def read_events(self) -> list[EarningsEvent]:
        """Reads recently generated earnings events from financial_reports.csv."""
        path = self.settings.reports_csv
        if not path.exists():
            return []
        return events_from_csv(path.read_text(encoding="utf-8"))

    def write_events(self, events: list[EarningsEvent]) -> None:
        """Atomically writes events to financial_reports.csv."""
        with self.lock:
            atomic_write_text(self.settings.reports_csv, events_to_csv(events))

    # return last updated time of financial_reports.csv
    # path.stat(): Queries the filesystem for the file's metadata (file size, permissions, timestamps, etc.).
    # .st_mtime: Extracts the file's modification time (mtime). This comes back as a raw Unix timestamp
    # (a float representing seconds since the Unix Epoch, Jan 1, 1970 — for example, 1760570000.54).
    # datetime.fromtimestamp(..., tz=timezone.utc): Converts that raw numeric timestamp into a timezone-aware Python
    # datetime object explicitly set to UTC (e.g., 2026-10-15 22:30:00+00:00).
    def updated_at(self) -> datetime | None:
        path = self.settings.reports_csv
        if not path.exists():
            return None
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)

    # ----- raw provider cache (earnings_raw.csv) ---------------------------

    # read raw provider data from earnings_raw.csv
    def read_raw(self) -> str | None:
        path = self.settings.raw_csv
        return path.read_text(encoding="utf-8") if path.exists() else None

    # write raw provider data to earnings_raw.csv
    def write_raw(self, contents: str) -> None:
        with self.lock:
            atomic_write_text(self.settings.raw_csv, contents)

    # ----- watchlist (repo-root watchlist.csv, shared with the CLI/CI) -----

    # read watchlist from watchlist.csv
    def read_watchlist(self) -> dict[str, Company]:
        return read_watchlist(self.settings.watchlist_path)

    # write watchlist to watchlist.csv
    def write_watchlist(self, companies: list[Company]) -> None:
        buffer = io.StringIO()
        writer = csv.writer(buffer, lineterminator="\n")
        writer.writerow(["symbol", "name"])
        for company in companies:
            writer.writerow([company.symbol, company.name])
        with self.lock:
            atomic_write_text(self.settings.watchlist_path, buffer.getvalue())
