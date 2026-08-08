import unittest

import numpy as np
import pandas as pd

from signals import (
    calculate_us_orion_score,
    evaluate_us_entry_permission,
    get_us_trigger_display,
    run_us_orion_walkforward_validation,
)


def _frame(values, index, with_ohlcv=False):
    frame = pd.DataFrame({"Close": values}, index=index)
    if with_ohlcv:
        frame["Open"] = frame["Close"] * 0.999
        frame["Low"] = frame["Close"] * 0.995
        frame["Volume"] = np.linspace(90_000_000, 110_000_000, len(index))
    return frame


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
        "spy_10y": _frame(spy, market_index, with_ohlcv=True),
        "qqq_10y": _frame(spy * np.linspace(0.98, 1.04, 90), market_index, with_ohlcv=True),
        "rsp_10y": _frame(spy * np.linspace(0.99, 1.02, 90), market_index),
        "soxx_10y": _frame(spy * np.linspace(0.95, 1.06, 90), market_index, with_ohlcv=True),
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
            macro, "CLEAR", metrics, flow_score=20, flow_is_stale=False, environment_score=70
        )
        self.assertEqual(state, "FALLING_KNIFE_VETO")
        self.assertFalse(checks["falling_knife_released"])

    def test_fresh_confirmed_market_allows_ten_percent_starter(self):
        macro = build_macro_data()
        _, _, _, _, metrics = calculate_us_orion_score(macro)
        state, checks, reasons = evaluate_us_entry_permission(
            macro, "CLEAR", metrics, flow_score=20, flow_is_stale=False, environment_score=70
        )
        self.assertEqual(state, "STARTER_GO_10", reasons)
        self.assertTrue(all(checks.values()))

    def test_one_missing_soft_confirmation_allows_five_percent(self):
        macro = build_macro_data()
        _, _, _, _, metrics = calculate_us_orion_score(macro)
        state, _, reasons = evaluate_us_entry_permission(
            macro, "CLEAR", metrics, flow_score=20, flow_is_stale=True, environment_score=70
        )
        self.assertEqual(state, "STARTER_GO_5")
        self.assertIn("가격·거래량 상승 확인이 부족함", reasons)

    def test_environment_below_sixty_waits(self):
        macro = build_macro_data()
        _, _, _, _, metrics = calculate_us_orion_score(macro)
        state, _, reasons = evaluate_us_entry_permission(
            macro, "CAUTION", metrics, flow_score=20, flow_is_stale=False, environment_score=59
        )
        self.assertEqual(state, "ENTRY_WAIT")
        self.assertIn("환경점수 60점 미만", reasons)

    def test_clear_credit_stress_is_a_hard_veto(self):
        macro = build_macro_data()
        macro["fred_macro"].iloc[-1, macro["fred_macro"].columns.get_loc("BAMLH0A0HYM2")] = 6.0
        _, _, _, _, metrics = calculate_us_orion_score(macro)
        state, checks, _ = evaluate_us_entry_permission(
            macro, "CLEAR", metrics, flow_score=20, flow_is_stale=False, environment_score=70
        )
        self.assertEqual(state, "CREDIT_STRESS_VETO")
        self.assertFalse(checks["credit_stress_absent"])

    def test_walkforward_uses_entry_events_without_forced_wait_exit(self):
        result = run_us_orion_walkforward_validation(
            build_macro_data(), transaction_cost_bps=5, min_history=60
        )
        self.assertTrue(result["usable"])
        self.assertGreater(result["observations"], 0)
        self.assertEqual(result["method"], "entry_event_next_open_no_forced_exit_on_wait")
        self.assertEqual(result["transaction_cost_bps_each_way"], 5.0)
        self.assertIn("starter_any", result["signals"])
        self.assertNotIn("exposure", result)

    def test_diagnostic_icons_match_direction(self):
        self.assertEqual(get_us_trigger_display("연준 유동성 프록시 4주 변화 -25.0B")[0], "🔴")
        self.assertEqual(get_us_trigger_display("RSP-SPY 20일 상대수익률 +1.2%p")[0], "🟢")
        self.assertEqual(get_us_trigger_display("30년물 5.21%로 장기 할인율 부담")[0], "🔴")


if __name__ == "__main__":
    unittest.main()
