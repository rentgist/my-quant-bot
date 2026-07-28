import unittest

import numpy as np
import pandas as pd

from regime_playbook import (
    build_holding_action,
    build_market_features,
    build_regime_action_plan,
    classify_market_regime,
    run_regime_backtest,
)


def market_frame(returns: np.ndarray, start: str = "2018-01-01") -> pd.DataFrame:
    dates = pd.bdate_range(start, periods=len(returns))
    close = 100 * np.cumprod(1 + returns)
    return pd.DataFrame({"Open": close, "Close": close}, index=dates)


class RegimeClassificationTests(unittest.TestCase):
    def test_crash_turns_on_panic_freeze(self):
        returns = np.concatenate([np.full(600, 0.0004), np.array([-0.06])])
        regime = classify_market_regime(market_frame(returns), bottom_score=80)
        self.assertEqual(regime["code"], "CRASH")
        self.assertTrue(regime["panic_freeze"])

    def test_smooth_rising_market_is_uptrend(self):
        regime = classify_market_regime(
            market_frame(np.full(700, 0.0007)),
            bottom_score=10,
        )
        self.assertEqual(regime["code"], "UPTREND")
        self.assertFalse(regime["panic_freeze"])

    def test_features_have_no_lookahead_when_future_is_appended(self):
        rng = np.random.default_rng(7)
        original = market_frame(rng.normal(0.0002, 0.01, 650))
        extended = pd.concat(
            [
                original,
                market_frame(
                    rng.normal(0.0, 0.03, 20),
                    start=str((original.index[-1] + pd.offsets.BDay()).date()),
                ).set_axis(
                    pd.bdate_range(original.index[-1] + pd.offsets.BDay(), periods=20)
                ),
            ]
        )
        before = build_market_features(original).iloc[-1]
        same_date = build_market_features(extended).loc[original.index[-1]]
        self.assertAlmostEqual(before["HV20"], same_date["HV20"])
        self.assertAlmostEqual(before["MA120"], same_date["MA120"])


class AccountActionTests(unittest.TestCase):
    def test_panic_does_not_force_seventy_percent_equity_to_twenty(self):
        regime = {
            "status": "ok",
            "code": "CRASH",
            "panic_freeze": True,
            "message": "panic",
        }
        action = build_regime_action_plan(5000, 3500, regime)
        self.assertEqual(action["action"], "PANIC_FREEZE")
        self.assertEqual(action["amount"], 0)
        self.assertAlmostEqual(action["current_equity_weight"], 0.70)

    def test_fifty_percent_equity_is_inside_crash_band(self):
        regime = {
            "status": "ok",
            "code": "CRASH",
            "panic_freeze": False,
            "message": "downtrend",
        }
        action = build_regime_action_plan(5000, 2500, regime)
        self.assertEqual(action["action"], "HOLD")
        self.assertEqual(action["amount"], 0)

    def test_confirmed_downtrend_reduction_is_capped_at_five_percent(self):
        regime = {
            "status": "ok",
            "code": "CRASH",
            "panic_freeze": False,
            "message": "downtrend",
        }
        action = build_regime_action_plan(5000, 4000, regime)
        self.assertEqual(action["action"], "REDUCE")
        self.assertEqual(action["amount"], 250)


class HoldingActionTests(unittest.TestCase):
    def test_panic_freezes_technical_sell(self):
        action = build_holding_action(
            {"Price": 70, "MA20": 85, "MA60": 90, "RSI_14": 25},
            {"code": "CRASH", "panic_freeze": True},
            holding_value=1000,
            fundamental_score=1,
            pnl_pct=-30,
        )
        self.assertEqual(action["label"], "매도 동결")
        self.assertEqual(action["sell_fraction"], 0)

    def test_weak_stock_reduction_is_partial_and_amount_is_explicit(self):
        action = build_holding_action(
            {"Price": 70, "MA20": 80, "MA60": 90, "RSI_14": 45},
            {"code": "CRASH", "panic_freeze": False},
            holding_value=800,
            fundamental_score=1,
            pnl_pct=-20,
        )
        self.assertEqual(action["label"], "25% 축소 검토")
        self.assertEqual(action["sell_value"], 200)


class RegimeBacktestTests(unittest.TestCase):
    def test_backtest_is_long_only_and_returns_holdout_metrics(self):
        rng = np.random.default_rng(42)
        returns = np.concatenate(
            [
                rng.normal(0.0005, 0.007, 700),
                rng.normal(-0.0007, 0.025, 160),
                rng.normal(0.0004, 0.009, 300),
            ]
        )
        result = run_regime_backtest(market_frame(returns))
        self.assertEqual(result["status"], "ok")
        self.assertGreaterEqual(result["latest_weight"], 0)
        self.assertLessEqual(result["latest_weight"], 1)
        self.assertIn("strategy_mdd", result["holdout_metrics"])


if __name__ == "__main__":
    unittest.main()
