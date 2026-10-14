import ast
import datetime as dt
from pathlib import Path
import textwrap
import unittest
from unittest.mock import Mock

import pandas as pd
import requests

from kr_market_data import (
    INSTITUTIONS, KST, fetch_monthly_flow, fetch_naver_snapshot,
    parse_monthly_flow, parse_naver_snapshot, valid_flow,
)


class KoreanFlowTests(unittest.TestCase):
    def setUp(self):
        self.now = dt.datetime(2026, 10, 13, 11, 35, tzinfo=KST)
        self.integration = {
            "itemCode": "KOSPI",
            "dealTrendInfo": {"bizdate": "20261013", "foreignValue": "-24,848",
                              "institutionalValue": "+8,078", "personalValue": "+14,218"},
            "upDownStockInfo": {"riseCount": "56", "fallCount": "849",
                                "upperCount": "2", "lowerCount": "3"},
        }
        self.basic = {"itemCode": "KOSPI", "marketStatus": "OPEN",
                      "localTradedAt": "2026-10-13T11:33:00+09:00"}

    def parse(self):
        return parse_naver_snapshot(self.integration, self.basic, self.now)

    def monthly_frame(self):
        frame = pd.DataFrame({c: [100000000, 200000000] for c in INSTITUTIONS},
                             index=pd.to_datetime(["2026-10-08", "2026-10-12"]))
        frame["외국인"] = [-150000000, 25000000]
        frame["개인"] = [25000000, 50000000]
        frame["기타법인"] = 999999999999
        frame["기타외국인"] = 999999999999
        return frame

    def monthly(self, frame):
        return parse_monthly_flow(frame, dt.date(2026, 9, 13), dt.date(2026, 10, 12), self.now)

    def test_current_response_sign_units_and_breadth(self):
        data = self.parse()
        self.assertEqual(data["values"], (-24848, 8078, 14218))
        self.assertEqual((data["advancing"], data["declining"]), (56, 849))
        self.assertAlmostEqual(data["adr"], 56 / 849)
        self.assertEqual(data["status"], "ok")
        self.assertIsNone(data["program_net"])

    def test_legitimate_zero_is_valid(self):
        for key in ("foreignValue", "institutionalValue", "personalValue"):
            self.integration["dealTrendInfo"][key] = "0"
        self.assertEqual(self.parse()["values"], (0, 0, 0))
        self.assertTrue(valid_flow((0, 0, 0)))

    def test_missing_flow_does_not_disable_breadth(self):
        del self.integration["dealTrendInfo"]["foreignValue"]
        data = self.parse()
        self.assertEqual(data["values"], (None, None, None))
        self.assertEqual(data["breadth_status"], "ok")

    def test_missing_breadth_does_not_disable_flow(self):
        del self.integration["upDownStockInfo"]
        self.assertEqual(self.parse()["status"], "ok")
        self.assertIsNone(self.parse()["adr"])

    def test_http_error_never_returns_synthetic_values(self):
        response = Mock()
        response.raise_for_status.side_effect = requests.HTTPError("503")
        data = fetch_naver_snapshot(self.now, get=Mock(return_value=response))
        self.assertEqual(data["values"], (None, None, None))
        self.assertIn("HTTP", data["reason"])

    def test_json_error_and_timeout_are_unknown(self):
        response = Mock()
        response.json.side_effect = ValueError("HTML")
        self.assertEqual(fetch_naver_snapshot(self.now, Mock(return_value=response))["status"], "unavailable")
        self.assertEqual(fetch_naver_snapshot(self.now, Mock(side_effect=requests.Timeout()))["values"], (None,) * 3)

    def test_date_mismatch_stale_open_and_future_are_rejected(self):
        for timestamp in ("2026-10-12T11:33:00+09:00", "2026-10-13T10:00:00+09:00",
                          "2026-10-14T11:33:00+09:00"):
            with self.subTest(timestamp=timestamp):
                self.basic["localTradedAt"] = timestamp
                self.assertEqual(self.parse()["values"], (None,) * 3)
        self.basic["localTradedAt"] = "2026-10-13T11:33:00+09:00"
        self.integration["dealTrendInfo"]["bizdate"] = "20261012"
        self.assertEqual(self.parse()["values"], (None,) * 3)

    def test_closed_weekend_response_keeps_explicit_trade_date(self):
        self.basic.update(marketStatus="CLOSE", localTradedAt="2026-10-09T15:30:00+09:00")
        self.integration["dealTrendInfo"]["bizdate"] = "20261009"
        self.now = dt.datetime(2026, 10, 10, 8, tzinfo=KST)
        self.assertEqual(self.parse()["status"], "ok")
        self.assertIn("2026-10-09", self.parse()["as_of"])

    def test_prior_close_is_not_scored_after_weekday_open(self):
        self.basic.update(marketStatus="CLOSE", localTradedAt="2026-10-12T15:30:00+09:00")
        self.integration["dealTrendInfo"]["bizdate"] = "20261012"
        data = self.parse()
        self.assertEqual(data["status"], "unavailable")
        self.assertEqual(data["values"], (None, None, None))
        self.assertEqual(data["breadth_status"], "unavailable")
        self.assertIn("2026-10-12", data["as_of"])
        self.assertIn("전 거래일 종가", data["reason"])

    def test_prior_close_is_reference_before_weekday_open(self):
        self.basic.update(marketStatus="CLOSE", localTradedAt="2026-10-12T15:30:00+09:00")
        self.integration["dealTrendInfo"]["bizdate"] = "20261012"
        self.now = dt.datetime(2026, 10, 13, 8, 30, tzinfo=KST)
        self.assertEqual(self.parse()["status"], "ok")

    def test_malformed_and_negative_breadth_are_unknown(self):
        for value in (None, "N/A", "-2", "3.5"):
            with self.subTest(value=value):
                self.integration["upDownStockInfo"]["riseCount"] = value
                self.assertEqual(self.parse()["breadth_status"], "unavailable")

    def test_monthly_aggregation_excludes_other_corporations_and_foreigners(self):
        data = self.monthly(self.monthly_frame())
        self.assertEqual(data["values"], (-1.25, 21.0, 0.75))
        self.assertEqual(data["as_of"], "2026-10-12")

    def test_monthly_missing_category_and_nan_are_unknown(self):
        frame = self.monthly_frame().drop(columns="보험")
        self.assertEqual(self.monthly(frame)["values"], (None,) * 3)
        frame = self.monthly_frame()
        frame.loc[frame.index[0], "외국인"] = float("nan")
        self.assertEqual(self.monthly(frame)["values"], (None,) * 3)

    def test_institution_total_is_not_counted_twice(self):
        frame = self.monthly_frame()
        frame["기관합계"] = [100000000, 200000000]
        self.assertEqual(self.monthly(frame)["values"][1], 3.0)

    def test_monthly_future_dates_and_duplicate_dates_are_rejected(self):
        frame = self.monthly_frame()
        frame.index = pd.to_datetime(["2026-10-12", "2026-10-13"])
        self.assertEqual(self.monthly(frame)["status"], "unavailable")
        frame.index = pd.to_datetime(["2026-10-12", "2026-10-12"])
        self.assertEqual(self.monthly(frame)["status"], "unavailable")

    def test_completed_day_cutoff_and_failed_fetch(self):
        fetch = Mock(return_value=self.monthly_frame())
        fetch_monthly_flow(self.now, fetch)
        self.assertEqual(fetch.call_args.args[1], "20261012")
        fetch_monthly_flow(self.now.replace(hour=18), fetch)
        self.assertEqual(fetch.call_args.args[1], "20261013")
        data = fetch_monthly_flow(self.now, Mock(side_effect=RuntimeError("failure")))
        self.assertEqual(data["values"], (None,) * 3)

    def test_macro_consumer_distinguishes_zero_from_missing(self):
        path = Path(__file__).resolve().parents[1] / "signals.py"
        tree = ast.parse(path.read_text())
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "analyze_macro_flow")
        ns = {"valid_flow": valid_flow}
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), ns)
        analyze = ns["analyze_macro_flow"]
        _, zero = analyze({}, (0, 0, 0), {"flow_1m": (0, 0, 0)})
        _, missing = analyze({}, (None,) * 3)
        self.assertTrue(zero["flow_valid"])
        self.assertTrue(zero["flow_1m_valid"])
        self.assertFalse(missing["flow_valid"])
        self.assertFalse(missing["flow_1m_valid"])
        self.assertFalse(valid_flow((float("inf"), 1, 2)))

    def test_changed_dashboard_block_renders_zero_and_unknown(self):
        from streamlit.testing.v1 import AppTest
        source = (Path(__file__).resolve().parents[1] / "final.py").read_text()
        start = source.index('    flow_metadata = get_kr_market_snapshot()')
        end = source.index('    if st.button("🔄 CFO AI 시장 브리핑 생성"', start)
        block = textwrap.dedent(source[start:end])
        for values in ((0, 0, 0), (None, None, None)):
            with self.subTest(values=values):
                harness = """import streamlit as st
import pandas as pd
from signals import analyze_macro_flow
cnn_score = None
cnn_rating = 'N/A'
macro_charts = {}
kospi_10y = pd.DataFrame()
def get_kr_market_snapshot():
    return {'values': VALUES, 'as_of': '2026-10-13', 'reason': '테스트 응답', 'fetched_at': '2026-10-14'}
def get_1m_investor_flow_snapshot():
    return {'values': VALUES, 'as_of': '2026-10-12', 'reason': '테스트 응답', 'fetched_at': '2026-10-14'}
""".replace("VALUES", repr(values)) + block
                app = AppTest.from_string(harness).run(timeout=15)
                self.assertEqual(len(app.exception), 0)
                self.assertEqual(len(app.metric), 9)
                self.assertEqual(len(app.caption), 2)


if __name__ == "__main__":
    unittest.main()
