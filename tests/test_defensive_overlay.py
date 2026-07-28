import unittest

import numpy as np
import pandas as pd

from defensive_overlay import (
    build_defensive_action_plan,
    build_defensive_features,
    current_defensive_state,
    run_defensive_backtest,
)


def market_frame(returns: np.ndarray, start: str = "2018-01-01") -> pd.DataFrame:
    dates = pd.bdate_range(start, periods=len(returns))
    close = 100 * np.cumprod(1 + returns)
    open_price = close * (1 + np.sin(np.arange(len(close))) * 0.0005)
    return pd.DataFrame({"Open": open_price, "Close": close}, index=dates)


class DefensiveFeatureTests(unittest.TestCase):
    def test_high_volatility_and_broken_trend_reduce_target_without_leverage(self):
        rng = np.random.default_rng(42)
        calm = rng.normal(0.0004, 0.006, 650)
        stressed = rng.normal(-0.0015, 0.035, 80)
        features = build_defensive_features(
            market_frame(np.concatenate([calm, stressed])),
            target_volatility=0.12,
            trend_days=200,
            defensive_cap=0.55,
        )
        latest = features.iloc[-1]
        self.assertLessEqual(latest["RawTargetWeight"], 0.55)
        self.assertGreaterEqual(latest["EquityWeight"], 0.20)
        self.assertLessEqual(latest["EquityWeight"], 1.00)

    def test_backtest_uses_next_open_and_reduces_crash_drawdown(self):
        rng = np.random.default_rng(7)
        rising = rng.normal(0.0005, 0.007, 500)
        crash = np.full(90, -0.012)
        recovery = rng.normal(0.0006, 0.009, 220)
        result = run_defensive_backtest(
            market_frame(np.concatenate([rising, crash, recovery])),
            target_volatility=0.12,
            trend_days=120,
            defensive_cap=0.40,
            rebalance_days=5,
            transaction_cost_bps=15,
        )
        self.assertEqual(result["status"], "ok")
        self.assertGreater(result["metrics"]["mdd_improvement"], 0)
        self.assertGreater(result["metrics"]["volatility_reduction"], 0)
        self.assertIn("안전 방어조합", result["equity_curve"].columns)


class DefensiveActionTests(unittest.TestCase):
    def test_panic_freeze_blocks_low_point_sale(self):
        state = {
            "status": "ok",
            "target_equity_weight": 0.30,
            "panic_freeze": True,
            "reentry_stage": 0,
            "reentry_label": "바닥 확인 전 — 새 매수 대기",
        }
        action = build_defensive_action_plan(
            total_assets=5000,
            current_equity_amount=3500,
            state=state,
            validation_passed=True,
        )
        self.assertEqual(action["action"], "PANIC_FREEZE")
        self.assertEqual(action["amount"], 0)

    def test_normal_reduction_is_capped_at_ten_percent_of_assets(self):
        state = {
            "status": "ok",
            "target_equity_weight": 0.30,
            "panic_freeze": False,
            "reentry_stage": 0,
            "reentry_label": "바닥 확인 전 — 새 매수 대기",
        }
        action = build_defensive_action_plan(
            total_assets=5000,
            current_equity_amount=4000,
            state=state,
            validation_passed=True,
        )
        self.assertEqual(action["action"], "REDUCE_EQUITY")
        self.assertEqual(action["amount"], 500)

    def test_reentry_requires_a_confirmed_stage(self):
        state = {
            "status": "ok",
            "target_equity_weight": 0.70,
            "panic_freeze": False,
            "reentry_stage": 0,
            "reentry_label": "바닥 확인 전 — 새 매수 대기",
        }
        action = build_defensive_action_plan(
            total_assets=5000,
            current_equity_amount=2000,
            state=state,
            validation_passed=True,
        )
        self.assertEqual(action["action"], "HOLD")
        self.assertEqual(action["amount"], 0)

    def test_first_reentry_stage_uses_only_ten_percent_of_available_cash(self):
        state = {
            "status": "ok",
            "target_equity_weight": 0.80,
            "panic_freeze": False,
            "reentry_stage": 1,
            "reentry_label": "1차 안정 — 예비현금의 10%까지",
        }
        action = build_defensive_action_plan(
            total_assets=5000,
            current_equity_amount=2000,
            state=state,
            validation_passed=True,
        )
        self.assertEqual(action["action"], "ADD_EQUITY")
        self.assertEqual(action["amount"], 300)

    def test_current_state_has_four_step_reentry_output(self):
        rng = np.random.default_rng(21)
        returns = rng.normal(0.0005, 0.008, 800)
        state = current_defensive_state(market_frame(returns))
        self.assertEqual(state["status"], "ok")
        self.assertIn(state["reentry_stage"], range(5))
        self.assertIn("target_equity_weight", state)


if __name__ == "__main__":
    unittest.main()
