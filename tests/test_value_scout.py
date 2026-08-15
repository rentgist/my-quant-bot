import unittest

from value_scout import (
    calculate_scout_budget,
    evaluate_scout_candidate,
    evaluate_scout_market_gate,
    score_scout_fundamentals,
)


def quality_stock(**overrides):
    stock = {
        "Name": "우량 테스트",
        "_ticker": "TEST",
        "Price": 70.0,
        "Change": 1.0,
        "MA5": 69.0,
        "MA20_gap": -8.0,
        "RSI_14": 40.0,
        "Gap_High": -30.0,
        "Rev_Growth": 0.25,
        "Op_Margin": 0.15,
        "ROE": 0.12,
        "PEG": 1.1,
        "PER": 20.0,
    }
    stock.update(overrides)
    return stock


def open_gate():
    return evaluate_scout_market_gate(
        bottom_score=85,
        data_valid=True,
        falling_knife=False,
        systemic_risk=False,
        trend_confirmed=False,
    )


class MarketGateTests(unittest.TestCase):
    def test_high_score_opens_screening_not_an_order(self):
        gate = open_gate()
        self.assertEqual(gate["state"], "CANDIDATE_SCREENING")
        self.assertTrue(gate["candidate_screening_allowed"])
        self.assertIn("주문 신호는 아닙니다", gate["reason"])

    def test_falling_knife_blocks_even_with_high_score(self):
        gate = evaluate_scout_market_gate(
            bottom_score=95,
            data_valid=True,
            falling_knife=True,
            systemic_risk=False,
            trend_confirmed=False,
        )
        self.assertEqual(gate["state"], "FALLING_KNIFE")
        self.assertFalse(gate["candidate_screening_allowed"])

    def test_panic_freeze_can_be_passed_as_falling_knife_veto(self):
        panic_freeze = True
        gate = evaluate_scout_market_gate(
            bottom_score=88,
            data_valid=True,
            falling_knife=panic_freeze,
            systemic_risk=False,
            trend_confirmed=False,
        )
        self.assertEqual(gate["state"], "FALLING_KNIFE")

    def test_confirmed_trend_hands_off_to_core(self):
        gate = evaluate_scout_market_gate(
            bottom_score=85,
            data_valid=True,
            falling_knife=False,
            systemic_risk=False,
            trend_confirmed=True,
        )
        self.assertEqual(gate["state"], "TREND_HANDOFF")


class FundamentalTests(unittest.TestCase):
    def test_missing_fields_are_not_counted_as_failures_or_passes(self):
        result = score_scout_fundamentals({"Rev_Growth": 0.25, "Op_Margin": 0.15})
        self.assertEqual(result["available"], 2)
        self.assertFalse(result["quality_confirmed"])
        self.assertEqual(result["status"], "DATA_INCOMPLETE")

    def test_four_of_five_available_passes_quality_gate(self):
        result = score_scout_fundamentals(quality_stock(PER=45.0))
        self.assertEqual(result["score"], 4)
        self.assertTrue(result["quality_confirmed"])


class ScoutBudgetTests(unittest.TestCase):
    def test_budget_uses_twenty_percent_of_target_and_two_percent_cap(self):
        small_target = calculate_scout_budget(target_weight_pct=5)
        large_target = calculate_scout_budget(target_weight_pct=20)
        self.assertEqual(small_target["asset_cap_pct"], 1.0)
        self.assertEqual(large_target["asset_cap_pct"], 2.0)

    def test_aggregate_five_percent_cap_is_enforced(self):
        result = calculate_scout_budget(target_weight_pct=20, aggregate_scout_pct=4.5)
        self.assertEqual(result["max_new_weight_pct"], 0.5)


class CandidateTests(unittest.TestCase):
    def test_quality_stock_in_value_zone_allows_only_capped_scout(self):
        result = evaluate_scout_candidate(
            quality_stock(),
            open_gate(),
            target_weight_pct=10,
            aggregate_scout_pct=1,
            total_assets=5000,
        )
        self.assertTrue(result["allowed"])
        self.assertEqual(result["max_new_weight_pct"], 2.0)
        self.assertEqual(result["max_order_amount"], 100.0)

    def test_stock_falling_knife_blocks_scout(self):
        result = evaluate_scout_candidate(
            quality_stock(Change=-5.0),
            open_gate(),
        )
        self.assertEqual(result["state"], "FALLING_KNIFE")
        self.assertEqual(result["max_new_weight_pct"], 0.0)

    def test_quality_failure_blocks_cheap_stock(self):
        result = evaluate_scout_candidate(
            quality_stock(Rev_Growth=-0.2, Op_Margin=-0.1, ROE=-0.1),
            open_gate(),
        )
        self.assertEqual(result["state"], "QUALITY_REVIEW")

    def test_overheated_rebound_is_not_a_value_scout(self):
        result = evaluate_scout_candidate(
            quality_stock(RSI_14=75.0, MA20_gap=15.0),
            open_gate(),
        )
        self.assertEqual(result["state"], "OVERHEAT")


if __name__ == "__main__":
    unittest.main()
