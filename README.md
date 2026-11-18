# Financial Reports Calendar

Tracks upcoming earnings dates for a watchlist of companies and shows them in a calendar.

- **Backend:** FastAPI + Postgres (SQLAlchemy, Alembic). A daily job pulls Alpha Vantage's earnings calendar.
- **Frontend:** Next.js calendar and watchlist editor.
- **Database:** the watchlist and all earnings events live in Postgres.
  - Configuration (the watchlist) is not stored in the repo.
  - Events are **persistent**. Past events and "rescheduled to ..." notices are never deleted.
- **Feed:** `GET /api/calendar.ics` serves an iCalendar feed you can subscribe to, if the backend is reachable.

## Setup

```bash
cp .env.example .env        # set ALPHAVANTAGE_API_KEY (free key: https://www.alphavantage.co/support/#api-key)
make setup
make db-up                  # Postgres 16 via docker compose
make migrate                # create tables
make backend                # http://localhost:8000
make frontend               # http://localhost:3000
```

`DATABASE_URL` defaults to the docker-compose database
(`postgresql+psycopg://fin:fin@localhost:5433/fin`).

### Importing an existing watchlist

The watchlist is edited in the UI (or `/api/watchlist`). To import a legacy CSV (`symbol,name` header) once:

```bash
make seed CSV=path/to/watchlist.csv
```

The previous `watchlist.csv` was removed from the repo. Recover it with `git show HEAD:watchlist.csv > /tmp/watchlist.csv`.

## How refreshes work

1. The job runs daily (`REFRESH_CRON`, default `0 6 * * *` in `REFRESH_TZ`), on first start when no events exist, and via "Refresh now" (5-minute cooldown).
2. The raw provider response is stored in `provider_snapshots`. Watchlist edits re-sync from that snapshot, so they cost no API call.
3. Events are upserted into `earnings_events`.
   - If the provider moves a report date for the same fiscal period, the old row is kept with `rescheduled_to` set. It stays visible permanently.
   - Events of symbols later removed from the watchlist are kept but hidden. Use `?include_unwatched=true` to see them.
4. Run history, status and cooldown are stored in `job_runs`, so they survive restarts.
   A Postgres advisory lock prevents overlapping refreshes, even across workers.

## Tests

```bash
make db-up
# fin_test must exist (tables are TRUNCATED, use a throwaway database):
docker compose exec db createdb -U fin fin_test
make test-backend           # TEST_DATABASE_URL overrides postgresql+psycopg://fin:fin@localhost:5433/fin_test
make test-frontend
```

## Schema changes

```bash
cd backend && .venv/bin/alembic revision --autogenerate -m "describe change"
make migrate
```
