"""Regression tests for preserving visible earnings-date revisions."""

from datetime import date
from pathlib import Path
import sys
import tempfile
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from generate_financial_reports_calendar import (  # noqa: E402
    EarningsEvent,
    build_calendar,
    read_previous_events,
    retain_rescheduled_events,
)


class RescheduledEventsTests(unittest.TestCase):
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
