import unittest

import numpy as np
import pandas as pd

from hedging import (
    build_plain_action_plan,
    calculate_beta_hedge_size,
    evaluate_hedge_state,
    run_hedge_backtest,
)


class HedgePolicyTests(unittest.TestCase):
    def test_tactical_entry_is_blocked_during_rebound_risk(self):
        decision = evaluate_hedge_state(
            horizon_key="tactical",
            position_status="none",
            entry_score=90,
            exit_score=20,
            rsi=31.0,
            foreign_futures=5000,
            data_quality="live",
        )
        self.assertEqual(decision.action, "WAIT_REVERSAL")
        self.assertFalse(decision.allow_new_entry)

    def test_existing_inverse_is_reduced_on_exit_signal(self):
        decision = evaluate_hedge_state(
            horizon_key="tactical",
            position_status="inverse2x",
            entry_score=80,
            exit_score=45,
            rsi=38.0,
            foreign_futures=-2000,
            holding_days=1,
            data_quality="live",
        )
        self.assertEqual(decision.action, "REDUCE")

    def test_two_x_is_rejected_for_longer_horizon(self):
        decision = evaluate_hedge_state(
            horizon_key="short",
            position_status="inverse2x",
            entry_score=80,
            exit_score=0,
            rsi=45.0,
            foreign_futures=-3000,
            holding_days=2,
            data_quality="live",
        )
        self.assertEqual(decision.action, "EXIT_2X_HORIZON")

    def test_beta_sizing_respects_horizon_cap(self):
        result = calculate_beta_hedge_size(
            total_assets=100_000_000,
            equity_weight=1.0,
            portfolio_beta=1.2,
            target_coverage=0.5,
            horizon_key="tactical",
        )
        self.assertEqual(result["raw_allocation"], 30_000_000)
        self.assertEqual(result["recommended_allocation"], 10_000_000)
        self.assertAlmostEqual(result["achieved_coverage"], 1 / 6)

    def test_failed_holdout_blocks_new_inverse_entry(self):
        decision = evaluate_hedge_state(
            horizon_key="short",
            position_status="none",
            entry_score=90,
            exit_score=0,
            rsi=45.0,
            foreign_futures=-3000,
            data_quality="live",
            validation_passed=False,
        )
        self.assertEqual(decision.action, "BLOCK_VALIDATION")
        self.assertFalse(decision.allow_new_entry)

    def test_plain_action_plan_turns_reduce_into_amount(self):
        decision = evaluate_hedge_state(
            horizon_key="tactical",
            position_status="inverse2x",
            entry_score=80,
            exit_score=45,
            rsi=38.0,
            foreign_futures=-2000,
            holding_days=1,
            data_quality="live",
        )
        plan = build_plain_action_plan(
            decision=decision,
            position_status="inverse2x",
            holding_amount=1000,
            recommended_allocation=500,
            policy_cap=500,
            entry_score=80,
            entry_threshold=75,
            exit_score=45,
            exit_threshold=35,
        )
        self.assertEqual(plan["amount_value"], "500만원")
        self.assertIn("매도", plan["title"])


class HedgeBacktestTests(unittest.TestCase):
    def test_backtest_uses_historical_inverse_prices(self):
        dates = pd.bdate_range("2020-01-01", periods=420)
        trend = np.linspace(100, 70, len(dates))
        shock = np.sin(np.arange(len(dates)) / 8) * 3
        kospi_close = trend + shock
        kospi_open = kospi_close * 1.001
        inverse1_close = 100 + (100 - kospi_close) * 0.8
        inverse2_close = 100 + (100 - kospi_close) * 1.6
        usdkrw = np.linspace(1100, 1350, len(dates))
        vkospi = 18 + np.maximum(0, 100 - kospi_close) * 0.8

        def frame(close, open_values=None):
            values = close if open_values is None else open_values
            return pd.DataFrame({"Open": values, "Close": close}, index=dates)

        result = run_hedge_backtest(
            kospi_hist=frame(kospi_close, kospi_open),
            vkospi_hist=frame(vkospi),
            usdkrw_hist=frame(usdkrw),
            inverse1x_hist=frame(inverse1_close),
            inverse2x_hist=frame(inverse2_close),
            horizon_key="tactical",
            transaction_cost_bps=10,
        )
        self.assertEqual(result["status"], "ok")
        self.assertIn("hedged_mdd", result["metrics"])
        self.assertGreaterEqual(result["metrics"]["trades"], 0)
        self.assertFalse(result["equity_curve"].empty)

        holdout_start = dates[-80]
        holdout = run_hedge_backtest(
            kospi_hist=frame(kospi_close, kospi_open),
            vkospi_hist=frame(vkospi),
            usdkrw_hist=frame(usdkrw),
            inverse1x_hist=frame(inverse1_close),
            inverse2x_hist=frame(inverse2_close),
            horizon_key="tactical",
            transaction_cost_bps=10,
            entry_threshold=70,
            exit_threshold=45,
            max_holding_days=2,
            evaluation_start=holdout_start,
        )
        self.assertEqual(holdout["status"], "ok")
        self.assertGreaterEqual(
            pd.Timestamp(holdout["metrics"]["evaluation_start"]),
            holdout_start,
        )


if __name__ == "__main__":
    unittest.main()
