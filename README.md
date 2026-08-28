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
