import datetime as dt
import unittest

from market_refresh import collect_if_valid, is_market_session, refresh_is_due


class FakeFrame:
    def __init__(self, empty=False):
        self.empty = empty


def valid_snapshot():
    return {
        "kospi_10y": FakeFrame(), "usdkrw_10y": FakeFrame(),
        "spy_10y": FakeFrame(), "vix_10y": FakeFrame(),
    }


class MarketRefreshTests(unittest.TestCase):
    def test_valid_collection_is_publishable(self):
        ok, snapshot, error = collect_if_valid(valid_snapshot)
        self.assertTrue(ok)
        self.assertIsNotNone(snapshot)
        self.assertIsNone(error)

    def test_partial_collection_is_rejected(self):
        partial = valid_snapshot()
        partial["vix_10y"] = FakeFrame(empty=True)
        ok, snapshot, error = collect_if_valid(lambda: partial)
        self.assertFalse(ok)
        self.assertIsNone(snapshot)
        self.assertIn("vix_10y", error)

    def test_provider_exception_is_rejected(self):
        ok, snapshot, error = collect_if_valid(lambda: (_ for _ in ()).throw(RuntimeError("offline")))
        self.assertFalse(ok)
        self.assertIsNone(snapshot)
        self.assertIn("offline", error)

    def test_refresh_interval_is_five_minutes(self):
        now = dt.datetime(2026, 8, 10, 10, 0)
        self.assertFalse(refresh_is_due(now - dt.timedelta(minutes=4, seconds=59), now))
        self.assertTrue(refresh_is_due(now - dt.timedelta(minutes=5), now))

    def test_korean_and_us_sessions_in_kst(self):
        self.assertTrue(is_market_session(dt.datetime(2026, 8, 10, 10, 0)))
        self.assertTrue(is_market_session(dt.datetime(2026, 8, 10, 22, 30)))
        self.assertFalse(is_market_session(dt.datetime(2026, 8, 8, 10, 0)))
