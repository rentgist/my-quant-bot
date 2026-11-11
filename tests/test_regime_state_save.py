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
    post_close_refresh_due,
    regime_auto_confirm_ready,
    regime_save_allowed,
    save_state_to_github,
)

KST = datetime.timezone(datetime.timedelta(hours=9))


def kst(day, hour, minute=0):
    return datetime.datetime(2026, 11, day, hour, minute, tzinfo=KST)


class SaveTimingTests(unittest.TestCase):
    def test_today_bar_blocked_before_close(self):
        for hour, minute in ((9, 0), (13, 0), (15, 40), (15, 49)):
            allowed, reason = regime_save_allowed("2026-11-11", kst(11, hour, minute))
            self.assertFalse(allowed)
            self.assertIn("장마감", reason)

    def test_today_bar_allowed_after_close(self):
        self.assertTrue(regime_save_allowed("2026-11-11", kst(11, 15, 50))[0])
        self.assertTrue(regime_save_allowed("2026-11-11", kst(11, 20, 0))[0])

    def test_previous_completed_bar_allowed_before_open(self):
        self.assertTrue(regime_save_allowed("2026-11-10", kst(11, 8, 0))[0])

    def test_missing_or_future_bar_blocked(self):
        self.assertFalse(regime_save_allowed(None, kst(11, 18))[0])
        self.assertFalse(regime_save_allowed("2026-11-12", kst(11, 18))[0])


class AutoConfirmReadyTests(unittest.TestCase):
    CLOSED_FLOW = {"status": "ok", "market_status": "CLOSE", "as_of": "2026-11-11T15:30:00+09:00"}

    def ready(self, as_of="2026-11-11", now=None, fetched="11-11 15:55:02", flow=None):
        return regime_auto_confirm_ready(as_of, now or kst(11, 16), fetched, flow or self.CLOSED_FLOW)

    def test_fresh_close_data_is_ready(self):
        self.assertTrue(self.ready()[0])

    def test_before_close_is_not_ready(self):
        self.assertFalse(self.ready(now=kst(11, 15, 45))[0])

    def test_previous_bar_is_never_auto_confirmed(self):
        ok, reason = self.ready(as_of="2026-11-10", fetched="11-10 16:00:00")
        self.assertFalse(ok)
        self.assertIn("오늘이 아니", reason)

    def test_intraday_snapshot_is_not_ready(self):
        for fetched in ("11-11 15:20:00", "11-11 15:35:00", "11-10 16:00:00", "시간 정보 없음", None):
            ok, reason = self.ready(fetched=fetched)
            self.assertFalse(ok, fetched)
        self.assertIn("최신 데이터 불러오기", reason)

    def test_intraday_or_stale_flow_is_not_ready(self):
        for flow in (
            {**self.CLOSED_FLOW, "market_status": "OPEN"},
            {**self.CLOSED_FLOW, "as_of": "2026-11-10T15:30:00+09:00"},
            {**self.CLOSED_FLOW, "status": "unavailable"},
        ):
            self.assertFalse(self.ready(flow=flow)[0], flow)


