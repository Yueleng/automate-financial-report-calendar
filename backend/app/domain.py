"""Pure domain logic: provider CSV parsing, event identity and iCalendar rendering.

No file or database access lives here; persistence is in repositories.py.
"""

from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Iterable
from urllib.parse import urlencode
from urllib.request import urlopen

ALPHAVANTAGE_URL = "https://www.alphavantage.co/query"
VALID_HORIZONS = {"3month", "6month", "12month"}



class GeneratorError(RuntimeError):
    """A user-facing failure (bad input, provider error).

    Library code raises this instead of SystemExit so callers such as the
    FastAPI background job can handle it like any other exception.
    """


@dataclass(frozen=True)
class Company:
    """One symbol from the user's watchlist."""
    symbol: str
    name: str


@dataclass(frozen=True)
class EarningsEvent:
    """The normalized data needed to render one all-day calendar event."""
    symbol: str
    name: str
    # the date the provider expects the report to be released, which may be revised
    # and it will be placed in the calendar as an all-day event on that date
    report_date: date
    # The fiscal quarter or year that the report covers.
    # for Q2, it usually is the last day of the quarter, e.g. 2026-06-30
    # while some corporation is wild and may use any other date.
    # for example, NVDA's Q2 2026 report covers the period ending 2026-07-31
    fiscal_date_ending: str
    estimate: str = ""
    currency: str = ""
    rescheduled_to: date | None = None


def fetch_alpha_vantage_csv(api_key: str, horizon: str) -> str:
    """Request Alpha Vantage's full earnings CSV and reject common error bodies."""
    # urlencode safely escapes API parameters before embedding them in the URL.
    query = urlencode(
        {
            "function": "EARNINGS_CALENDAR",
            "horizon": horizon,
            "apikey": api_key,
        }
    )
    with urlopen(f"{ALPHAVANTAGE_URL}?{query}", timeout=30) as response:
        body = response.read().decode("utf-8-sig")

    if "Thank you for using Alpha Vantage" in body or "Our standard API rate limit" in body:
        raise GeneratorError("Alpha Vantage rate limit reached. Try again later.")
    if "Invalid API call" in body:
        raise GeneratorError(f"Alpha Vantage returned an error:\n{body.strip()}")
    if "symbol" not in body.lower():
        raise GeneratorError(f"Unexpected Alpha Vantage response:\n{body[:500].strip()}")
    return body


def parse_date(value: str) -> date | None:
    """Parse provider dates, treating blank, placeholder, and malformed values as absent."""
    value = value.strip()
    if not value or value.lower() in {"none", "n/a", "nan"}:
        return None
    for date_format in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(value, date_format).date()
        except ValueError:
            continue
    return None


def parse_events(csv_text: str, companies: dict[str, Company]) -> list[EarningsEvent]:
    """Keep valid provider rows whose symbols appear in the watchlist.

    Alpha Vantage returns CSV in this form::

        symbol,name,reportDate,fiscalDateEnding,estimate,currency,timeOfTheDay
        BMO,BANK OF MONTREAL,2026-08-25,2026-07-31,2.72,USD,pre-market
        BNS,BANK OF NOVA SCOTIA (THE),2026-08-25,2026-07-31,1.53,USD,pre-market
        
    A set removes duplicate dataclass values before ordering makes the generated
    calendar deterministic (and therefore friendly to version control).
    """
    rows = csv.DictReader(csv_text.splitlines())
    if rows.fieldnames is None:
        raise GeneratorError("Source CSV is empty.")

    events: list[EarningsEvent] = []
    for row in rows:
        symbol = (row.get("symbol") or "").strip().upper()
        if symbol not in companies:
            continue

        report_date = parse_date(row.get("reportDate") or row.get("report_date") or "")
        if report_date is None:
            continue

        fiscal_date_ending = parse_date(row.get("fiscalDateEnding") or "")
        if fiscal_date_ending is None:
            continue

        company = companies[symbol]
        events.append(
            EarningsEvent(
                symbol=symbol,
                name=company.name,
                report_date=report_date,
                fiscal_date_ending=fiscal_date_ending.isoformat(),
                estimate=(row.get("estimate") or "").strip(),
                currency=(row.get("currency") or "").strip(),
            )
        )

    return sorted(set(events), key=lambda event: (event.report_date, event.symbol))


