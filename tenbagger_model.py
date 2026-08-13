"""Deterministic tenbagger-candidate scoring.

The model identifies research candidates; it never predicts a tenfold return or
grants an order.  Fundamental quality and entry timing are scored separately so
that a good company is not confused with a good price today.
"""

from __future__ import annotations

import math
from typing import Any


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _between(value: float | None, low: float, high: float) -> bool:
    return value is not None and low <= value <= high


def evaluate_tenbagger_candidate(stock: dict[str, Any], sector: str = "") -> dict[str, Any]:
    """Return a transparent 0-100 research score and independent timing state."""
    region = stock.get("Region") or ("한국" if "한국" in sector else "미국")
    mcap = _number(stock.get("MarketCap"))
    revenue_growth = _number(stock.get("Rev_Growth"))
    earnings_growth = _number(stock.get("Earnings_Growth"))
    operating_margin = _number(stock.get("Op_Margin"))
    roe = _number(stock.get("ROE"))
    rule_40 = _number(stock.get("Rule_of_40"))
    peg = _number(stock.get("PEG"))
    forward_pe = _number(stock.get("Forward_PER"))
    fcf_yield = _number(stock.get("FCF_Yield"))
    roic = _number(stock.get("ROIC"))
    current_ratio = _number(stock.get("Current_Ratio"))
    debt_to_equity = _number(stock.get("Debt_Equity"))
    dilution = _number(stock.get("Dilution_YoY"))
    price = _number(stock.get("Price"))
    ma20 = _number(stock.get("MA20"))
    ma60 = _number(stock.get("MA60"))
    ma120 = _number(stock.get("MA120"))
    w52_position = _number(stock.get("W52_pos"))
    ma20_gap = _number(stock.get("MA20_gap"))
    daily_change = _number(stock.get("Change"))
    turnaround = bool(stock.get("Is_Turnaround"))

    required = [mcap, revenue_growth, price, ma20, ma60, w52_position]
    coverage = sum(value is not None for value in required) / len(required)
    vetoes: list[str] = []
    cautions: list[str] = []

    if stock.get("error"):
        vetoes.append(f"데이터 조회 실패: {stock['error']}")
    if coverage < 0.67:
        vetoes.append("핵심 데이터 충족률 67% 미만")
    if mcap is None or mcap <= 0:
        vetoes.append("시가총액 확인 불가")
    else:
        min_cap, max_cap = ((100_000_000_000, 10_000_000_000_000) if region == "한국"
                            else (300_000_000, 100_000_000_000))
        if mcap < min_cap:
            vetoes.append("유동성·생존 위험이 큰 초소형주")
        elif mcap >= max_cap:
            vetoes.append("현재 규모에서 10배 비대칭이 제한적인 대형주")
    if revenue_growth is None:
        vetoes.append("매출 성장률 확인 불가")
    if daily_change is not None and daily_change <= -8:
        vetoes.append("당일 급락 중인 낙하 칼날")
    if ma20_gap is not None and ma20_gap <= -15:
        vetoes.append("20일선 대비 15% 이상 하회")
    if dilution is not None and dilution >= 0.15:
        vetoes.append("최근 주식 수 15% 이상 희석")

    growth = 0
    if revenue_growth is not None:
        if revenue_growth >= 0.30:
            growth += 15
        elif revenue_growth >= 0.20:
            growth += 12
        elif revenue_growth >= 0.10:
            growth += 7
        elif revenue_growth < 0:
            cautions.append("매출 역성장")
    if earnings_growth is not None:
        if earnings_growth >= 0.30:
            growth += 10
        elif earnings_growth >= 0.15:
            growth += 6
        elif earnings_growth < 0:
            cautions.append("이익 성장률 둔화")
    elif turnaround:
        growth += 6

    profitability = 0
    if operating_margin is not None:
        if operating_margin >= 0.20:
            profitability += 10
        elif operating_margin >= 0.10:
            profitability += 7
        elif operating_margin > 0:
            profitability += 3
        else:
            cautions.append("영업적자")
    if roe is not None:
        profitability += 7 if roe >= 0.15 else 4 if roe >= 0.08 else 0
    if rule_40 is not None:
        profitability += 8 if rule_40 >= 40 else 4 if rule_40 >= 25 else 0

    resilience = 0
    if fcf_yield is not None:
        if fcf_yield > 0:
            resilience += 5
        else:
            cautions.append("잉여현금흐름 적자")
    if roic is not None:
        resilience += 5 if roic >= 0.10 else 2 if roic > 0 else 0
    if current_ratio is not None:
        resilience += 2 if current_ratio >= 1.2 else 0
    if debt_to_equity is not None:
        resilience += 2 if debt_to_equity <= 100 else 0
    if dilution is not None:
        resilience += 1 if dilution <= 0.03 else 0

    valuation = 0
    if _between(peg, 0.01, 1.5):
        valuation += 7
    elif _between(peg, 1.5, 2.5):
        valuation += 3
    if _between(forward_pe, 0.1, 40):
        valuation += 4
    elif _between(forward_pe, 40, 70):
        valuation += 2
    if fcf_yield is not None and fcf_yield >= 0.02:
        valuation += 4

    timing = 0
    if price is not None and ma120 is not None and price >= ma120:
        timing += 6
    if ma20 is not None and ma60 is not None and ma20 >= ma60:
        timing += 5
    if w52_position is not None and w52_position >= 55:
        timing += 5
    if daily_change is None or daily_change > -5:
        timing += 4
    if w52_position is not None and w52_position >= 95 and ma20_gap is not None and ma20_gap > 15:
        timing = max(0, timing - 8)
        cautions.append("52주 고점 부근의 단기 과열")

    quality_score = min(80, growth + profitability + resilience + valuation)
    total_score = min(100, quality_score + timing)
    quality_pass = quality_score >= 48 and growth >= 12 and not vetoes
    eligible = total_score >= 65 and quality_pass

    if vetoes:
        grade = "제외"
    elif total_score >= 80:
        grade = "A"
    elif total_score >= 70:
        grade = "B"
    elif total_score >= 60:
        grade = "관찰"
    else:
        grade = "제외"

    if not quality_pass:
        timing_status = "QUALITY_WAIT"
    elif timing >= 15:
        timing_status = "ENTRY_REVIEW"
    elif "52주 고점 부근의 단기 과열" in cautions:
        timing_status = "PULLBACK_WAIT"
    else:
        timing_status = "TREND_WAIT"

    if "바이오" in sector and (operating_margin is None or operating_margin <= 0):
        cautions.append("임상·허가 데이터는 재무 스코어로 검증할 수 없음")

    return {
        "score": round(total_score, 1),
        "quality_score": round(quality_score, 1),
        "timing_score": round(timing, 1),
        "growth_score": round(growth, 1),
        "grade": grade,
        "eligible": eligible,
        "quality_pass": quality_pass,
        "timing_status": timing_status,
        "data_coverage": round(coverage, 2),
        "vetoes": vetoes,
        "cautions": cautions,
    }


def legacy_tenbagger_label(stock: dict[str, Any], sector: str = "") -> str:
    result = evaluate_tenbagger_candidate(stock, sector)
    if not result["eligible"]:
        return "-"
    if result["grade"] == "A":
        return "🔥 정밀검증 우선 후보"
    return "🌱 텐배거 연구 후보"
