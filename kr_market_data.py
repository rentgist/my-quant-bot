"""한국 수급 응답 검증. 결측은 실제 0원과 구분해 보존한다."""

import datetime as dt
import math
import re
from decimal import Decimal, InvalidOperation

import requests

KST = dt.timezone(dt.timedelta(hours=9))
NAVER_BASE = "https://stock.naver.com/api/securityFe/api/index/KOSPI/"
INSTITUTIONS = ("금융투자", "보험", "투신", "사모", "은행", "기타금융", "연기금")


def unavailable(source, reason, now):
    return {"values": (None, None, None), "status": "unavailable",
            "source": source, "as_of": None, "fetched_at": now.isoformat(),
            "reason": reason, "advancing": None, "declining": None,
            "adr": None, "breadth_status": "unavailable",
            "breadth_reason": reason, "program_net": None,
            "program_status": "unavailable"}


def _number(value):
    if isinstance(value, bool) or value is None:
        raise ValueError("숫자 누락")
    text = str(value).strip().replace(",", "")
    if not re.fullmatch(r"[+-]?\d+(?:\.\d+)?", text):
        raise ValueError("숫자 형식 오류")
    try:
        result = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError("숫자 형식 오류") from exc
    if not result.is_finite():
        raise ValueError("유한 숫자가 아님")
    return result


def valid_flow(values):
    try:
        return len(values) == 3 and all(v is not None and not isinstance(v, bool)
                                       and math.isfinite(float(v)) for v in values)
    except (TypeError, ValueError, OverflowError):
        return False


def parse_naver_snapshot(integration, basic, now):
    """응답 기준일을 검증한 뒤 수급과 시장 폭을 독립적으로 파싱한다."""
    now = now.astimezone(KST)
    result = unavailable(NAVER_BASE + "integration", "응답 형식 또는 기준일 오류", now)
    try:
        if integration.get("itemCode") != "KOSPI" or basic.get("itemCode") != "KOSPI":
            return result
        traded_at = dt.datetime.fromisoformat(basic["localTradedAt"])
        if traded_at.tzinfo is None:
            return result
        traded_at = traded_at.astimezone(KST)
        age = now - traded_at
        if age.total_seconds() < -300 or age > dt.timedelta(days=10):
            result["reason"] = result["breadth_reason"] = "오래되었거나 미래 기준시각인 응답"
            return result
        result["as_of"] = traded_at.isoformat()
        result["market_status"] = basic.get("marketStatus")
        if basic.get("marketStatus") == "OPEN" and (
                traded_at.date() != now.date() or age > dt.timedelta(minutes=15)):
            result["reason"] = result["breadth_reason"] = "장중 시세 기준시각 지연"
            return result
        if basic.get("marketStatus") not in ("OPEN", "CLOSE", "CLOSED"):
            return result
        # 평일 장 개시 이후에는 전 거래일 종가 응답을 현재 수급으로 점수화하지 않는다.
        # 휴장일 여부를 별도 캘린더 없이 단정할 수 없으므로 기준시각은 표시하되 값은
        # unavailable로 유지한다. 주말과 평일 개장 전에는 최근 종가를 참고용으로 허용한다.
        if (basic.get("marketStatus") in ("CLOSE", "CLOSED")
                and now.weekday() < 5 and now.time() >= dt.time(9)
                and traded_at.date() != now.date()):
            result["reason"] = result["breadth_reason"] = (
                "현재 세션 데이터 미확인: 최근 응답은 전 거래일 종가")
            return result
        trend = integration.get("dealTrendInfo") or {}
        # 시장 폭에는 별도 기준일이 없으므로 같은 integration 응답의 수급일을 확인한다.
        bizdate = dt.datetime.strptime(trend["bizdate"], "%Y%m%d").date()
        if bizdate != traded_at.date():
            result["reason"] = result["breadth_reason"] = "수급일과 지수 기준일 불일치"
            return result
    except (KeyError, TypeError, ValueError, AttributeError):
        return result
    try:
        result["values"] = tuple(int(_number(trend[key])) for key in
                                 ("foreignValue", "institutionalValue", "personalValue"))
        result["status"] = "ok"
        result["reason"] = "장중 잠정 수급" if basic["marketStatus"] == "OPEN" else "최근 거래일 수급"
    except (KeyError, TypeError, ValueError):
        result["reason"] = "투자자 수급 필수값 누락 또는 형식 오류"
    try:
        breadth = integration["upDownStockInfo"]
        counts = [_number(breadth[key]) for key in ("riseCount", "fallCount")]
        if any(c < 0 or c != int(c) for c in counts) or sum(counts) == 0:
            raise ValueError("종목 수 오류")
        result["advancing"], result["declining"] = map(int, counts)
        # 상승·하락 수에 상한·하한 종목이 이미 포함되어 있다.
        result["adr"] = float(counts[0] / counts[1]) if counts[1] else None
        result["breadth_status"] = "ok"
        result["breadth_reason"] = "하락 종목 0개: ADR 산출 불가" if not counts[1] else "정상"
    except (KeyError, TypeError, ValueError):
        result["breadth_reason"] = "시장 폭 필수값 누락 또는 형식 오류"
    return result


