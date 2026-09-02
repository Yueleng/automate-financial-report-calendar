"""Regression tests for preserving visible earnings-date revisions."""

from datetime import date
from pathlib import Path
import sys
import tempfile
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from generate_financial_reports_calendar import (  # noqa: E402
    EarningsEvent,
    Company,
    build_calendar,
    parse_events,
    read_previous_events,
    retain_rescheduled_events,
)


class RescheduledEventsTests(unittest.TestCase):
    def test_parse_events_requires_a_valid_fiscal_period_ending(self) -> None:
        events = parse_events(
            "\n".join(
                [
                    "symbol,name,reportDate,fiscalDateEnding,estimate,currency,timeOfTheDay",
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

        self.assertEqual([event.symbol for event in events], ["NVDA"])

    def test_ignores_previous_events_without_a_fiscal_period(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "previous.ics"
            path.write_text(
                "\n".join(
                    [
                        "BEGIN:VCALENDAR",
                        "BEGIN:VEVENT",
                        "DESCRIPTION:Company: NVIDIA\\nSymbol: NVDA\\nReport date: 2026-10-28",
                        "END:VEVENT",
                        "END:VCALENDAR",
                    ]
                ),
                encoding="utf-8",
            )

            loaded = read_previous_events(path)

        self.assertEqual(loaded, [])

    def test_keeps_old_date_and_adds_current_date_for_a_quarter_revision(self) -> None:
        previous = EarningsEvent(
            symbol="NVDA",
            name="NVIDIA",
            report_date=date(2026, 10, 28),
            fiscal_date_ending="2026-09-30",
        )
        current = EarningsEvent(
            symbol="NVDA",
            name="NVIDIA",
            report_date=date(2026, 10, 29),
            fiscal_date_ending="2026-09-30",
        )

        retained = retain_rescheduled_events([current], [previous], date(2026, 10, 1))

        self.assertEqual([event.report_date for event in retained], [date(2026, 10, 28), date(2026, 10, 29)])
        self.assertEqual(retained[0].rescheduled_to, date(2026, 10, 29))
        self.assertIsNone(retained[1].rescheduled_to)
        self.assertIn("rescheduled to Oct 29", build_calendar(retained, "Test calendar"))

    def test_drops_the_reschedule_notice_after_its_original_date(self) -> None:
        previous = EarningsEvent(
            symbol="NVDA",
            name="NVIDIA",
            report_date=date(2026, 10, 28),
            fiscal_date_ending="2026-09-30",
        )
        current = EarningsEvent(
            symbol="NVDA",
            name="NVIDIA",
            report_date=date(2026, 10, 29),
            fiscal_date_ending="2026-09-30",
        )

        retained = retain_rescheduled_events([current], [previous], date(2026, 10, 29))

        self.assertEqual(retained, [current])

    def test_preserves_first_revision_notice_when_report_is_rescheduled_again(self) -> None:
        previous = EarningsEvent(
            symbol="NVDA",
            name="NVIDIA",
            report_date=date(2026, 10, 28),
            fiscal_date_ending="2026-09-30",
            rescheduled_to=date(2026, 10, 29),
        )
        current = EarningsEvent(
            symbol="NVDA",
            name="NVIDIA",
            report_date=date(2026, 10, 30),
            fiscal_date_ending="2026-09-30",
        )

        retained = retain_rescheduled_events([current], [previous], date(2026, 10, 1))

        self.assertEqual(retained, [previous, current])

    def test_reads_rescheduled_event_back_from_prior_feed(self) -> None:
        previous = EarningsEvent(
            symbol="NVDA",
            name="NVIDIA",
            report_date=date(2026, 10, 28),
            fiscal_date_ending="2026-09-30",
            rescheduled_to=date(2026, 10, 29),
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "previous.ics"
            path.write_text(build_calendar([previous], "Test calendar"), encoding="utf-8")
            loaded = read_previous_events(path)

        self.assertEqual(loaded, [previous])


if __name__ == "__main__":
    unittest.main()
