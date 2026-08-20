import ast
import os
import tempfile
import unittest
from pathlib import Path

import pandas as pd


def load_signal_functions():
    signals_path = Path(__file__).resolve().parents[1] / "signals.py"
    module = ast.parse(signals_path.read_text(encoding="utf-8"))
    required_names = {
        "load_state_from_github",
        "save_state_to_github",
        "calculate_cashflow_signal",
        "evaluate_market_execution_quality",
        "calculate_regime_classification",
    }
    function_nodes = [
        node for node in module.body
        if isinstance(node, ast.FunctionDef) and node.name in required_names
    ]
    isolated_module = ast.Module(body=function_nodes, type_ignores=[])
    namespace = {}
    exec(compile(isolated_module, str(signals_path), "exec"), namespace)
    return namespace


def make_kospi_frame(final_close=108.0, final_high=110.0, final_low=100.0):
    closes = [100.0] * 19 + [final_close]
    highs = [101.0] * 19 + [final_high]
    lows = [99.0] * 19 + [final_low]
    return pd.DataFrame({"Close": closes, "High": highs, "Low": lows})


class MarketExecutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        functions = load_signal_functions()
        cls.cashflow = staticmethod(functions["calculate_cashflow_signal"])
        cls.execution = staticmethod(functions["evaluate_market_execution_quality"])
        cls.classify = staticmethod(functions["calculate_regime_classification"])

    def test_missing_futures_does_not_block_strong_cashflow(self):
        score, status, details = self.cashflow(
            foreign_futures=None,
            oi_signal="가격 상승 + 미결제약정 증가 (신규 롱 가능성)",
            kospi_hist=make_kospi_frame(),
            foreign_cashflow=4000,
            market_breadth={"advancing": 240, "declining": 100},
            rsp_change_pct=0.1,
        )

        self.assertGreaterEqual(score, 70)
        self.assertIn("강함", status)
        self.assertTrue(any("미확인" in message for _, message in details))

    def test_open_interest_increase_without_price_direction_is_neutral(self):
        base_score, _, _ = self.cashflow(
            foreign_futures=None,
            oi_signal="미확인",
            kospi_hist=make_kospi_frame(),
            foreign_cashflow=None,
            market_breadth=None,
            rsp_change_pct=None,
        )
        ambiguous_score, _, _ = self.cashflow(
            foreign_futures=None,
            oi_signal="증가 추세",
            kospi_hist=make_kospi_frame(),
            foreign_cashflow=None,
            market_breadth=None,
            rsp_change_pct=None,
        )

        self.assertEqual(base_score, ambiguous_score)

    def test_rsp_is_only_a_small_global_confirmation(self):
        score, _, _ = self.cashflow(
            foreign_futures=None,
            oi_signal="미확인",
            kospi_hist=make_kospi_frame(),
            foreign_cashflow=None,
            market_breadth=None,
            rsp_change_pct=0.1,
        )

        self.assertEqual(score, 35)

    def test_failed_breakout_defers_new_order(self):
        quality = self.execution(
            make_kospi_frame(final_close=102.0, final_high=110.0, final_low=100.0)
        )

        self.assertEqual(quality["code"], "FAILED_BREAKOUT")
        self.assertTrue(quality["defer_new_order"])

    def test_clean_close_can_be_executed_next_session(self):
        quality = self.execution(make_kospi_frame())

        self.assertEqual(quality["code"], "EXECUTABLE")
        self.assertFalse(quality["defer_new_order"])

    def test_conditional_go_keeps_signal_but_defers_order_on_failed_breakout(self):
        previous_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as temp_dir:
            os.chdir(temp_dir)
            try:
                regime, action, _ = self.classify(
                    60,
                    55,
                    True,
                    execution_quality={
                        "defer_new_order": True,
                        "reason": "돌파 실패로 종가 체결 품질이 나쁩니다.",
                    },
                )
            finally:
                os.chdir(previous_cwd)

        self.assertIn("조건부 GO", regime)
        self.assertIn("체결 유예", regime)
        self.assertIn("오늘 신규 주문은 동결", action)


if __name__ == "__main__":
    unittest.main()
