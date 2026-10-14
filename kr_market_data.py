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
