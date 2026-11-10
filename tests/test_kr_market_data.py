import ast
import datetime as dt
from pathlib import Path
import textwrap
import unittest
from unittest.mock import Mock

import pandas as pd
import requests

from kr_market_data import (
    INSTITUTIONS, KST, OI_SIGNALS, apply_session, near_month_contract, second_thursday,
    session_current, fetch_daum_futures_flow, fetch_daum_open_interest,
    fetch_monthly_flow, fetch_naver_futures_flow, fetch_naver_snapshot,
    parse_daum_futures_flow, parse_daum_open_interest, parse_monthly_flow,
    parse_naver_futures_flow, parse_naver_snapshot, select_futures_flow, valid_flow,
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


class KoreanFuturesTests(unittest.TestCase):
    def setUp(self):
        self.now = dt.datetime(2026, 11, 9, 15, 0, tzinfo=KST)  # 월요일 장중
        self.naver = {"dealTrendInfo": {"bizdate": "20261109", "foreignValue": "+7,409",
                                        "institutionalValue": "-3,120", "personalValue": "-4,289"}}
        days = [d for d in range(9, 0, -1) if dt.date(2026, 11, d).weekday() < 5]
        self.daum_rows = [{"date": f"2026-11-{d:02d} 00:00:00", "foreignSettlement": 100 * d,
                           "institutionalSettlement": -50, "privateSettlement": -50}
                          for d in days]
        self.masters = {"data": [{"symbolCode": "KR4101VC0004", "name": "F 202612"}]}
        self.oi_rows = [
            {"date": "2026-11-09 00:00:00", "tradePrice": 412.5, "changePrice": 3.25,
             "unsettledVolume": 260000},
            {"date": "2026-11-06 00:00:00", "tradePrice": 409.25, "changePrice": -1.0,
             "unsettledVolume": 250000},
        ]

    def test_naver_sign_and_current_session(self):
        result = parse_naver_futures_flow(self.naver, self.now)
        self.assertEqual((result["foreign"], result["institution"], result["personal"]),
                         (7409, -3120, -4289))
        self.assertTrue(result["current"])
        self.assertIs(select_futures_flow(result, {}), result)

    def test_naver_zero_is_valid_and_missing_is_unknown(self):
        self.naver["dealTrendInfo"]["foreignValue"] = "0"
        self.assertEqual(parse_naver_futures_flow(self.naver, self.now)["foreign"], 0)
        del self.naver["dealTrendInfo"]["foreignValue"]
        missing = parse_naver_futures_flow(self.naver, self.now)
        self.assertEqual(missing["status"], "unavailable")
        self.assertIsNone(missing["foreign"])
        self.assertIsNone(select_futures_flow(missing, {}))

    def test_prior_session_is_reference_only_after_open(self):
        self.naver["dealTrendInfo"]["bizdate"] = "20261106"
        after_open = parse_naver_futures_flow(self.naver, self.now)
        self.assertEqual(after_open["status"], "ok")
        self.assertFalse(after_open["current"])
        self.assertIsNone(select_futures_flow(after_open, after_open))
        before_open = parse_naver_futures_flow(self.naver, self.now.replace(hour=8))
        self.assertTrue(before_open["current"])
        future = parse_naver_futures_flow(self.naver, dt.datetime(2026, 11, 5, 15, tzinfo=KST))
        self.assertFalse(future["current"])

    def test_daum_windows_and_fallback(self):
        result = parse_daum_futures_flow(self.daum_rows, self.now)
        self.assertEqual(result["foreign"], 900)
        self.assertEqual(result["foreign_5d"], 100 * (9 + 6 + 5 + 4 + 3))
        self.assertIsNone(result["foreign_20d"])  # 11월 1~9일 평일은 7개뿐
        naver_down = parse_naver_futures_flow({}, self.now)
        self.assertIs(select_futures_flow(naver_down, result), result)

    def test_daum_gap_in_window_and_bad_order_are_unknown(self):
        self.daum_rows[2]["foreignSettlement"] = None
        result = parse_daum_futures_flow(self.daum_rows, self.now)
        self.assertEqual(result["foreign"], 900)
        self.assertIsNone(result["foreign_5d"])
        reversed_rows = list(reversed(self.daum_rows))
        self.assertEqual(parse_daum_futures_flow(reversed_rows, self.now)["status"], "unavailable")
        self.assertEqual(parse_daum_futures_flow([], self.now)["status"], "unavailable")

    def test_fractional_contracts_are_rejected(self):
        self.naver["dealTrendInfo"]["foreignValue"] = "12.5"
        self.assertEqual(parse_naver_futures_flow(self.naver, self.now)["status"], "unavailable")

    def test_open_interest_signal_combinations(self):
        # 방향은 연속 두 거래일 가격으로 정한다. changePrice는 부호 없는 값으로 둔다.
        cases = {(412.5, 260000): "가격 상승 + 미결제약정 증가 (신규 롱 가능성)",
                 (412.5, 240000): "가격 상승 + 미결제약정 감소 (숏커버 가능성)",
                 (405.0, 260000): "가격 하락 + 미결제약정 증가 (신규 숏 가능성)",
                 (405.0, 240000): "가격 하락 + 미결제약정 감소 (롱청산 가능성)"}
        for (price, oi), expected in cases.items():
            with self.subTest(price=price, oi=oi):
                self.oi_rows[0].update(tradePrice=price, changePrice=abs(price - 409.25),
                                       unsettledVolume=oi)
                result = parse_daum_open_interest(self.masters, self.oi_rows, self.now)
                self.assertEqual(result["signal"], expected)
                self.assertIn(result["signal"], OI_SIGNALS.values())

    def test_open_interest_rollover_flat_stale_and_malformed(self):
        self.oi_rows[0]["unsettledVolume"] = 150000
        self.assertIsNone(parse_daum_open_interest(self.masters, self.oi_rows, self.now)["signal"])
        self.oi_rows[0]["unsettledVolume"] = 250000
        self.assertIsNone(parse_daum_open_interest(self.masters, self.oi_rows, self.now)["signal"])
        same_day = [dict(r) for r in self.oi_rows]
        same_day[0].update(unsettledVolume=260000, date="2026-11-06")
        self.assertEqual(parse_daum_open_interest(self.masters, same_day, self.now)["status"],
                         "unavailable")
        stale_rows = [dict(r) for r in self.oi_rows]
        stale_rows[0]["date"], stale_rows[1]["date"] = "2026-11-06", "2026-11-05"
        stale = parse_daum_open_interest(self.masters, stale_rows, self.now)
        self.assertFalse(stale["current"])
        self.assertIsNone(stale["signal"])
        self.assertEqual(parse_daum_open_interest(self.masters, self.oi_rows[:1], self.now)["status"],
                         "unavailable")

    def test_before_open_accepts_only_immediately_previous_weekday(self):
        monday_8am = self.now.replace(hour=8)
        self.assertTrue(session_current(dt.date(2026, 11, 6), monday_8am))
        self.assertFalse(session_current(dt.date(2026, 11, 5), monday_8am))
        sunday = dt.datetime(2026, 11, 8, 20, tzinfo=KST)
        self.assertTrue(session_current(dt.date(2026, 11, 6), sunday))
        self.assertFalse(session_current(dt.date(2026, 11, 5), sunday))
        self.assertFalse(session_current(dt.date(2026, 11, 10), self.now))

    def test_cached_snapshot_is_revalidated_across_open(self):
        self.naver["dealTrendInfo"]["bizdate"] = "20261106"
        self.oi_rows[0]["date"], self.oi_rows[1]["date"] = "2026-11-06", "2026-11-05"
        before = self.now.replace(hour=8, minute=59)
        flow = parse_naver_futures_flow(self.naver, before)
        oi = parse_daum_open_interest(self.masters, self.oi_rows, before)
        self.assertTrue(flow["current"])
        self.assertIsNotNone(oi["signal"])
        after = self.now.replace(hour=9, minute=1)
        self.assertFalse(apply_session(flow, after)["current"])
        self.assertIsNone(select_futures_flow(apply_session(flow, after), {}))
        self.assertIsNone(apply_session(oi, after)["signal"])
        self.assertTrue(flow["current"])  # 원본 캐시 객체는 바꾸지 않는다.

    def test_open_interest_requires_consecutive_sessions_and_integer_counts(self):
        self.oi_rows[1]["date"] = "2026-11-02"
        gap = parse_daum_open_interest(self.masters, self.oi_rows, self.now)
        self.assertEqual(gap["status"], "ok")
        self.assertIsNone(gap["signal"])
        self.assertIn("연속 거래일 아님", gap["reason"])
        self.oi_rows[1].update(date="2026-11-06", unsettledVolume=260000)
        self.oi_rows[0]["unsettledVolume"] = 260000.5
        self.assertEqual(parse_daum_open_interest(self.masters, self.oi_rows, self.now)["status"],
                         "unavailable")

    def test_fetch_errors_and_headers(self):
        get = Mock(side_effect=requests.Timeout())
        for fetch in (fetch_naver_futures_flow, fetch_daum_futures_flow, fetch_daum_open_interest):
            with self.subTest(fetch=fetch.__name__):
                result = fetch(self.now, get=get)
                self.assertEqual(result["status"], "unavailable")
                self.assertIsNone(result.get("foreign"))
                self.assertIsNone(result.get("signal"))

        def ok(payload):
            response = Mock()
            response.json.return_value = payload
            return response
        get = Mock(side_effect=[ok(self.masters), ok({"data": self.oi_rows})])
        result = fetch_daum_open_interest(self.now, get=get)
        self.assertEqual(result["status"], "ok")
        self.assertIn("finance.daum.net", get.call_args_list[0].kwargs["headers"]["Referer"])
        self.assertIn("KR4101VC0004", get.call_args_list[1].args[0])
        bad = Mock(side_effect=[ok({"data": [{"symbolCode": "../x", "name": "F 202612"}]})])
        self.assertEqual(fetch_daum_open_interest(self.now, get=bad)["reason"], "근월물 식별 불가")
        self.assertEqual(bad.call_count, 1)

    def test_unsigned_change_price_cannot_flip_direction(self):
        self.oi_rows[0].update(tradePrice=405.0, changePrice=4.25, unsettledVolume=260000)
        result = parse_daum_open_interest(self.masters, self.oi_rows, self.now)
        self.assertEqual(result["signal"], "가격 하락 + 미결제약정 증가 (신규 숏 가능성)")
        self.assertEqual(result["change"], -4.25)
        self.oi_rows[0]["change"] = "RISE"  # 방향 필드가 가격 차이와 모순되면 판정하지 않는다.
        contradicted = parse_daum_open_interest(self.masters, self.oi_rows, self.now)
        self.assertIsNone(contradicted["signal"])
        self.assertIn("불일치", contradicted["reason"])
        self.oi_rows[0]["change"] = "FALL"
        self.assertIsNotNone(parse_daum_open_interest(self.masters, self.oi_rows, self.now)["signal"])
        self.oi_rows[0]["change"] = "UNKNOWN"
        self.assertEqual(parse_daum_open_interest(self.masters, self.oi_rows, self.now)["status"],
                         "unavailable")

    def test_near_month_ignores_order_and_expired_or_ambiguous_contracts(self):
        entries = [{"symbolCode": "FAR", "name": "F 202703"},
                   {"symbolCode": "SPREAD", "name": "SP 202612-202703"},
                   {"symbolCode": "OLD", "name": "F 202609"},
                   {"symbolCode": "NEAR", "name": "F 202612"}]
        self.assertEqual(near_month_contract(entries, self.now)["symbolCode"], "NEAR")
        expiry_day = dt.datetime(2026, 12, 10, 15, 0, tzinfo=KST)
        self.assertEqual(near_month_contract(entries, expiry_day)["symbolCode"], "NEAR")
        after_expiry = expiry_day.replace(hour=15, minute=20)
        self.assertEqual(near_month_contract(entries, after_expiry)["symbolCode"], "FAR")
        duplicate = entries + [{"symbolCode": "NEAR2", "name": "코스피200 F 202612"}]
        self.assertIsNone(near_month_contract(duplicate, self.now))
        self.assertIsNone(near_month_contract([{"symbolCode": "X", "name": "미니 F 202612"}], self.now))
        self.assertEqual(second_thursday(2026, 12), dt.date(2026, 12, 10))
        self.assertEqual(second_thursday(2027, 3), dt.date(2027, 3, 11))

    def test_cached_values_keep_fetch_time_provisional_and_expire_contracts(self):
        fetched = parse_naver_futures_flow(self.naver, self.now.replace(hour=15, minute=44))
        self.assertTrue(apply_session(fetched, self.now.replace(hour=15, minute=46))["provisional"])
        expiry_day = dt.datetime(2026, 12, 10, 15, 19, tzinfo=KST)
        self.oi_rows[0]["date"], self.oi_rows[1]["date"] = "2026-12-10", "2026-12-09"
        oi = parse_daum_open_interest(self.masters, self.oi_rows, expiry_day)
        self.assertEqual(oi["expiry"], "2026-12-10")
        self.assertIsNotNone(oi["signal"])
        expired = apply_session(oi, expiry_day.replace(minute=20))
        self.assertFalse(expired["current"])
        self.assertIsNone(expired["signal"])
        self.assertIn("만기 경과", expired["reason"])

    def test_today_dated_payload_before_open_is_not_current(self):
        monday_8am = self.now.replace(hour=8)
        self.assertFalse(session_current(dt.date(2026, 11, 9), monday_8am))
        self.naver["dealTrendInfo"]["foreignValue"] = "+6,000"
        early = parse_naver_futures_flow(self.naver, monday_8am)
        self.assertFalse(early["current"])
        self.assertIsNone(select_futures_flow(early, {}))

    def test_intraday_values_are_marked_provisional(self):
        intraday = parse_naver_futures_flow(self.naver, self.now)
        self.assertTrue(intraday["provisional"])
        closed = parse_naver_futures_flow(self.naver, self.now.replace(hour=15, minute=45))
        self.assertFalse(closed["provisional"])
        self.naver["dealTrendInfo"]["bizdate"] = "20261106"
        self.assertFalse(parse_naver_futures_flow(self.naver, self.now.replace(hour=8))["provisional"])
        self.assertTrue(parse_daum_open_interest(self.masters, self.oi_rows, self.now)["provisional"])

    def test_flow_block_uses_auto_then_manual_override(self):
        from streamlit.testing.v1 import AppTest
        source = (Path(__file__).resolve().parents[1] / "final.py").read_text(encoding="utf-8")
        start = source.index("        # 파생 데이터는 현재 세션 자동값")
        end = source.index('        st.markdown(f"**상태:** {kr_flow_status}")', start)
        block = textwrap.dedent(source[start:end])
        snap = {"naver": parse_naver_futures_flow(self.naver, self.now),
                "daum": parse_daum_futures_flow(self.daum_rows, self.now),
                "oi": parse_daum_open_interest(self.masters, self.oi_rows, self.now)}
        harness = f"""import streamlit as st
import pandas as pd
from kr_market_data import select_futures_flow
from signals import calculate_cashflow_signal, regime_save_allowed
from config import get_kst_now
def get_kr_futures_snapshot():
    return {snap!r}
def sync_futures_sniper():
    pass
def get_intraday_market_internals():
    return {{'as_of': None, 'breadth_reason': '테스트', 'advancing': None, 'declining': None}}
summary_dict = {{}}
kospi_10y = pd.DataFrame()
rsp_change_pct = None
""" + block + ("\nst.session_state['captured'] = (foreign_futures_signal, oi_signal, kr_flow_score)"
                       "\nst.session_state['note'] = foreign_futures_note\n")
        app = AppTest.from_string(harness).run(timeout=15)
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(app.session_state["captured"][:2],
                         (7409, "가격 상승 + 미결제약정 증가 (신규 롱 가능성)"))
        self.assertEqual(app.session_state["captured"][2], 15 + 10)
        self.assertTrue(any("장중 잠정" in c.value for c in app.caption))
        self.assertTrue(any("현재가 412.50" in c.value for c in app.caption))
        self.assertEqual(app.session_state["note"], "네이버 자동, 장중 잠정")
        app.number_input[0].set_value(-2000)
        app.checkbox(key="futures_confirmed_main").check()
        app.run(timeout=15)
        self.assertEqual(app.session_state["captured"][0], -2000)
        self.assertEqual(app.session_state["note"], "수동 확인")


if __name__ == "__main__":
    unittest.main()
