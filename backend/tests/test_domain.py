"""Pure domain tests: provider parsing and iCalendar rendering (no database)."""

from datetime import date

from app.domain import Company, EarningsEvent, build_calendar, event_uid, parse_events

HEADER = "symbol,name,reportDate,fiscalDateEnding,estimate,currency,timeOfTheDay"


def test_parse_events_requires_a_valid_fiscal_period_ending() -> None:
    events = parse_events(
        "\n".join(
            [
                HEADER,
                "NVDA,NVIDIA,2026-10-29,2026-09-30,1.25,USD,post-market",
                "MSFT,MICROSOFT,2026-10-28,,3.10,USD,after-hours",
                "AAPL,APPLE,2026-10-30,N/A,1.50,USD,after-hours",
            ]
        ),
        {
            "NVDA": Company(symbol="NVDA", name="NVIDIA"),
            "MSFT": Company(symbol="MSFT", name="Microsoft"),
            "AAPL": Company(symbol="AAPL", name="Apple"),
        },
    )
    assert [event.symbol for event in events] == ["NVDA"]


def test_build_calendar_labels_rescheduled_events() -> None:
    notice = EarningsEvent(
        symbol="NVDA",
        name="NVIDIA",
        report_date=date(2026, 10, 28),
        fiscal_date_ending="2026-09-30",
        rescheduled_to=date(2026, 10, 29),
    )
    active = EarningsEvent(
        symbol="NVDA", name="NVIDIA", report_date=date(2026, 10, 29), fiscal_date_ending="2026-09-30"
    )
    ics = build_calendar([notice, active], "Test calendar")
    assert "NVDA financial report — rescheduled to Oct 29" in ics
    assert ics.count("BEGIN:VEVENT") == 2
    assert event_uid(notice) != event_uid(active)