def fetch_naver_snapshot(now, get=None):
    get = get or requests.get
    try:
        responses = []
        for endpoint in ("integration", "basic"):
            response = get(NAVER_BASE + endpoint, headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
            response.raise_for_status()
            responses.append(response.json())
        return parse_naver_snapshot(*responses, now=now)
    except requests.RequestException:
        return unavailable(NAVER_BASE + "integration", "네이버 연결 또는 HTTP 오류", now)
    except (ValueError, TypeError):
        return unavailable(NAVER_BASE + "integration", "네이버 JSON 응답 오류", now)


def parse_monthly_flow(frame, start_date, end_date, now):
    """KRX 일별 순매수 원화를 합산한다. 상세 외국인은 기타외국인과 구분한다."""
    result = unavailable("KRX / pykrx 일별 순매수", "KRX 응답 누락 (연결·로그인·필수 열 확인 필요)", now)
    result["requested_period"] = f"{start_date.isoformat()} ~ {end_date.isoformat()}"
    try:
        if frame is None or frame.empty or not frame.index.is_unique or not frame.columns.is_unique:
            return result
        dates = [v.date() for v in frame.index]
        if any(d < start_date or d > end_date for d in dates):
            return result
        if (end_date - max(dates)).days > 10:
            result["reason"] = "최근 완료 거래일 데이터 지연"
            return result
        required = ["외국인", "개인"]
        institutions = ["기관합계"] if "기관합계" in frame.columns else list(INSTITUTIONS)
        required += institutions
        if not all(c in frame.columns for c in required):
            return result
        totals = {c: sum((_number(v) for v in frame[c]), Decimal(0)) for c in required}
        result["values"] = tuple(float(v / Decimal(100000000)) for v in
                                 (totals["외국인"], sum(totals[c] for c in institutions), totals["개인"]))
        result["status"] = "ok"
        result["as_of"] = max(dates).isoformat()
        result["reason"] = "최근 30일 조회기간의 완료 거래일 누적 (원→억원)"
    except (TypeError, ValueError, AttributeError):
        pass
    return result


def fetch_monthly_flow(now, fetch=None):
    now = now.astimezone(KST)
    # KRX 당일 확정치 제공 시점(18시) 전에는 당일을 포함하지 않는다.
    end_date = now.date() if now.hour >= 18 else now.date() - dt.timedelta(days=1)
    start_date = now.date() - dt.timedelta(days=30)
    try:
        if fetch is None:
            from pykrx import stock
            fetch = stock.get_market_trading_value_by_date
        frame = fetch(start_date.strftime("%Y%m%d"), end_date.strftime("%Y%m%d"),
                      "KOSPI", detail=True)
        return parse_monthly_flow(frame, start_date, end_date, now)
    except Exception:
        result = unavailable("KRX / pykrx 일별 순매수", "KRX 조회 실패 (연결·라이브러리·응답 확인 필요)", now)
        result["requested_period"] = f"{start_date.isoformat()} ~ {end_date.isoformat()}"
        return result


# ── KOSPI200 선물 수급·미결제약정 (비공식 공개 JSON, 로그인 불필요) ──
NAVER_FUT_URL = "https://m.stock.naver.com/api/index/FUT/integration"
DAUM_FUT_FLOW_URL = "https://finance.daum.net/api/investor/future/days"
DAUM_FUT_MASTERS_URL = "https://finance.daum.net/api/futures/masters"
DAUM_FUT_DAYS_URL = "https://finance.daum.net/api/future/{code}/days"
DAUM_HEADERS = {"User-Agent": "Mozilla/5.0",
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Referer": "https://finance.daum.net/domestic/investors/DERIVATIVES",
                "X-Requested-With": "XMLHttpRequest"}
OI_SIGNALS = {
    (True, True): "가격 상승 + 미결제약정 증가 (신규 롱 가능성)",
    (True, False): "가격 상승 + 미결제약정 감소 (숏커버 가능성)",
    (False, True): "가격 하락 + 미결제약정 증가 (신규 숏 가능성)",
    (False, False): "가격 하락 + 미결제약정 감소 (롱청산 가능성)",
}
# 근월물 만기 전후에는 차월물로 넘어가며 미결제약정이 크게 줄어 방향 신호가 아니다.
OI_ROLLOVER_DROP = Decimal("0.2")
FUTURES_CLOSE = dt.time(15, 45)
FUTURES_EXPIRY_CLOSE = dt.time(15, 20)
DIRECTION_FIELD = {"RISE": 1, "UPPER_LIMIT": 1, "EVEN": 0, "FALL": -1, "LOWER_LIMIT": -1}


def previous_weekday(day):
    day -= dt.timedelta(days=1)
    while day.weekday() >= 5:
        day -= dt.timedelta(days=1)
    return day


def session_current(as_of, now):
    """기준일이 현재 세션 값인지. 주말·평일 개장 전에는 바로 앞 평일 종가만 허용한다.

    휴장 캘린더가 없으므로 공휴일로 생긴 공백은 단정하지 않고 점수에서 제외한다.
    """
    now = now.astimezone(KST)
    if now.weekday() >= 5 or now.time() < dt.time(9):
        # 개장 전 오늘 날짜 응답은 초기화 값이거나 이월 값일 수 있어 인정하지 않는다.
        return as_of == previous_weekday(now.date())
    return as_of == now.date()


def apply_session(result, now):
    """조회 시각 기준으로 현재 세션 여부를 다시 판정한다. 캐시된 응답도 09:00 경계를 넘으면 바뀐다."""
    result = dict(result)
    if result.get("status") != "ok":
        return result
    as_of = dt.date.fromisoformat(result["as_of"])
    result["current"] = session_current(as_of, now)
    # 잠정 여부는 표시 시각이 아니라 조회 시각으로 정한다. 마감 전에 받은 캐시 값은 마감 뒤에도 잠정이다.
    fetched = dt.datetime.fromisoformat(result["fetched_at"]).astimezone(KST)
    result["provisional"] = (result["current"] and as_of == fetched.date()
                             and fetched.time() < FUTURES_CLOSE)
    expiry = result.get("expiry")
    local = now.astimezone(KST)
    expired = expiry is not None and (
        dt.date.fromisoformat(expiry) < local.date()
        or (dt.date.fromisoformat(expiry) == local.date() and local.time() >= FUTURES_EXPIRY_CLOSE))
    if expired:
        # 캐시된 근월물이 만기를 지나면 다음 조회에서 차월물을 고를 때까지 쓰지 않는다.
        result["current"] = result["provisional"] = False
        result["signal"] = None
        result["reason"] = "근월물 만기 경과 — 다음 조회 대기 (점수 제외)"
    elif not result["current"]:
        result["reason"] = "지난 거래일 값 (점수 제외)"
        if "signal" in result:
            result["signal"] = None
    elif "candidate_signal" in result:
        result["signal"] = result["candidate_signal"]
        result["reason"] = result["candidate_reason"]
    else:
        result["reason"] = "현재 세션 값"
    return result


def _futures_unavailable(source, reason, now):
    return {"status": "unavailable", "source": source, "as_of": None,
            "fetched_at": now.isoformat(), "reason": reason, "current": False,
            "foreign": None, "institution": None, "personal": None}


def _contracts(value):
    number = _number(value)
    if number != int(number):
        raise ValueError("계약 수는 정수")
    return int(number)


def parse_naver_futures_flow(integration, now):
    """네이버 선물 integration의 당일 투자자별 순매수(계약)."""
    now = now.astimezone(KST)
    result = _futures_unavailable(NAVER_FUT_URL, "응답 형식 또는 기준일 오류", now)
    try:
        trend = integration["dealTrendInfo"]
        as_of = dt.datetime.strptime(trend["bizdate"], "%Y%m%d").date()
        values = [_contracts(trend[k]) for k in
                  ("foreignValue", "institutionalValue", "personalValue")]
    except (KeyError, TypeError, ValueError, AttributeError):
        return result
    result.update(as_of=as_of.isoformat(), foreign=values[0], institution=values[1],
                  personal=values[2], status="ok")
    return apply_session(result, now)


def parse_daum_futures_flow(rows, now):
    """다음 일별 투자자별 선물 순매수(계약). 응답은 최신 거래일이 첫 행이다."""
    now = now.astimezone(KST)
    result = _futures_unavailable(DAUM_FUT_FLOW_URL, "응답 형식 또는 기준일 오류", now)
    result.update(foreign_5d=None, foreign_20d=None)
    try:
        dates = [dt.date.fromisoformat(str(r["date"])[:10]) for r in rows]
        if not dates or dates != sorted(dates, reverse=True) or len(set(dates)) != len(dates):
            return result
        values = [_contracts(rows[0][k]) for k in
                  ("foreignSettlement", "institutionalSettlement", "privateSettlement")]
    except (KeyError, TypeError, ValueError, AttributeError):
        return result

    def window(n):
        # 창 안에 하루라도 모르는 날이 있으면 합계도 모른다.
        if len(rows) < n:
            return None
        try:
            return sum(_contracts(r["foreignSettlement"]) for r in rows[:n])
        except (KeyError, TypeError, ValueError):
            return None

    result.update(as_of=dates[0].isoformat(), foreign=values[0], institution=values[1],
                  personal=values[2], status="ok", foreign_5d=window(5), foreign_20d=window(20))
    return apply_session(result, now)


def _oi_unavailable(reason, now):
    return {"status": "unavailable", "source": DAUM_FUT_MASTERS_URL, "as_of": None,
            "fetched_at": now.isoformat(), "reason": reason, "current": False,
            "contract": None, "price": None, "change": None, "oi": None,
            "prev_oi": None, "signal": None}


def second_thursday(year, month):
    first = dt.date(year, month, 1)
    return first + dt.timedelta(days=(3 - first.weekday()) % 7 + 7)


def contract_expiry(entry):
    """KOSPI200 분기 선물 월물의 만기일. 이름·코드를 식별할 수 없으면 None."""
    if not isinstance(entry, dict):
        return None
    name, code = str(entry.get("name") or ""), str(entry.get("symbolCode") or "")
    match = re.fullmatch(r"(?:코스피200\s*)?F\s*(20\d{2})(03|06|09|12)", name.strip())
    if not match or not re.fullmatch(r"[A-Za-z0-9]+", code):
        return None
    return second_thursday(int(match[1]), int(match[2]))


def near_month_contract(entries, now):
    """응답 순서에 기대지 않고 이름의 만기월(3·6·9·12월)로 만기 전 가장 가까운 월물을 고른다."""
    now = now.astimezone(KST)
    candidates = []
    for entry in entries or []:
        expiry = contract_expiry(entry)
        if expiry is None:
            continue
        if expiry < now.date() or (expiry == now.date() and now.time() >= FUTURES_EXPIRY_CLOSE):
            continue
        candidates.append((expiry, entry))
    if not candidates:
        return None
    nearest = min(expiry for expiry, _ in candidates)
    matches = [entry for expiry, entry in candidates if expiry == nearest]
    return matches[0] if len(matches) == 1 else None  # 같은 만기 후보가 둘이면 식별할 수 없다.


def parse_daum_open_interest(masters, rows, now):
    """근월물 같은 월물의 연속 두 거래일로 가격 방향과 미결제약정 증감을 결합한다."""
    now = now.astimezone(KST)
    result = _oi_unavailable("응답 형식 또는 기준일 오류", now)
    try:
        near = near_month_contract(masters["data"], now)
        if near is None:
            result["reason"] = "근월물 식별 불가"
            return result
        d0, d1 = (dt.date.fromisoformat(str(r["date"])[:10]) for r in rows[:2])
        if d0 <= d1:
            return result
        oi, prev_oi = _contracts(rows[0]["unsettledVolume"]), _contracts(rows[1]["unsettledVolume"])
        price, prev_price = _number(rows[0]["tradePrice"]), _number(rows[1]["tradePrice"])
        if oi <= 0 or prev_oi <= 0 or price <= 0 or prev_price <= 0:
            return result
        direction = rows[0].get("change")
        if direction is not None and direction not in DIRECTION_FIELD:
            return result
    except (KeyError, IndexError, TypeError, ValueError, AttributeError):
        return result
    # changePrice는 부호 없는 값일 수 있으므로 연속 두 거래일 가격으로 방향을 정한다.
    change = price - prev_price
    result.update(as_of=d0.isoformat(), contract=near.get("name"), price=float(price),
                  change=float(change), oi=oi, prev_oi=prev_oi, status="ok",
                  expiry=contract_expiry(near).isoformat(), candidate_signal=None)
    if d1 != previous_weekday(d0):
        # 휴장 공백이거나 누락된 거래일이면 여러 세션의 증감을 하루 가격 변화와 섞지 않는다.
        result["candidate_reason"] = "연속 거래일 아님 — 조합 판정 불가"
    elif direction is not None and DIRECTION_FIELD[direction] != (change > 0) - (change < 0):
        result["candidate_reason"] = "가격 방향 필드와 가격 차이 불일치 — 조합 판정 불가"
    elif change == 0 or oi == prev_oi:
        result["candidate_reason"] = "가격 또는 미결제약정 보합 — 조합 판정 불가"
    elif Decimal(prev_oi - oi) / prev_oi > OI_ROLLOVER_DROP:
        result["candidate_reason"] = "미결제약정 급감 — 만기 롤오버 가능성, 점수 제외"
    else:
        result["candidate_signal"] = OI_SIGNALS[(change > 0, oi > prev_oi)]
        result["candidate_reason"] = "현재 세션 값"
    return apply_session(result, now)


def _get_json(get, url, **kwargs):
    response = get(url, timeout=5, **kwargs)
    response.raise_for_status()
    return response.json()


def fetch_naver_futures_flow(now, get=None):
    get = get or requests.get
    try:
        data = _get_json(get, NAVER_FUT_URL, headers={
            "User-Agent": "Mozilla/5.0", "Referer": "https://m.stock.naver.com/"})
        return parse_naver_futures_flow(data, now)
    except requests.RequestException:
        return _futures_unavailable(NAVER_FUT_URL, "네이버 연결 또는 HTTP 오류", now)
    except (ValueError, TypeError):
        return _futures_unavailable(NAVER_FUT_URL, "네이버 JSON 응답 오류", now)


def fetch_daum_futures_flow(now, get=None):
    get = get or requests.get
    try:
        data = _get_json(get, DAUM_FUT_FLOW_URL, headers=DAUM_HEADERS, params={
            "page": 1, "perPage": 20, "terms": "days", "pagination": "true"})
        return parse_daum_futures_flow(data.get("data") or [], now)
    except requests.RequestException:
        result = _futures_unavailable(DAUM_FUT_FLOW_URL, "다음 연결 또는 HTTP 오류", now)
    except (ValueError, TypeError, AttributeError):
        result = _futures_unavailable(DAUM_FUT_FLOW_URL, "다음 JSON 응답 오류", now)
    result.update(foreign_5d=None, foreign_20d=None)
    return result


def fetch_daum_open_interest(now, get=None):
    get = get or requests.get
    try:
        masters = _get_json(get, DAUM_FUT_MASTERS_URL, headers=DAUM_HEADERS)
        near = near_month_contract(masters["data"], now)
        if near is None:
            return _oi_unavailable("근월물 식별 불가", now)
        days = _get_json(get, DAUM_FUT_DAYS_URL.format(code=near["symbolCode"]), headers=DAUM_HEADERS,
                         params={"page": 1, "perPage": 2})
        return parse_daum_open_interest(masters, days.get("data") or [], now)
    except requests.RequestException:
        return _oi_unavailable("다음 연결 또는 HTTP 오류", now)
    except (KeyError, IndexError, ValueError, TypeError, AttributeError):
        return _oi_unavailable("다음 JSON 응답 오류", now)


def select_futures_flow(naver, daum):
    """현재 세션 값 중 네이버를 우선하고, 없으면 다음을 쓴다. 둘 다 없으면 None."""
    for snap in (naver, daum):
        if snap.get("status") == "ok" and snap.get("current") and snap.get("foreign") is not None:
            return snap
    return None
