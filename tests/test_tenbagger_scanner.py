import datetime as dt
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tenbagger_model import evaluate_tenbagger_candidate
from tenbagger_scanner import run_afternoon_finalize, run_morning_cycle


def strong_stock(name="ALPHA"):
    return {
        "Name": name,
        "Region": "미국",
        "_ticker": name,
        "Price": 120.0,
        "Change": 1.0,
        "MarketCap": 5_000_000_000,
        "Rev_Growth": 0.35,
        "Earnings_Growth": 0.40,
        "Op_Margin": 0.25,
        "ROE": 0.20,
        "Forward_PER": 25.0,
        "PEG": 1.0,
        "FCF_Yield": 0.04,
        "ROIC": 0.15,
        "Rule_of_40": 60.0,
        "Current_Ratio": 2.0,
        "Debt_Equity": 20.0,
        "Dilution_YoY": 0.01,
        "MA20": 115.0,
        "MA60": 110.0,
        "MA120": 100.0,
        "MA20_gap": 4.35,
        "W52_pos": 80.0,
        "error": None,
    }


class TenbaggerModelTests(unittest.TestCase):
    def test_strong_company_is_research_candidate(self):
        result = evaluate_tenbagger_candidate(strong_stock(), "미국 AI")
        self.assertTrue(result["eligible"])
        self.assertEqual(result["timing_status"], "ENTRY_REVIEW")

    def test_missing_growth_is_vetoed_instead_of_treated_as_zero(self):
        stock = strong_stock()
        stock["Rev_Growth"] = None
        result = evaluate_tenbagger_candidate(stock)
        self.assertFalse(result["eligible"])
        self.assertIn("매출 성장률 확인 불가", result["vetoes"])

    def test_falling_knife_is_vetoed(self):
        stock = strong_stock()
        stock["Change"] = -9.0
        result = evaluate_tenbagger_candidate(stock)
        self.assertFalse(result["eligible"])
        self.assertIn("당일 급락 중인 낙하 칼날", result["vetoes"])

    def test_material_dilution_is_vetoed(self):
        stock = strong_stock()
        stock["Dilution_YoY"] = 0.20
        result = evaluate_tenbagger_candidate(stock)
        self.assertFalse(result["eligible"])
        self.assertIn("최근 주식 수 15% 이상 희석", result["vetoes"])


class TenbaggerCycleTests(unittest.TestCase):
    def test_one_sector_per_morning_then_afternoon_finalize(self):
        universe = {"미국 A": ["AAA"], "미국 B": ["BBB"]}

        def fetcher(query, is_kr=False, fast_mode=False):
            return strong_stock(query)

        with tempfile.TemporaryDirectory() as temporary:
            state_path = Path(temporary) / "state.json"
            final_path = Path(temporary) / "final.json"
            with patch("tenbagger_scanner.TENBAGGER_UNIVERSE", universe):
                first = run_morning_cycle(fetcher, state_path=state_path, now=dt.datetime(2026, 8, 10, 9, 20))
                self.assertEqual(first["completed_sectors"], ["미국 A"])
                self.assertFalse(first["cycle_complete"])

                incomplete = run_afternoon_finalize(fetcher, state_path=state_path, final_path=final_path)
                self.assertEqual(incomplete["status"], "cycle_incomplete")

                second = run_morning_cycle(fetcher, state_path=state_path, now=dt.datetime(2026, 8, 11, 9, 20))
                self.assertTrue(second["cycle_complete"])
                complete = run_afternoon_finalize(
                    fetcher, state_path=state_path, final_path=final_path,
                    now=dt.datetime(2026, 8, 11, 14, 10),
                )
                self.assertEqual(complete["status"], "ready")
                self.assertEqual(complete["candidate_count"], 2)

    def test_afternoon_quote_updates_price_before_final_score(self):
        universe = {"미국 A": ["AAA"]}

        def fetcher(query, is_kr=False, fast_mode=False):
            return strong_stock(query)

        def quote_fetcher(query, is_kr=False):
            return {
                "price": 125.0,
                "previous_close": 120.0,
                "as_of": "2026-08-11T14:10:00+09:00",
                "source": "test quote",
            }

        with tempfile.TemporaryDirectory() as temporary:
            state_path = Path(temporary) / "state.json"
            final_path = Path(temporary) / "final.json"
            with patch("tenbagger_scanner.TENBAGGER_UNIVERSE", universe):
                run_morning_cycle(fetcher, state_path=state_path)
                result = run_afternoon_finalize(
                    fetcher, quote_fetcher=quote_fetcher,
                    state_path=state_path, final_path=final_path,
                )
            self.assertEqual(result["candidates"][0]["Price"], 125.0)
            self.assertEqual(result["candidates"][0]["Price_Source"], "test quote")


if __name__ == "__main__":
    unittest.main()
