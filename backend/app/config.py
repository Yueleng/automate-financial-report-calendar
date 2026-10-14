"""Runtime settings for the backend, read from environment variables.

The repository-root ``.env`` (already used by the CLI for the Alpha Vantage
key) is loaded first, so local development needs no extra configuration.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent

load_dotenv(PROJECT_ROOT / ".env")


def _env(name: str, default: str) -> str:
    value = os.environ.get(name, "").strip()
    return value or default


@dataclass
class Settings:
    alphavantage_api_key: str = ""
    watchlist_path: Path = PROJECT_ROOT / "watchlist.csv"
    data_dir: Path = BACKEND_ROOT / "data"
    # Standard 5-field crontab, evaluated in refresh_tz.
    refresh_cron: str = "0 6 * * *"
    refresh_tz: str = "America/Toronto"
    refresh_horizon: str = "12month"
    # Minimum seconds between manual "Refresh now" runs (Alpha Vantage free
    # tier allows roughly 25 requests per day).
    refresh_cooldown_seconds: int = 300
    calendar_name: str = "Financial Reports Watchlist"
    cors_origins: list[str] = field(default_factory=lambda: ["http://localhost:3000"])
    # Tests disable the background scheduler so no real network call happens.
    scheduler_enabled: bool = True

    @property
    def reports_csv(self) -> Path:
        """Filtered watchlist events served by the API."""
        return self.data_dir / "financial_reports.csv"

    @property
    def raw_csv(self) -> Path:
        """Last full Alpha Vantage response, cached so watchlist edits need no API call."""
        return self.data_dir / "earnings_raw.csv"

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            alphavantage_api_key=_env("ALPHAVANTAGE_API_KEY", ""),
            watchlist_path=Path(_env("WATCHLIST_PATH", str(PROJECT_ROOT / "watchlist.csv"))),
            data_dir=Path(_env("DATA_DIR", str(BACKEND_ROOT / "data"))),
            refresh_cron=_env("REFRESH_CRON", "0 6 * * *"),
            refresh_tz=_env("REFRESH_TZ", "America/Toronto"),
            refresh_horizon=_env("REFRESH_HORIZON", "12month"),
            refresh_cooldown_seconds=int(_env("REFRESH_COOLDOWN_SECONDS", "300")),
            cors_origins=[
                origin.strip()
                for origin in _env("CORS_ORIGINS", "http://localhost:3000").split(",")
                if origin.strip()
            ],
            scheduler_enabled=_env("SCHEDULER_ENABLED", "true").lower() not in {"0", "false", "no"},
        )
