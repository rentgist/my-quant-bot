"""Issue #118 (#111 batch A items 1-2): structured falling-knife flag and KR recovery gate."""
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from signals import (
    calculate_kr_bottom_finder,
    calculate_us_bottom_finder,
    get_strategic_advice,
    kr_recovery_score_from_regime,
)


def _knife_after_mild_drop():
    """300 rising days, a mild pullback, then a -3% day: knife with a low bottom score."""
    index = pd.bdate_range(end="2026-11-10", periods=320)
    close = np.concatenate([np.linspace(80, 100, 300), np.linspace(99.5, 96.5, 19)])
    close = np.append(close, close[-1] * 0.97)
    return pd.DataFrame({"Close": close}, index=index)


class FallingKnifeFlagTests(unittest.TestCase):
    def test_us_finder_returns_knife_flag_even_below_35(self):
        score, verdict, _details, _phase, is_knife = calculate_us_bottom_finder(
            _knife_after_mild_drop(), pd.DataFrame(), None
        )
        self.assertLess(score, 35)
        self.assertTrue(is_knife)
        self.assertNotIn("칼날", verdict)  # the bug: text alone loses the state

    def test_kr_finder_returns_knife_flag_even_below_35(self):
        score, verdict, _details, _phase, is_knife = calculate_kr_bottom_finder(
            _knife_after_mild_drop(), pd.DataFrame(), pd.DataFrame()
        )
        self.assertLess(score, 35)
        self.assertTrue(is_knife)
        self.assertNotIn("칼날", verdict)

    def test_empty_input_returns_five_values_without_knife(self):
        result = calculate_us_bottom_finder(pd.DataFrame(), pd.DataFrame(), None)
        self.assertEqual(len(result), 5)
        self.assertFalse(result[4])

    def test_knife_flag_forces_stop_when_verdict_text_has_no_knife(self):
        head, _color, _actions = get_strategic_advice(
            0, 20, "⚪ 바닥 조건 미충족", recovery_score=100, is_falling_knife=True
        )
        self.assertIn("STOP", head)

    def test_knife_flag_overrides_top_and_go_paths(self):
        for score, verdict in ((10, "📈 고점권 — 바닥 탐지 불가"), (60, "🟢 바닥 후보 관찰 구간")):
            head, _, _ = get_strategic_advice(0, score, verdict, recovery_score=100, is_falling_knife=True)
            self.assertIn("STOP", head)

    def test_legacy_text_check_still_works_without_flag(self):
        head, _, _ = get_strategic_advice(0, 40, "⚠️ 떨어지는 칼날 (관망 권장)")
        self.assertIn("STOP", head)

    def test_no_knife_low_score_is_clear(self):
        head, _, _ = get_strategic_advice(0, 20, "⚪ 바닥 조건 미충족", is_falling_knife=False)
        self.assertIn("CLEAR", head)


class KrRecoveryGateTests(unittest.TestCase):
    def test_recovery_comes_from_confirmed_trend_only(self):
        ok = {"status": "ok", "panic_freeze": False}
        self.assertEqual(kr_recovery_score_from_regime({**ok, "code": "BOTTOM_RECOVERY"}), 100)
        self.assertEqual(kr_recovery_score_from_regime({**ok, "code": "UPTREND"}), 100)
        self.assertEqual(kr_recovery_score_from_regime({**ok, "code": "SIDEWAYS"}), 0)
        self.assertEqual(kr_recovery_score_from_regime({**ok, "code": "CRASH"}), 0)
        self.assertEqual(
            kr_recovery_score_from_regime({"status": "ok", "code": "UPTREND", "panic_freeze": True}), 0
        )
        self.assertEqual(kr_recovery_score_from_regime({"status": "unavailable", "code": "SIDEWAYS"}), 0)
        self.assertEqual(kr_recovery_score_from_regime(None), 0)

    def test_low_danger_without_recovery_is_wait_not_go(self):
        recovery = kr_recovery_score_from_regime({"status": "ok", "code": "SIDEWAYS", "panic_freeze": False})
        head, _, _ = get_strategic_advice(
            0, 60, "🟢 바닥 후보 관찰 구간", recovery_score=recovery, is_falling_knife=False
        )
        self.assertIn("WAIT", head)
        self.assertNotIn("GO", head)

    def test_confirmed_recovery_allows_go(self):
        recovery = kr_recovery_score_from_regime({"status": "ok", "code": "BOTTOM_RECOVERY", "panic_freeze": False})
        head, _, _ = get_strategic_advice(
            0, 60, "🟢 바닥 후보 관찰 구간", recovery_score=recovery, is_falling_knife=False
        )
        self.assertIn("GO", head)


class FinalWiringTests(unittest.TestCase):
    """final.py runs Streamlit at import, so check the wiring in its source."""

    @classmethod
    def setUpClass(cls):
        cls.source = (Path(__file__).resolve().parents[1] / "final.py").read_text(encoding="utf-8")

    def test_go_gate_no_longer_uses_macro_safety(self):
        self.assertNotIn("recovery_score=kr_macro_score", self.source)
        self.assertEqual(self.source.count("recovery_score=kr_recovery_score, is_falling_knife=kr_is_knife"), 2)
        self.assertIn("recovery_score=us_rec_score, is_falling_knife=us_is_knife", self.source)

    def test_scout_gates_use_flag_not_verdict_text(self):
        self.assertNotIn('"칼날" in str(kr_verdict)', self.source)
        self.assertNotIn('"칼날" in str(us_verdict)', self.source)
        self.assertIn("bool(kr_is_knife)", self.source)
        self.assertIn("bool(us_is_knife)", self.source)


if __name__ == "__main__":
    unittest.main()
