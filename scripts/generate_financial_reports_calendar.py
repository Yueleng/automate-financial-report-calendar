#!/usr/bin/env python3
"""Generate an iCalendar feed for upcoming financial report dates."""

from __future__ import annotations

import argparse
import csv
import hashlib
import os
import sys
import textwrap
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable
from urllib.parse import urlencode
from urllib.request import urlopen

from dotenv import load_dotenv


# Resolve paths relative to the repository, not the caller's current directory.
# This also lets a local .env file supply the API key during development.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")


ALPHAVANTAGE_URL = "https://www.alphavantage.co/query"
VALID_HORIZONS = {"3month", "6month", "12month"}


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
    # the fiscal quarter or year that the report covers, 
    # for Q2, it usually is the last day of the quarter, e.g. 2026-06-30
    # while some corporation is wild and may use any other date.
    fiscal_date_ending: str = ""
    estimate: str = ""
    currency: str = ""
    rescheduled_to: date | None = None


def parse_args() -> argparse.Namespace:
    """Define the command-line interface and return the selected options."""
    parser = argparse.ArgumentParser(
        description="Generate dist/financial-reports.ics from an earnings calendar source."
    )
    parser.add_argument("--watchlist", default="watchlist.csv", help="CSV with symbol,name columns.")
    parser.add_argument("--output", default="dist/financial-reports.ics", help="Output .ics path.")
    parser.add_argument(
        "--horizon",
        default="12month",
        choices=sorted(VALID_HORIZONS),
        help="Alpha Vantage earnings lookahead.",
    )
    parser.add_argument(
        "--input-csv",
        help="Use an existing Alpha Vantage earnings CSV instead of calling the API.",
    )
    parser.add_argument(
        "--calendar-name",
        default="Financial Reports Watchlist",
        help="Calendar display name embedded in the .ics file.",
    )
    parser.add_argument(
        "--previous-ics",
        help=(
            "Previously published .ics feed. Revised near-term report dates are retained "
            "there as reschedule notices until their original date passes."
        ),
    )
    return parser.parse_args()


def read_watchlist(path: Path) -> dict[str, Company]:
    """Load the watchlist into a symbol-keyed lookup table.

    Normalizing symbols here means later matching is insensitive to whitespace
    and letter case in either the watchlist or provider response.
    """
    if not path.exists():
        raise SystemExit(f"Watchlist not found: {path}")

    with path.open(newline="", encoding="utf-8") as file:
        rows = csv.DictReader(file)
        if rows.fieldnames is None or "symbol" not in rows.fieldnames:
            raise SystemExit("watchlist.csv must include a 'symbol' column.")

        companies: dict[str, Company] = {}
        for row in rows:
            symbol = (row.get("symbol") or "").strip().upper()
            if not symbol:
                continue
            name = (row.get("name") or symbol).strip()
            companies[symbol] = Company(symbol=symbol, name=name)

    if not companies:
        raise SystemExit("No symbols found in watchlist.")
    return companies


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
        raise SystemExit("Alpha Vantage rate limit reached. Try again later.")
    if "Invalid API call" in body:
        raise SystemExit(f"Alpha Vantage returned an error:\n{body.strip()}")
    if "symbol" not in body.lower():
        raise SystemExit(f"Unexpected Alpha Vantage response:\n{body[:500].strip()}")
    return body


def read_source_csv(args: argparse.Namespace) -> str:
    """Choose an offline CSV fixture when given; otherwise fetch live data."""
    if args.input_csv:
        return Path(args.input_csv).read_text(encoding="utf-8-sig")

    api_key = os.environ.get("ALPHAVANTAGE_API_KEY", "").strip()
    if not api_key:
        raise SystemExit(
            "Set ALPHAVANTAGE_API_KEY or pass --input-csv with an existing earnings CSV."
        )
    return fetch_alpha_vantage_csv(api_key, args.horizon)


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
        raise SystemExit("Source CSV is empty.")

    events: list[EarningsEvent] = []
    for row in rows:
        symbol = (row.get("symbol") or "").strip().upper()
        if symbol not in companies:
            continue

        report_date = parse_date(row.get("reportDate") or row.get("report_date") or "")
        if report_date is None:
            continue

        company = companies[symbol]
        events.append(
            EarningsEvent(
                symbol=symbol,
                name=company.name,
                report_date=report_date,
                fiscal_date_ending=(row.get("fiscalDateEnding") or "").strip(),
                estimate=(row.get("estimate") or "").strip(),
                currency=(row.get("currency") or "").strip(),
            )
        )

    return sorted(set(events), key=lambda event: (event.report_date, event.symbol))


def unfold_ical_lines(contents: str) -> list[str]:
    """Unfold RFC 5545 continuation lines before reading an existing feed."""
    lines: list[str] = []
    for line in contents.splitlines():
        if line.startswith((" ", "\t")) and lines:
            lines[-1] += line[1:]
        else:
            lines.append(line)
    return lines


def ical_unescape(value: str) -> str:
    """Decode the text escaping used in fields written by ical_escape."""
    return (
        value.replace("\\n", "\n")
        .replace("\\,", ",")
        .replace("\\;", ";")
        .replace("\\\\", "\\")
    )


