import unittest

import numpy as np
import pandas as pd

from signals import (
    calculate_us_orion_score,
    evaluate_us_entry_permission,
    run_us_orion_walkforward_validation,
)


def _frame(values, index):
    return pd.DataFrame({"Close": values}, index=index)


def build_macro_data(falling_knife=False):
    market_index = pd.bdate_range(end=pd.Timestamp.now().normalize(), periods=90)
    x = np.arange(len(market_index), dtype=float)
    spy = 500 + x * 0.45 + np.sin(x / 3) * 2
    if falling_knife:
        spy[-1] = spy[-2] * 0.94
    fred_index = pd.date_range(end=pd.Timestamp.now().normalize(), periods=90)
    fred = pd.DataFrame(
        {
            "WALCL": np.linspace(6_650_000, 6_720_000, 90),
            "WTREGEN": np.linspace(820_000, 780_000, 90),
            "RRPONTSYD": np.linspace(4.0, 1.5, 90),
            "BAMLH0A0HYM2": np.linspace(3.5, 3.2, 90),
        },
        index=fred_index,
    )
    return {
        "spy_10y": _frame(spy, market_index),
        "rsp_10y": _frame(spy * np.linspace(0.99, 1.02, 90), market_index),
        "soxx_10y": _frame(spy * np.linspace(0.95, 1.06, 90), market_index),
        "vix_10y": _frame(np.linspace(17, 15, 90), market_index),
        "vix3m_10y": _frame(np.linspace(19, 18, 90), market_index),
        "tnx_10y": _frame(np.linspace(4.4, 4.3, 90), market_index),
        "tyx_10y": _frame(np.linspace(4.9, 4.8, 90), market_index),
        "irx_10y": _frame(np.linspace(4.5, 4.1, 90), market_index),
        "dxy_10y": _frame(np.linspace(104, 102, 90), market_index),
        "usdjpy_10y": _frame(np.linspace(155, 153, 90), market_index),
        "btc_10y": _frame(np.linspace(90_000, 100_000, 90), market_index),
        "hyg_10y": _frame(np.linspace(78, 82, 90), market_index),
        "ief_10y": _frame(np.linspace(94, 94.5, 90), market_index),
        "fred_macro": fred,
        "fred_as_of": {name: fred_index[-1].strftime("%Y-%m-%d") for name in fred.columns},
    }


class UsOrionTests(unittest.TestCase):
    def test_rrp_billions_are_converted_to_millions(self):
        macro = build_macro_data()
        _, _, _, _, metrics = calculate_us_orion_score(macro)
        fred = macro["fred_macro"].iloc[-1]
        expected_b = (fred["WALCL"] - fred["WTREGEN"] - fred["RRPONTSYD"] * 1000) / 1000
        self.assertAlmostEqual(metrics["net_liquidity"], expected_b, places=6)

    def test_soxx_relative_strength_is_scored(self):
        _, _, _, _, metrics = calculate_us_orion_score(build_macro_data())
        self.assertIn("soxx_spy_20d_gap", metrics)
        self.assertGreater(metrics["soxx_spy_20d_gap"], 0)

    def test_missing_required_series_blocks_clear(self):
        macro = build_macro_data()
        del macro["vix_10y"]
        _, phase, _, _, metrics = calculate_us_orion_score(macro)
        self.assertEqual(phase, "DATA_ERROR")
        self.assertFalse(metrics["data_quality"]["valid"])

    def test_falling_knife_vetoes_entry(self):
        macro = build_macro_data(falling_knife=True)
        _, _, _, _, metrics = calculate_us_orion_score(macro)
        state, checks, _ = evaluate_us_entry_permission(
            macro, "CLEAR", metrics, flow_score=20, flow_is_stale=False
        )
        self.assertEqual(state, "FALLING_KNIFE_VETO")
        self.assertFalse(checks["falling_knife_released"])

    def test_fresh_confirmed_market_allows_only_starter_stage(self):
        macro = build_macro_data()
        _, _, _, _, metrics = calculate_us_orion_score(macro)
        state, checks, reasons = evaluate_us_entry_permission(
            macro, "CLEAR", metrics, flow_score=20, flow_is_stale=False
        )
        self.assertEqual(state, "STARTER_GO", reasons)
        self.assertTrue(all(checks.values()))

    def test_stale_flow_keeps_entry_waiting(self):
        macro = build_macro_data()
        _, _, _, _, metrics = calculate_us_orion_score(macro)
        state, _, reasons = evaluate_us_entry_permission(
            macro, "CLEAR", metrics, flow_score=20, flow_is_stale=True
        )
        self.assertEqual(state, "ENTRY_WAIT")
        self.assertIn("수급 프록시 최신", reasons)

    def test_walkforward_uses_next_day_returns_and_costs(self):
        result = run_us_orion_walkforward_validation(
            build_macro_data(), transaction_cost_bps=5, min_history=60
        )
        self.assertTrue(result["usable"])
        self.assertGreater(result["observations"], 0)
        self.assertEqual(result["transaction_cost_bps"], 5.0)
        self.assertGreaterEqual(result["exposure"], 0.0)
        self.assertLessEqual(result["exposure"], 1.0)


if __name__ == "__main__":
    unittest.main()
