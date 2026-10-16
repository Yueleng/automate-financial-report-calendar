# Financial Reports Calendar

This repo generates an auto-updating iCalendar feed for the companies in `watchlist.csv`.
Google Calendar can subscribe to the generated `.ics` URL after you publish it with GitHub Pages.

## Watchlist

Edit [watchlist.csv](watchlist.csv) to add or remove companies.

The current list uses the most common US-traded symbols:

- `MSFT` - Microsoft
- `PDD` - PDD Holdings
- `GOOGL` - Alphabet
- `TCEHY` - Tencent ADR
- `XIACY` - Xiaomi ADR
- `NVDA` - NVIDIA
- `MU` - Micron
- `BABA` - Alibaba ADR

For Tencent and Xiaomi, ADR symbols are used because the default data source is easiest to automate with US-style symbols. If you prefer Hong Kong listings, change them after confirming the provider's supported symbol format.

## One-Time Local Run

1. Get a free Alpha Vantage API key:
   <https://www.alphavantage.co/support/#api-key>

2. Run the generator:

```bash
export ALPHAVANTAGE_API_KEY="your_api_key"
python3 scripts/generate_financial_reports_calendar.py
```

3. The calendar file will be written to:

```text
dist/financial-reports.ics
```

You can import that file into Google Calendar once, but for automatic updates you should subscribe to a hosted URL instead.

## Auto-Updating Google Calendar Feed

The included GitHub Actions workflow runs monthly and deploys the generated calendar to GitHub Pages.

1. Push this folder to a GitHub repo.
2. In GitHub, add a repository secret named `ALPHAVANTAGE_API_KEY`.
3. In GitHub repo settings, enable Pages with source `GitHub Actions`.
4. Run the workflow once manually from the Actions tab.
5. Subscribe in Google Calendar using:

```text
https://YOUR_GITHUB_USERNAME.github.io/YOUR_REPO_NAME/financial-reports.ics
```

Google Calendar refresh timing is controlled by Google and is not immediate. The source calendar will be regenerated monthly by GitHub Actions.

### Revised earnings dates

Before publishing a new feed, the workflow downloads the currently published
calendar. If Alpha Vantage moves a company’s report date by less than 31 days
for the same fiscal period, the feed keeps the old, future event and labels it
for example as `NVDA financial report — rescheduled to Oct 29`. It also includes
the normal event on the new date. The labelled old event is removed after its
original date has passed.

## Useful Commands

Generate with a 12-month lookahead:

```bash
ALPHAVANTAGE_API_KEY="your_api_key" python3 scripts/generate_financial_reports_calendar.py --horizon 12month
```

Use a different watchlist or output path:

```bash
ALPHAVANTAGE_API_KEY="your_api_key" python3 scripts/generate_financial_reports_calendar.py \
  --watchlist watchlist.csv \
  --output dist/financial-reports.ics
```

Test without network using a CSV export:

```bash
python3 scripts/generate_financial_reports_calendar.py --input-csv sample-alpha-vantage.csv
```

## Data Source

The default source is Alpha Vantage's documented Earnings Calendar API. It returns expected company earnings in CSV format for the next 3, 6, or 12 months.

Docs: <https://www.alphavantage.co/documentation/#earnings-calendar>

---

## Web Application (Next.js + FastAPI)

In addition to the standalone CLI and GitHub Pages feed, this repository includes an interactive local web app:
- **FastAPI backend** (`backend/`): Serves earnings data directly from an atomic CSV store (`backend/data/financial_reports.csv`) and manages scheduled Alpha Vantage syncs via APScheduler.
- **Next.js frontend** (`frontend/`): Interactive FullCalendar earnings view, symbol chips filter, on-demand refresh button with rate-limit cooldown, and live watchlist management.

### Quickstart

#### 1. Setup & Environment

Install dependencies for both backend and frontend:
```bash
make setup
```
> This creates a Python virtual environment in `backend/.venv`, installs backend dependencies, and runs `pnpm install` for the Next.js frontend.

*(Optional)* If you plan to sync live earnings directly from Alpha Vantage, create a `.env` file in the repository root:
```bash
cp .env.example .env
# Edit .env and insert your API key:
# ALPHAVANTAGE_API_KEY="your_api_key_here"
```

---

#### 2. Running the App (Two Terminals)

Start the backend and frontend in separate terminal windows:

##### Terminal 1: Backend (FastAPI)
```bash
make backend
```
*Or manually:*
```bash
cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000
```
- **Backend URL:** [http://localhost:8000](http://localhost:8000)
- **Interactive Swagger Docs:** [http://localhost:8000/docs](http://localhost:8000/docs)
- **Health Check:** [http://localhost:8000/api/health](http://localhost:8000/api/health)

> **Note:** The background sync scheduler runs in-process via APScheduler, so run with a single worker (e.g. `--reload` in dev).

##### Terminal 2: Frontend (Next.js)
```bash
make frontend
```
*Or manually:*
```bash
cd frontend && pnpm dev
```
- **Web App UI:** [http://localhost:3000](http://localhost:3000)

> **Note:** The frontend automatically reverse-proxies `/api/*` requests to the backend at `http://localhost:8000/api/*` via Next.js rewrites configured in `frontend/next.config.ts`.

---

#### 3. Running Tests

Run the complete test suite across CLI core, FastAPI backend, and Next.js frontend:
```bash
make test
```

Or run test suites individually:
- `make test-backend` — Backend unit & API router tests via `pytest`
- `make test-frontend` — Frontend ESLint checks & production build validation
- `make test-core` — Standalone calendar generator CLI tests

### API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/health` | Liveness health check |
| `GET` | `/api/reports?start=&end=&symbol=` | Filtered earnings events from the local CSV store |
| `GET` | `/api/calendar.ics` | Subscription `.ics` feed generated from stored events |
| `GET` | `/api/watchlist` | Get current tracked companies |
| `POST` | `/api/watchlist` | Add company ticker → immediately re-filters local events |
| `DELETE` | `/api/watchlist/{symbol}` | Remove company ticker → immediately re-filters |
| `POST` | `/api/jobs/refresh` | Trigger background sync with Alpha Vantage (`202 Accepted`, `429` cooldown) |
| `GET` | `/api/jobs/status` | Current background job status and countdowns |

