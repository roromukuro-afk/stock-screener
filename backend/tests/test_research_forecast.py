import unittest
from datetime import date

from app.services.research_forecast import (
    compute_accuracy_metrics,
    normalize_yahoo_symbol,
    split_factor_between,
    target_date_for_horizon,
)


class ResearchForecastTest(unittest.TestCase):
    def test_target_dates_from_smfg_analysis_date(self):
        base = date(2026, 8, 20)
        self.assertEqual(target_date_for_horizon(base, "1w"), date(2026, 8, 27))
        self.assertEqual(target_date_for_horizon(base, "1m"), date(2026, 9, 20))
        self.assertEqual(target_date_for_horizon(base, "3m"), date(2026, 11, 20))
        self.assertEqual(target_date_for_horizon(base, "6m"), date(2027, 2, 20))
        self.assertEqual(target_date_for_horizon(base, "1y"), date(2027, 8, 20))

    def test_month_end_is_clamped(self):
        self.assertEqual(target_date_for_horizon(date(2026, 1, 31), "1m"), date(2026, 2, 28))

    def test_japanese_symbol_is_normalized_for_yahoo(self):
        self.assertEqual(normalize_yahoo_symbol("8316", "JP"), "8316.T")
        self.assertEqual(normalize_yahoo_symbol("8316.T", "JP"), "8316.T")

    def test_split_factor_only_uses_events_after_analysis_and_through_check_date(self):
        events = [
            {"date": "2026-08-01", "ratio": 3.0},
            {"date": "2026-10-01", "ratio": 2.0},
            {"date": "2027-10-01", "ratio": 2.0},
        ]
        self.assertEqual(split_factor_between(events, "2026-08-20", "2027-08-20"), 2.0)

    def test_accuracy_metrics_use_comparable_price_basis(self):
        metrics = compute_accuracy_metrics(
            base_price=100.0,
            predicted_return_pct=10.0,
            predicted_price=110.0,
            actual_price_comparable=112.0,
        )
        self.assertAlmostEqual(metrics["actual_return_pct"], 12.0)
        self.assertAlmostEqual(metrics["price_error"], 2.0)
        self.assertAlmostEqual(metrics["absolute_price_error"], 2.0)
        self.assertAlmostEqual(metrics["return_error_pct_points"], 2.0)
        self.assertTrue(metrics["direction_match"])

    def test_direction_miss_is_detected(self):
        metrics = compute_accuracy_metrics(
            base_price=100.0,
            predicted_return_pct=5.0,
            predicted_price=105.0,
            actual_price_comparable=95.0,
        )
        self.assertFalse(metrics["direction_match"])
        self.assertAlmostEqual(metrics["actual_return_pct"], -5.0)


if __name__ == "__main__":
    unittest.main()
