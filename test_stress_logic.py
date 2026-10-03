"""Offline regression tests for causal features and market-session outcomes."""
from __future__ import annotations

import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

import eval as evaluation
import stress


class StressLogicTests(unittest.TestCase):
    def test_future_cannot_change_breadth_feature(self) -> None:
        idx = pd.bdate_range("2010-01-01", periods=700)
        rng = np.random.default_rng(17)
        px = pd.DataFrame({t: 100 * np.exp(np.cumsum(rng.normal(0, .01, len(idx))))
                           for t in stress.TICKERS}, index=idx)
        br = pd.DataFrame({"s5fi": rng.uniform(10, 90, len(idx)),
                           "s5th": rng.uniform(10, 90, len(idx))}, index=idx)
        prefix = stress.candidates(px.iloc[:500], br.iloc[:500])["breadth_divergence"]
        whole = stress.candidates(px, br)["breadth_divergence"].iloc[:500]
        pd.testing.assert_series_equal(prefix, whole)
        expected = stress.pct_rank(px["^GSPC"].pct_change(20, fill_method=None), 252) - stress.pct_rank(br["s5th"], 252)
        pd.testing.assert_series_equal(whole, expected.iloc[:500], check_names=False)

    def test_event_boundary_and_incomplete_tail(self) -> None:
        idx = pd.bdate_range("2020-01-01", periods=50)
        px = pd.Series(100.0, index=idx)
        px.iloc[20] = 94
        y = stress.event_labels(px)
        self.assertTrue(y.iloc[0])
        self.assertFalse(y.iloc[20])  # today's fall is excluded
        self.assertTrue(y.iloc[-20:].isna().all())
        px.iloc[20] = 100
        px.iloc[21] = 94
        self.assertFalse(stress.event_labels(px).iloc[0])

    def test_missing_close_is_unknown(self) -> None:
        px = pd.Series(100.0, index=pd.bdate_range("2020-01-01", periods=60))
        px.iloc[10] = np.nan
        y = stress.event_labels(px)
        self.assertTrue(pd.isna(y.iloc[0]))
        self.assertTrue(pd.isna(y.iloc[10]))
        self.assertFalse(y.iloc[11])

    def test_filtered_scores_do_not_extend_horizon(self) -> None:
        px = pd.Series(100.0, index=pd.bdate_range("2020-01-01", periods=100))
        px.iloc[25] = 90
        scores = pd.Series(90.0, index=px.index[::2])
        table = stress.event_rate(px, scores)
        expected = stress.event_labels(px).reindex(scores.index).dropna()
        self.assertEqual(table.loc["all days", "days"], len(expected))
        self.assertAlmostEqual(table.loc["all days", "rate"], expected.mean() * 100)

    def test_constant_calibration_and_unknown_outcomes(self) -> None:
        scores = pd.Series([50.0] * 4)
        labels = pd.Series([True, False, pd.NA, pd.NA], dtype="boolean")
        curve = stress.calibration(scores, labels)
        self.assertEqual(curve["days"].sum(), 2)
        self.assertEqual(stress.chance(50, curve), 50)
        with self.assertRaises(ValueError):
            stress.calibration(scores, pd.Series(pd.NA, index=scores.index, dtype="boolean"))

    def test_low_coverage_has_no_score(self) -> None:
        frame = pd.DataFrame({"a": [90.0], "b": [np.nan], "c": [np.nan], "d": [np.nan]})
        self.assertTrue(pd.isna(stress.score(frame, list(frame))["MSS"].iloc[0]))

    def test_eval_offline_preserves_calendar_and_unknown_tail(self) -> None:
        px = pd.Series(100.0, index=pd.bdate_range("2020-01-01", periods=70))
        px.iloc[25] = 90
        with patch.object(evaluation.pd, "read_csv", return_value=px.to_frame()):
            got = evaluation.hits(px.index[::2], offline=True)
        pd.testing.assert_series_equal(got, stress.event_labels(px).reindex(px.index[::2]), check_names=False)

    def test_historical_export_uses_each_year_and_leaves_gaps_unknown(self) -> None:
        idx = pd.bdate_range("2020-01-01", periods=10)
        retrospective = stress.score(pd.DataFrame({"latest": 95.0}, index=idx), ["latest"])
        oos = pd.Series(20.0, index=idx[2:].delete(3))
        got = stress.historical_scores(retrospective, oos)
        pd.testing.assert_series_equal(got.loc[oos.index, "MSS"], oos, check_names=False)
        self.assertTrue(pd.isna(got.loc[idx[5], "MSS"]))
        self.assertEqual(got.loc[idx[0], "MSS"], 95)
        self.assertEqual(got.loc[idx[-1], "regime"], "NORMAL")


if __name__ == "__main__":
    unittest.main()
