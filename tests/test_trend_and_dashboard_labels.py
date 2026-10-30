import sys
import unittest
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from build_dashboard import GROUPS, dom_comparison_note, missing_prior_snapshot
from calculate_trends import rank_high_confidence_rent_momentum


def market_with_rent_mom(value):
    return {
        "aggregate": {
            "averageRent": {"changes": {"mom": {"pct_change": value}}}
        }
    }


class TrendAndDashboardLabelTests(unittest.TestCase):
    def test_no_rent_rank_is_shown_when_no_market_has_rent_mom(self):
        trends = {
            "markets": {
                "greenville": market_with_rent_mom(None),
                "spartanburg": market_with_rent_mom(None),
            }
        }
        self.assertEqual(rank_high_confidence_rent_momentum(trends), (None, None))

    def test_rent_rank_uses_only_available_high_confidence_comparisons(self):
        trends = {
            "markets": {
                "greenville": market_with_rent_mom(1.2),
                "spartanburg": market_with_rent_mom(-0.4),
            }
        }
        self.assertEqual(
            rank_high_confidence_rent_momentum(trends),
            ("greenville", "spartanburg"),
        )

    def test_dashboard_explains_missing_snapshot_with_audited_dom_comparison(self):
        history = [{"month": "2026-08"}, {"month": "2026-10"}]
        self.assertEqual(missing_prior_snapshot(history), "September 2026")
        self.assertIn("RentCast September 2026 historical audit", dom_comparison_note(history))

    def test_directional_liberty_row_is_visible_with_other_markets(self):
        self.assertIn("liberty", GROUPS["other"]["markets"])


if __name__ == "__main__":
    unittest.main()