def read_previous_events(path: Path) -> list[EarningsEvent]:
    """Read events from the last published feed, tolerating a missing first-run file."""
    if not path.exists():
        return []

    events: list[EarningsEvent] = []
    event_fields: dict[str, str] | None = None
    for line in unfold_ical_lines(path.read_text(encoding="utf-8-sig")):
        if line == "BEGIN:VEVENT":
            event_fields = {}
        elif line == "END:VEVENT" and event_fields is not None:
            description = ical_unescape(event_fields.get("DESCRIPTION", ""))
            description_fields = {
                key.strip(): value.strip()
                for key, _, value in (entry.partition(":") for entry in description.splitlines())
                if key and value
            }
            report_date = parse_date(description_fields.get("Report date", ""))
            symbol = description_fields.get("Symbol", "").upper()
            if report_date and symbol:
                rescheduled_to = parse_date(event_fields.get("X-FINANCIAL-REPORT-RESCHEDULED-TO", ""))
                events.append(
                    EarningsEvent(
                        symbol=symbol,
                        name=description_fields.get("Company", symbol),
                        report_date=report_date,
                        fiscal_date_ending=description_fields.get("Fiscal period ending", ""),
                        estimate=description_fields.get("EPS estimate", "").split(" ")[0],
                        rescheduled_to=rescheduled_to,
                    )
                )
            event_fields = None
        elif event_fields is not None and ":" in line:
            key, value = line.split(":", 1)
            # DTSTART;VALUE=DATE is not currently needed because the description
            # preserves the original date in a format shared by this generator.
            event_fields[key] = value
    return events


def same_reporting_period(previous: EarningsEvent, current: EarningsEvent) -> bool:
    """Return whether two provider rows represent the same reporting quarter."""
    if previous.symbol != current.symbol:
        return False
    if previous.fiscal_date_ending and current.fiscal_date_ending:
        return previous.fiscal_date_ending == current.fiscal_date_ending
    return abs((previous.report_date - current.report_date).days) < 31


def retain_rescheduled_events(
    events: list[EarningsEvent], previous_events: Iterable[EarningsEvent], today: date
) -> list[EarningsEvent]:
    """Keep a visible old-date event when a near-term earnings date is revised.

    The provider's current row remains the active earnings event.  The old row is
    retained only through its original date and is labelled with the new date, so
    subscribers can see the revision without a separate notification event.
    """
    retained: dict[str, EarningsEvent] = {event_uid(event): event for event in events}

    for previous in previous_events:
        # no interest in events that have already passed
        if previous.report_date < today:
            continue

        matching_current = [
            event for event in events if same_reporting_period(previous, event)
        ]
        if any(event.report_date == previous.report_date for event in matching_current):
            # The provider still reports this date, so it is an active event, not
            # a revision notice.
            continue

        """rescheduling logic"""
        if previous.rescheduled_to:
            # Carry a previous revision forward, updating its destination if the
            # provider has moved the report date again.
            destination = matching_current[0].report_date if matching_current else previous.rescheduled_to
        elif matching_current:
            destination = matching_current[0].report_date
        else:
            continue

        if abs((destination - previous.report_date).days) >= 31:
            continue

        retained[event_uid(previous)] = EarningsEvent(
            symbol=previous.symbol,
            name=previous.name,
            report_date=previous.report_date,
            fiscal_date_ending=previous.fiscal_date_ending,
            estimate=previous.estimate,
            currency=previous.currency,
            rescheduled_to=destination,
        )

    return sorted(retained.values(), key=lambda event: (event.report_date, event.symbol, event.rescheduled_to is not None))


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
    if event.fiscal_date_ending:
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


def write_calendar(path: Path, contents: str) -> None:
    """Create the output directory if necessary and write the finished calendar."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        file.write(contents)


def main() -> int:
    """Run the pipeline: watchlist -> source data -> events -> .ics file."""
    args = parse_args()
    companies = read_watchlist(Path(args.watchlist))
    source_csv = read_source_csv(args)
    events = parse_events(source_csv, companies)
    previous_events = read_previous_events(Path(args.previous_ics)) if args.previous_ics else []
    events = retain_rescheduled_events(events, previous_events, date.today())
    calendar = build_calendar(events, args.calendar_name)
    write_calendar(Path(args.output), calendar)

    # Report coverage so a successful run does not hide missing provider dates.
    matched_symbols = sorted({event.symbol for event in events})
    missing_symbols = sorted(set(companies) - set(matched_symbols))

    print(f"Wrote {len(events)} events to {args.output}")
    retained_count = sum(event.rescheduled_to is not None for event in events)
    if retained_count:
        print(f"Retained {retained_count} rescheduled event(s) through their original date.")
    if matched_symbols:
        print("Matched symbols: " + ", ".join(matched_symbols))
    if missing_symbols:
        wrapped = textwrap.fill(", ".join(missing_symbols), width=88)
        print("No upcoming report dates found for: " + wrapped)

    return 0


if __name__ == "__main__":
    # Keeps importing this module side-effect free while making it executable.
    sys.exit(main())
