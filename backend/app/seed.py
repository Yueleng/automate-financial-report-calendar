"""One-off import of a legacy watchlist.csv into the database.

    python -m app.seed --watchlist-csv watchlist.csv

Idempotent: existing symbols just get their name updated.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from .config import Settings
from .db import make_engine, make_session_factory
from .domain import Company
from .repositories import WatchlistRepo


def read_csv(path: Path) -> list[Company]:
    with path.open(newline="", encoding="utf-8") as file:
        rows = csv.DictReader(file)
        if rows.fieldnames is None or "symbol" not in rows.fieldnames:
            raise SystemExit(f"{path} must include a 'symbol' column.")
        companies: dict[str, Company] = {}
        for row in rows:
            symbol = (row.get("symbol") or "").strip().upper()
            if symbol:
                companies[symbol] = Company(symbol=symbol, name=(row.get("name") or symbol).strip())
    return list(companies.values())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--watchlist-csv", type=Path, required=True)
    args = parser.parse_args()
    companies = read_csv(args.watchlist_csv)
    engine = make_engine(Settings.from_env().database_url)
    with make_session_factory(engine)() as session:
        WatchlistRepo(session).upsert_many(companies)
        session.commit()
    print(f"Seeded {len(companies)} symbols.")


if __name__ == "__main__":
    main()
