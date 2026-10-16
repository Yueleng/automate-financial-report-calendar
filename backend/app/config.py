"""Runtime settings for the backend, read from environment variables.

The repository-root ``.env`` (already used by the CLI for the Alpha Vantage
key) is loaded first, so local development needs no extra configuration.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# Path.parents provides a sequence of all logical ancestor directories of a path,
# ordered from the closest parent outward to the root filesystem.
# __file__ is the current file, which is app/config.py.
# .resolve() returns an absolute path.
# .parents[0] is app/, the parent of config.py.
# .parents[1] is backend/, the parent of app/.
BACKEND_ROOT = Path(__file__).resolve().parents[1]
# PROJECT_ROOT is the root of the repository, which is the parent of backend/.
PROJECT_ROOT = BACKEND_ROOT.parent

# load_dotenv will not overwrite
# existing environment variables by default.
# To overwrite an environment variable
# if it is already set in your shell environment,
# you can explicitly pass override=True.
# Example: load_dotenv(PROJECT_ROOT / ".env", override=True)
load_dotenv(PROJECT_ROOT / ".env")


def _env(name: str, default: str) -> str:
    """
    Helper function to get environment variables with support
    for the ``.env`` file.
    """
    value = os.environ.get(name, "").strip()
    return value or default


# dataclass decorator generates:
# - __init__() that accepts all arguments
# - __repr__() for developer-friendly output
# - __eq__() for value-based comparison
# - etc.
@dataclass
class Settings:
    # Alpha Vantage API key
    alphavantage_api_key: str = ""
    # Path to watchlist.csv
    watchlist_path: Path = PROJECT_ROOT / "watchlist.csv"
    # Directory for earnings data files
    data_dir: Path = BACKEND_ROOT / "data"
    # Standard 5-field crontab
    refresh_cron: str = "0 6 * * *"
    # Timezone for cron evaluation
    refresh_tz: str = "America/Toronto"
    # Earnings horizon
    refresh_horizon: str = "12month"
    # Minimum seconds between manual "Refresh now" runs
    refresh_cooldown_seconds: int = 300
    # Calendar name
    calendar_name: str = "Financial Reports Watchlist"
    # CORS origins
    cors_origins: list[str] = field(default_factory=lambda: ["http://localhost:3000"])
    # Tests disable the background scheduler so no real network call happens.
    scheduler_enabled: bool = True

    # @property turns a method into a getter so you can access it like a regular
    # variable without parentheses (), but it computes its value dynamically on access
    # read-only properties (can't be set like ``settings.reports_csv = ...``)
    @property
    def reports_csv(self) -> Path:
        """Filtered watchlist events served by the API."""
        return self.data_dir / "financial_reports.csv"

    @property
    def raw_csv(self) -> Path:
        """Last full Alpha Vantage response, cached so watchlist edits need no API call."""
        return self.data_dir / "earnings_raw.csv"

    # @classmethod - Binds the method to the class itself, rather than to a specific
    # instance (self). The first parameter passed is cls (the class itself, e.g., Settings),
    # not self.
    # Returns a new instance of Settings, configured with values read from environment
    # variables.
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