def same_reporting_period(previous: EarningsEvent, current: EarningsEvent) -> bool:
    """Return whether two provider rows represent the same reporting quarter."""
    return (
        previous.symbol == current.symbol
        and previous.fiscal_date_ending == current.fiscal_date_ending
    )



def ical_escape(value: str) -> str:
    """Escape characters that have special meaning in iCalendar text fields."""
    return (
        value.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )


def fold_ical_line(line: str) -> list[str]:
    """Fold long iCalendar content lines at the RFC 5545 75-character limit."""
    if len(line) <= 75:
        return [line]

    chunks: list[str] = []
    current = line
    while len(current) > 75:
        chunks.append(current[:75])
        # A leading space marks this chunk as a continuation line in .ics.
        current = " " + current[75:]
    chunks.append(current)
    return chunks


def event_uid(event: EarningsEvent) -> str:
    """Return a stable ID so calendar apps update, rather than duplicate, an event."""
    digest = hashlib.sha256(
        f"{event.symbol}|{event.report_date.isoformat()}|financial-report".encode("utf-8")
    ).hexdigest()[:16]
    return f"{digest}@financial-reports.local"


def event_description(event: EarningsEvent) -> str:
    """Build the human-readable details shown after a user opens an event."""
    lines = [
        f"Company: {event.name}",
        f"Symbol: {event.symbol}",
        f"Report date: {event.report_date.isoformat()}",
    ]
    lines.append(f"Fiscal period ending: {event.fiscal_date_ending}")
    if event.estimate:
        suffix = f" {event.currency}" if event.currency else ""
        lines.append(f"EPS estimate: {event.estimate}{suffix}")
    if event.rescheduled_to:
        lines.append(f"Rescheduled to: {event.rescheduled_to.isoformat()}")
    lines.append("Source: Alpha Vantage Earnings Calendar")
    return "\n".join(lines)


def build_calendar(events: Iterable[EarningsEvent], calendar_name: str) -> str:
    """Serialize events into a standards-compliant iCalendar (.ics) document."""
    # DTSTAMP records when this particular calendar export was produced.
    now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Investment Calendar//Financial Reports//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{ical_escape(calendar_name)}",
        "X-WR-TIMEZONE:America/Toronto",
    ]

    for event in events:
        start = event.report_date
        # All-day iCalendar events use an exclusive end date, hence next day.
        end = start + timedelta(days=1)
        summary = f"{event.symbol} financial report"
        if event.rescheduled_to:
            summary += f" — rescheduled to {event.rescheduled_to.strftime('%b %-d')}"
        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:{event_uid(event)}",
                f"DTSTAMP:{now}",
                f"DTSTART;VALUE=DATE:{start.strftime('%Y%m%d')}",
                f"DTEND;VALUE=DATE:{end.strftime('%Y%m%d')}",
                f"SUMMARY:{ical_escape(summary)}",
                f"DESCRIPTION:{ical_escape(event_description(event))}",
                *(
                    ["X-FINANCIAL-REPORT-STATUS:RESCHEDULED", f"X-FINANCIAL-REPORT-RESCHEDULED-TO:{event.rescheduled_to.strftime('%Y%m%d')}"]
                    if event.rescheduled_to
                    else []
                ),
                "TRANSP:TRANSPARENT",
                "END:VEVENT",
            ]
        )

    lines.append("END:VCALENDAR")

    folded_lines: list[str] = []
    for line in lines:
        folded_lines.extend(fold_ical_line(line))
    return "\r\n".join(folded_lines) + "\r\n"


