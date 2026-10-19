"""Single import point for the standalone core utility in ``scripts/``.

The core stays a self-contained CLI script (used unchanged by GitHub Actions),
so the backend adds ``scripts/`` to ``sys.path`` here and nowhere else.
"""

from __future__ import annotations

import sys

from .config import PROJECT_ROOT

_SCRIPTS_DIR = str(PROJECT_ROOT / "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from generate_financial_reports_calendar import (  # noqa: E402
    Company,
    EarningsEvent,
    GeneratorError,
    build_calendar,
    event_uid,
    events_from_csv,
    events_to_csv,
    fetch_alpha_vantage_csv,
    generate_events,
    read_watchlist,
)

__all__ = [
    "Company",
    "EarningsEvent",
    "GeneratorError",
    "build_calendar",
    "event_uid",
    "events_from_csv",
    "events_to_csv",
    "fetch_alpha_vantage_csv",
    "generate_events",
    "read_watchlist",
]
