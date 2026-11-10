"""Issue #119 (#111 batch A item 3): regime state save path, timing and trading-day counter."""
import datetime
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import signals
from signals import (
    calculate_regime_classification,
    next_warning_state,
    regime_save_allowed,
    save_state_to_github,
)

KST = datetime.timezone(datetime.timedelta(hours=9))


def kst(day, hour, minute=0):
    return datetime.datetime(2026, 11, day, hour, minute, tzinfo=KST)


class SaveTimingTests(unittest.TestCase):
    def test_today_bar_blocked_before_close(self):
        for hour, minute in ((9, 0), (13, 0), (15, 39)):
            allowed, reason = regime_save_allowed("2026-11-11", kst(11, hour, minute))
            self.assertFalse(allowed)
            self.assertIn("장마감", reason)

    def test_today_bar_allowed_after_close(self):
        self.assertTrue(regime_save_allowed("2026-11-11", kst(11, 15, 40))[0])
        self.assertTrue(regime_save_allowed("2026-11-11", kst(11, 20, 0))[0])

    def test_previous_completed_bar_allowed_before_open(self):
        self.assertTrue(regime_save_allowed("2026-11-10", kst(11, 8, 0))[0])

    def test_missing_or_future_bar_blocked(self):
        self.assertFalse(regime_save_allowed(None, kst(11, 18))[0])
        self.assertFalse(regime_save_allowed("2026-11-12", kst(11, 18))[0])


class TradingDayCounterTests(unittest.TestCase):
    def test_consecutive_trading_days_count_up(self):
        state = {"last_date": "", "warning_days": 0}
        state = next_warning_state(state, True, "2026-11-06", "2026-11-05")
        self.assertEqual(state["warning_days"], 1)
        # Friday -> Monday is consecutive in trading days.
        state = next_warning_state(state, True, "2026-11-09", "2026-11-06")
        self.assertEqual(state["warning_days"], 2)
        state = next_warning_state(state, True, "2026-11-10", "2026-11-09")
        self.assertEqual(state, {"last_date": "2026-11-10", "warning_days": 3})

    def test_same_bar_is_not_counted_twice(self):
        state = {"last_date": "2026-11-10", "warning_days": 2}
        self.assertEqual(next_warning_state(state, True, "2026-11-10", "2026-11-09")["warning_days"], 2)

    def test_missing_trading_day_restarts_streak(self):
        state = {"last_date": "2026-11-06", "warning_days": 2}
        self.assertEqual(next_warning_state(state, True, "2026-11-10", "2026-11-09")["warning_days"], 1)

    def test_non_warning_resets(self):
        state = {"last_date": "2026-11-09", "warning_days": 2}
        self.assertEqual(next_warning_state(state, False, "2026-11-10", "2026-11-09"),
                         {"last_date": "2026-11-10", "warning_days": 0})


class ClassificationSaveTests(unittest.TestCase):
    def setUp(self):
        self._cwd = os.getcwd()
        self._tmp = tempfile.TemporaryDirectory()
        os.chdir(self._tmp.name)

    def tearDown(self):
        os.chdir(self._cwd)
        self._tmp.cleanup()

    def classify(self, now, save=True, as_of="2026-11-11", prev="2026-11-10"):
        # flow 50, macro 25, below MA20 -> warning regime
        return calculate_regime_classification(
            25, 50, False, save_state=save, as_of_date=as_of, prev_trading_date=prev, now_kst=now
        )

    def saved(self):
        if not Path("regime_state.json").exists():
            return None
        return json.loads(Path("regime_state.json").read_text())

    def test_intraday_save_request_writes_nothing(self):
        self.classify(kst(11, 13))
        self.assertIsNone(self.saved())

    def test_after_close_save_uses_bar_date_and_reruns_do_not_double_count(self):
        Path("regime_state.json").write_text(json.dumps({"last_date": "2026-11-10", "warning_days": 1}))
        regime, _, _ = self.classify(kst(11, 16))
        self.assertIn("2/3일", regime)
        self.assertEqual(self.saved(), {"last_date": "2026-11-11", "warning_days": 2})
        regime, _, _ = self.classify(kst(11, 16, 5))  # 5-minute rerun
        self.assertIn("2/3일", regime)
        self.assertEqual(self.saved(), {"last_date": "2026-11-11", "warning_days": 2})

    def test_preview_without_save_leaves_state_untouched(self):
        Path("regime_state.json").write_text(json.dumps({"last_date": "2026-11-10", "warning_days": 1}))
        self.classify(kst(11, 16), save=False)
        self.assertEqual(self.saved(), {"last_date": "2026-11-10", "warning_days": 1})


class GithubPathTests(unittest.TestCase):
    def setUp(self):
        self._cwd = os.getcwd()
        self._tmp = tempfile.TemporaryDirectory()
        os.chdir(self._tmp.name)

    def tearDown(self):
        os.chdir(self._cwd)
        self._tmp.cleanup()

    def _save(self, **kwargs):
        get = mock.Mock(return_value=mock.Mock(status_code=404))
        put = mock.Mock()
        with mock.patch.object(signals.st, "secrets", {"GITHUB_TOKEN": "dummy"}), \
                mock.patch("requests.get", get), mock.patch("requests.put", put):
            save_state_to_github("regime_state.json", {"last_date": "2026-11-11", "warning_days": 1}, **kwargs)
        return get, put

    def test_save_targets_data_branch_not_main(self):
        get, put = self._save()
        self.assertEqual(put.call_count, 1)
        self.assertEqual(put.call_args.kwargs["json"]["branch"], "regime-state")
        self.assertEqual(get.call_args.kwargs["params"], {"ref": "regime-state"})

    def test_main_branch_is_refused(self):
        _, put = self._save(branch="main")
        put.assert_not_called()
        self.assertTrue(Path("regime_state.json").exists())

    def test_source_has_no_main_write(self):
        root = Path(__file__).resolve().parents[1]
        self.assertNotIn('"branch": "main"', (root / "signals.py").read_text(encoding="utf-8"))
        final = (root / "final.py").read_text(encoding="utf-8")
        self.assertNotIn("영구 저장 (GitHub 연동)\", value=False", final)
        self.assertIn("save_regime = st.button(", final)
        self.assertIn("save_state=save_regime and save_allowed", final)


if __name__ == "__main__":
    unittest.main()
