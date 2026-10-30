import importlib.util
import os
from datetime import datetime, timezone
from pathlib import Path
import unittest


os.environ.setdefault("GMAIL_ADDRESS", "sender@example.test")
os.environ.setdefault("GMAIL_APP_PASSWORD", "not-used-in-tests")
os.environ.setdefault("REPORT_RECIPIENT", "owner@example.test")

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "send_email.py"
SPEC = importlib.util.spec_from_file_location("market_email", MODULE_PATH)
market_email = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(market_email)

DASHBOARD_PATH = Path(__file__).resolve().parents[1] / "scripts" / "build_dashboard.py"
DASHBOARD_SPEC = importlib.util.spec_from_file_location("market_dashboard", DASHBOARD_PATH)
market_dashboard = importlib.util.module_from_spec(DASHBOARD_SPEC)
DASHBOARD_SPEC.loader.exec_module(market_dashboard)


def market_payload(rent=1500, dom=30, listings=40, mom=1.0):
    return {
        "aggregate": {
            "averageRent": {"current": rent, "changes": {"mom": {"pct_change": mom}}},
            "averageDaysOnMarket": {"current": dom, "changes": {"mom": {"pct_change": 0.5}}},
            "totalListings": {"current": listings},
        },
        "market_conditions": {"temperature": "neutral", "temperature_label": "Mixed but Balanced"},
    }


class ReportEmailTests(unittest.TestCase):
    def test_recipients_keep_owner_and_add_automation_mailbox(self):
        self.assertEqual(
            market_email.report_recipients("owner@example.test"),
            ["owner@example.test", "japm.workorder.reports@gmail.com"],
        )
        self.assertEqual(
            market_email.report_recipients("japm.workorder.reports@gmail.com"),
            ["japm.workorder.reports@gmail.com"],
        )

    def test_status_flags_missing_prior_month_and_unavailable_analysis(self):
        trends = {
            "as_of": "2026-10",
            "markets": {key: market_payload(mom=None) for key in market_email.MARKETS},
        }
        insights = {
            "regional": "Regional analysis unavailable this month.",
            "markets": {
                key: "Analysis unavailable this month." if key != "liberty" else "Hidden from dashboard due to low confidence."
                for key in market_email.MARKETS
            },
        }
        history = [{
            "month": "2026-10",
            "fetched_at": "2026-10-01T18:20:58+00:00",
            "data_sources": ["rentcast", "apartment_list", "zillow_research"],
        }]

        status = market_email.collect_report_status(
            trends,
            insights,
            history,
            now=datetime(2026, 10, 2, tzinfo=timezone.utc),
        )

        self.assertFalse(status["analysis_complete"])
        self.assertTrue(any("prior month (2026-09)" in note for note in status["warnings"]))
        self.assertTrue(any("AI narrative unavailable" in note for note in status["errors"]))
        self.assertIn("REPORT STATUS: REVIEW NEEDED", market_email.report_status_html(status))

    def test_status_is_ready_for_fresh_complete_report(self):
        trends = {
            "as_of": "2026-11",
            "markets": {key: market_payload() for key in market_email.MARKETS},
        }
        insights = {
            "regional": "Current market analysis.",
            "markets": {key: "Current market analysis." for key in market_email.MARKETS},
            "analysis_status": {
                "regional": {"status": "ok"},
                "markets": {key: {"status": "ok"} for key in market_email.MARKETS},
            },
        }
        history = [
            {"month": "2026-10", "fetched_at": "2026-10-01T12:00:00+00:00", "data_sources": ["rentcast"]},
            {"month": "2026-11", "fetched_at": "2026-11-01T12:00:00+00:00", "data_sources": ["rentcast"]},
        ]

        status = market_email.collect_report_status(
            trends,
            insights,
            history,
            now=datetime(2026, 11, 2, tzinfo=timezone.utc),
        )

        self.assertTrue(status["analysis_complete"])
        self.assertEqual(status["errors"], [])
        self.assertEqual(status["warnings"], [])
        self.assertIn("REPORT STATUS: READY", market_email.report_status_html(status))

    def test_dashboard_handles_null_market_in_partial_history(self):
        history = [{"markets": {"greenville": None}}]
        trends = {"markets": {"greenville": market_payload()}}
        confidence = market_dashboard.group_confidence(
            ["greenville"], history, trends, {"markets": {}},
        )
        self.assertIn("score", confidence)
        self.assertEqual(market_dashboard.recent_history_market(history, "greenville"), {})


if __name__ == "__main__":
    unittest.main()
