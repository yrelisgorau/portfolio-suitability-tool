"""Unit tests for portfolio_suitability. Run with: python -m unittest -v"""

import tempfile
import unittest
from pathlib import Path

from portfolio_suitability import (
    ASSET_CLASSES,
    PROFILES,
    RiskProfile,
    Status,
    assess_suitability,
    load_portfolios_from_csv,
    main,
    rebalancing_trades,
    report,
    to_weights,
)

BALANCED_TARGET = {"equities": 50, "bonds": 30, "cash": 10, "alternatives": 10}


class TestProfiles(unittest.TestCase):
    def test_all_targets_sum_to_100(self):
        for profile in PROFILES.values():
            self.assertAlmostEqual(sum(profile.target.values()), 100)

    def test_expected_profiles_exist(self):
        for name in ("cautious", "balanced", "growth"):
            self.assertIn(name, PROFILES)

    def test_risk_ordering(self):
        eq = [PROFILES[n].target["equities"] for n in ("cautious", "balanced", "growth", "adventurous")]
        self.assertEqual(eq, sorted(eq))

    def test_invalid_profile_rejected(self):
        with self.assertRaises(ValueError):
            RiskProfile("bad", "", {"equities": 60, "bonds": 30, "cash": 5, "alternatives": 10}, 5)
        with self.assertRaises(ValueError):
            RiskProfile("bad", "", {"equities": 100, "bonds": 0, "cash": 0}, 5)
        with self.assertRaises(ValueError):
            RiskProfile("bad", "", BALANCED_TARGET, 0)


class TestWeights(unittest.TestCase):
    def test_weights_sum_to_100(self):
        w = to_weights({"equities": 30, "bonds": 70})
        self.assertAlmostEqual(sum(w.values()), 100)
        self.assertEqual(w["cash"], 0)

    def test_scale_invariant(self):
        self.assertEqual(to_weights({"equities": 1, "bonds": 1}), to_weights({"equities": 1000, "bonds": 1000}))

    def test_bad_inputs(self):
        with self.assertRaises(ValueError):
            to_weights({"crypto": 10})
        with self.assertRaises(ValueError):
            to_weights({"equities": -5, "bonds": 10})
        with self.assertRaises(ValueError):
            to_weights({"equities": 0})


class TestSuitability(unittest.TestCase):
    def test_on_target_is_suitable(self):
        self.assertTrue(assess_suitability(BALANCED_TARGET, "balanced").suitable)

    def test_exactly_at_tolerance_is_suitable(self):
        edge = {"equities": 55, "bonds": 25, "cash": 10, "alternatives": 10}
        self.assertTrue(assess_suitability(edge, "balanced").suitable)

    def test_just_beyond_tolerance_is_flagged(self):
        over = {"equities": 55.5, "bonds": 24.5, "cash": 10, "alternatives": 10}
        result = assess_suitability(over, "balanced")
        self.assertFalse(result.suitable)
        statuses = {f.asset_class: f.status for f in result.flags}
        self.assertIs(statuses["equities"], Status.OVERWEIGHT)
        self.assertIn(statuses["bonds"], (Status.WITHIN, Status.UNDERWEIGHT))

    def test_breach_directions(self):
        result = assess_suitability({"equities": 70, "bonds": 15, "cash": 5, "alternatives": 10}, "balanced")
        by_class = {f.asset_class: f for f in result.flags}
        self.assertIs(by_class["equities"].status, Status.OVERWEIGHT)
        self.assertIs(by_class["bonds"].status, Status.UNDERWEIGHT)
        self.assertEqual({f.asset_class for f in result.breaches}, {"equities", "bonds"})

    def test_same_portfolio_differs_by_profile(self):
        growthy = {"equities": 70, "bonds": 15, "cash": 5, "alternatives": 10}
        self.assertTrue(assess_suitability(growthy, "growth").suitable)
        self.assertFalse(assess_suitability(growthy, "cautious").suitable)

    def test_profile_name_case_insensitive(self):
        self.assertTrue(assess_suitability(BALANCED_TARGET, "BALANCED").suitable)

    def test_unknown_profile(self):
        with self.assertRaises(ValueError):
            assess_suitability(BALANCED_TARGET, "reckless")

    def test_report_mentions_flags(self):
        text = report(assess_suitability({"equities": 90, "bonds": 10}, "balanced"))
        self.assertIn("NOT SUITABLE", text)
        self.assertIn("FLAG", text)
        self.assertIn("SUITABLE", report(assess_suitability(BALANCED_TARGET, "balanced")))


class TestRebalancing(unittest.TestCase):
    def test_trades_net_to_zero(self):
        holdings = {"equities": 62_000, "bonds": 18_000, "cash": 8_000, "alternatives": 12_000}
        trades = rebalancing_trades(holdings, "balanced")
        self.assertLess(abs(sum(trades.values())), 0.05)

    def test_applying_trades_reaches_target(self):
        holdings = {"equities": 45_000, "bonds": 30_000, "cash": 15_000, "alternatives": 10_000}
        trades = rebalancing_trades(holdings, "growth")
        after = {ac: holdings[ac] + trades[ac] for ac in ASSET_CLASSES}
        self.assertTrue(assess_suitability(after, "growth").suitable)
        for ac, target in PROFILES["growth"].target.items():
            self.assertAlmostEqual(to_weights(after)[ac], target, places=2)

    def test_on_target_needs_no_trades(self):
        trades = rebalancing_trades({k: v * 1000 for k, v in BALANCED_TARGET.items()}, "balanced")
        self.assertTrue(all(abs(t) < 0.01 for t in trades.values()))


class TestCsv(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)

    def _write(self, text: str, name: str = "p.csv") -> Path:
        path = Path(self.dir.name) / name
        path.write_text(text, encoding="utf-8")
        return path

    def test_loads_rows(self):
        path = self._write("client,profile,equities,bonds,cash,alternatives\nA,balanced,50,30,10,10\n")
        rows = load_portfolios_from_csv(path)
        self.assertEqual(rows, [("A", "balanced", BALANCED_TARGET_FLOAT)])

    def test_headers_case_insensitive_and_blank_is_zero(self):
        path = self._write("Client,Profile,Equities,Bonds,Cash,Alternatives\nA,cautious,20,50,25,\n")
        _, _, holdings = load_portfolios_from_csv(path)[0]
        self.assertEqual(holdings["alternatives"], 0.0)

    def test_missing_column(self):
        path = self._write("client,profile,equities,bonds\nA,balanced,50,50\n")
        with self.assertRaisesRegex(ValueError, "missing"):
            load_portfolios_from_csv(path)

    def test_non_numeric_value_reports_line(self):
        path = self._write("client,profile,equities,bonds,cash,alternatives\nA,balanced,abc,30,10,10\n")
        with self.assertRaisesRegex(ValueError, "Line 2"):
            load_portfolios_from_csv(path)

    def test_cli_exit_codes(self):
        ok = self._write("client,profile,equities,bonds,cash,alternatives\nA,balanced,50,30,10,10\n", "ok.csv")
        bad = self._write("client,profile,equities,bonds,cash,alternatives\nA,balanced,90,5,0,5\n", "bad.csv")
        self.assertEqual(main([str(ok)]), 0)
        self.assertEqual(main([str(bad)]), 1)
        self.assertEqual(main([str(Path(self.dir.name) / "nope.csv")]), 2)


BALANCED_TARGET_FLOAT = {k: float(v) for k, v in BALANCED_TARGET.items()}


if __name__ == "__main__":
    unittest.main()