class PostCloseRefreshTests(unittest.TestCase):
    def test_refreshes_once_after_close_when_snapshot_is_intraday(self):
        self.assertTrue(post_close_refresh_due(kst(11, 16), "11-11 15:25:00", False))
        self.assertTrue(post_close_refresh_due(kst(11, 16), "11-10 15:25:00", False))

    def test_no_refresh_when_already_fresh_tried_or_not_due(self):
        self.assertFalse(post_close_refresh_due(kst(11, 16), "11-11 15:45:00", False))
        self.assertFalse(post_close_refresh_due(kst(11, 16), "11-11 15:25:00", True))
        self.assertFalse(post_close_refresh_due(kst(11, 15, 35), "11-11 15:25:00", False))
        self.assertFalse(post_close_refresh_due(kst(14, 16), "11-13 15:25:00", False))  # Saturday


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
        expected = {"last_date": "2026-11-11", "warning_days": 2, "storage": "local"}
        self.assertEqual(self.saved(), expected)
        result = {}
        regime, _, _ = calculate_regime_classification(  # rerun, flow now 0
            25, 0, False, save_state=True, as_of_date="2026-11-11", prev_trading_date="2026-11-10",
            now_kst=kst(11, 16, 5), save_result=result,
        )
        # local-only confirmation stays visible as "local" and keeps the confirmed value
        self.assertEqual(result["status"], "local")
        self.assertEqual(self.saved(), expected)

    def test_confirmed_bar_is_not_rewritten_by_later_inputs(self):
        Path("regime_state.json").write_text(json.dumps({"last_date": "2026-11-11", "warning_days": 3}))
        result = {}
        # same bar, now non-warning inputs (flow 0): must not reset the confirmed counter
        calculate_regime_classification(
            25, 0, False, save_state=True, as_of_date="2026-11-11", prev_trading_date="2026-11-10",
            now_kst=kst(11, 17), save_result=result,
        )
        self.assertEqual(result["status"], "already")
        self.assertEqual(self.saved(), {"last_date": "2026-11-11", "warning_days": 3})

    def test_save_result_reports_blocked_intraday(self):
        result = {}
        calculate_regime_classification(
            25, 50, False, save_state=True, as_of_date="2026-11-11", prev_trading_date="2026-11-10",
            now_kst=kst(11, 13), save_result=result,
        )
        self.assertEqual(result["status"], "blocked")

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

    def _save(self, get_response=None, put_status=201, secrets=None, **kwargs):
        get = mock.Mock(return_value=get_response or mock.Mock(status_code=404))
        put = mock.Mock(return_value=mock.Mock(status_code=put_status))
        secrets = {"GITHUB_TOKEN": "dummy"} if secrets is None else secrets
        with mock.patch.object(signals.st, "secrets", secrets), \
                mock.patch("requests.get", get), mock.patch("requests.put", put):
            self.status = save_state_to_github(
                "regime_state.json", {"last_date": "2026-11-11", "warning_days": 1}, **kwargs
            )
        return get, put

    def test_save_status_values(self):
        self._save(put_status=201)
        self.assertEqual(self.status, "remote")
        self._save(put_status=404)  # e.g. regime-state branch missing
        self.assertEqual(self.status, "remote_failed")
        _, put = self._save(secrets={})
        self.assertEqual(self.status, "local")
        put.assert_not_called()

    def test_remote_already_confirmed_is_not_overwritten(self):
        import base64
        remote = base64.b64encode(json.dumps({"last_date": "2026-11-11", "warning_days": 2}).encode()).decode()
        response = mock.Mock(status_code=200)
        response.json.return_value = {"sha": "abc", "content": remote}
        _, put = self._save(get_response=response)
        self.assertEqual(self.status, "already")
        put.assert_not_called()
        # the remote (winning) value is mirrored locally instead of our attempt
        saved = json.loads(Path("regime_state.json").read_text())
        self.assertEqual(saved, {"last_date": "2026-11-11", "warning_days": 2, "storage": "remote"})

    def test_put_conflict_adopts_winner(self):
        import base64
        remote = base64.b64encode(json.dumps({"last_date": "2026-11-11", "warning_days": 3}).encode()).decode()
        winner = mock.Mock(status_code=200)
        winner.json.return_value = {"sha": "def", "content": remote}
        get = mock.Mock(side_effect=[mock.Mock(status_code=404), winner])
        put = mock.Mock(return_value=mock.Mock(status_code=409))
        with mock.patch.object(signals.st, "secrets", {"GITHUB_TOKEN": "dummy"}), \
                mock.patch("requests.get", get), mock.patch("requests.put", put):
            status = save_state_to_github("regime_state.json", {"last_date": "2026-11-11", "warning_days": 1})
        self.assertEqual(status, "already")
        saved = json.loads(Path("regime_state.json").read_text())
        self.assertEqual(saved["warning_days"], 3)

    def test_remote_success_and_failure_mark_storage(self):
        self._save(put_status=201)
        self.assertEqual(json.loads(Path("regime_state.json").read_text())["storage"], "remote")
        self._save(put_status=404)
        self.assertEqual(json.loads(Path("regime_state.json").read_text())["storage"], "local")

    def test_save_targets_data_branch_not_main(self):
        get, put = self._save()
        self.assertEqual(put.call_count, 1)
        self.assertEqual(put.call_args.kwargs["json"]["branch"], "regime-state")
        self.assertEqual(get.call_args.kwargs["params"], {"ref": "regime-state"})

    def test_any_other_branch_is_refused(self):
        for branch in ("main", "master", "refs/heads/main", "regime-state-x", ""):
            get, put = self._save(branch=branch)
            put.assert_not_called()
            get.assert_not_called()
        self.assertTrue(Path("regime_state.json").exists())

    def test_load_other_branch_never_reads_remote(self):
        get = mock.Mock()
        with mock.patch.object(signals.st, "secrets", {"GITHUB_TOKEN": "dummy"}), mock.patch("requests.get", get):
            signals.load_state_from_github("regime_state.json", branch="main")
        get.assert_not_called()

    def test_local_write_failure_does_not_break_classification(self):
        with mock.patch("builtins.open", side_effect=PermissionError("read-only")):
            save_state_to_github("regime_state.json", {"last_date": "2026-11-11", "warning_days": 1})
            regime, _, _ = calculate_regime_classification(
                25, 50, False, save_state=True, as_of_date="2026-11-11",
                prev_trading_date="2026-11-10",
                now_kst=datetime.datetime(2026, 11, 11, 16, tzinfo=KST),
            )
        self.assertIn("경고 국면", regime)

    def test_source_has_no_main_write(self):
        root = Path(__file__).resolve().parents[1]
        self.assertNotIn('"branch": "main"', (root / "signals.py").read_text(encoding="utf-8"))
        final = (root / "final.py").read_text(encoding="utf-8")
        self.assertNotIn("영구 저장 (GitHub 연동)", final)
        self.assertNotIn("save_regime", final)  # no manual save control left
        self.assertIn("save_state=regime_auto_save", final)
        self.assertIn("regime_auto_save = regime_ready and not regime_manual_inputs", final)
        self.assertIn("save_result=regime_save_result", final)
        self.assertIn("post_close_refresh_due(", final)
        self.assertIn("auto_refresh_due or post_close_due", final)


if __name__ == "__main__":
    unittest.main()
