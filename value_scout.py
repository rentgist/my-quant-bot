"""Independent Value Accumulation / Scout layer for ORION.

The Scout layer does not relax the core trend-confirmation signal.  It only
decides whether a small, separately capped value budget may be considered
before the main ORION entry signal is confirmed.  All inputs are close-based
and any allowed change is intended for the next trading session.
"""

from __future__ import annotations

from typing import Any, Optional

import numpy as np


SCOUT_SCORE_MIN = 80.0
SCOUT_AGGREGATE_CAP_PCT = 5.0
SCOUT_PER_ASSET_CAP_PCT = 2.0
SCOUT_TARGET_FRACTION = 0.20


_BROAD_ETF_TICKERS = {
    "SPY",
    "VOO",
    "VTI",
    "IVV",
    "RSP",
    "QQQ",
    "069500",
    "069500.KS",
    "102110",
    "102110.KS",
    "278530",
    "278530.KS",
}


def _safe_float(value: Any, default: float = np.nan) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if np.isfinite(number) else default


def infer_scout_asset_type(stock: dict[str, Any]) -> str:
    """Conservatively identify diversified ETFs; everything else is a stock."""
    ticker = str(stock.get("_ticker") or stock.get("Ticker") or "").upper().strip()
    name = str(stock.get("Name") or "").upper().strip()
    ticker_root = ticker.split(".")[0]
    if ticker in _BROAD_ETF_TICKERS or ticker_root in _BROAD_ETF_TICKERS:
        return "broad_etf"
    if any(brand in name for brand in ("KODEX 200", "TIGER 200", "ACE 200", "RISE 200")):
        return "broad_etf"
    return "quality_stock"


def score_scout_fundamentals(stock: dict[str, Any]) -> dict[str, Any]:
    """Score the existing five ORION quality checks without treating missing as zero."""
    checks: list[tuple[str, bool, bool]] = []

    revenue_growth = _safe_float(stock.get("Rev_Growth"))
    checks.append(("매출성장 20% 이상", np.isfinite(revenue_growth), revenue_growth >= 0.20))

    operating_margin = _safe_float(stock.get("Op_Margin"))
    is_turnaround = bool(stock.get("Is_Turnaround", False))
    operating_available = np.isfinite(operating_margin) or is_turnaround
    operating_passed = (np.isfinite(operating_margin) and operating_margin >= 0.10) or is_turnaround
    checks.append(("영업이익률 10% 이상 또는 흑자전환", operating_available, operating_passed))

    roe = _safe_float(stock.get("ROE"))
    checks.append(("ROE 5% 이상", np.isfinite(roe), roe >= 0.05))

    peg = _safe_float(stock.get("PEG"))
    checks.append(("PEG 0~1.5", np.isfinite(peg), 0 < peg <= 1.5))

    per = _safe_float(stock.get("PER"))
    checks.append(("PER 0~30", np.isfinite(per), 0 < per < 30))

    available = sum(1 for _, is_available, _ in checks if is_available)
    score = sum(1 for _, is_available, passed in checks if is_available and passed)
    quality_confirmed = available >= 4 and score >= 4
    details = [
        f"{'✅' if passed else '❌'} {label}"
        if is_available
        else f"⚪ {label} 데이터 없음"
        for label, is_available, passed in checks
    ]

    if quality_confirmed:
        status = "QUALITY_CONFIRMED"
        label = f"펀더멘털 확인 {score}/5"
    elif available < 4:
        status = "DATA_INCOMPLETE"
        label = f"펀더멘털 데이터 부족 {available}/5"
    else:
        status = "QUALITY_NOT_CONFIRMED"
        label = f"펀더멘털 미확인 {score}/5"

    return {
        "score": score,
        "available": available,
        "quality_confirmed": quality_confirmed,
        "status": status,
        "label": label,
        "details": details,
    }


def evaluate_scout_market_gate(
    *,
    bottom_score: float,
    data_valid: bool,
    falling_knife: bool,
    systemic_risk: bool,
    trend_confirmed: bool,
) -> dict[str, Any]:
    """Open candidate screening without turning a high bottom score into an order."""
    score = _safe_float(bottom_score, 0.0)
    if not data_valid:
        return {
            "state": "DATA_BLOCKED",
            "label": "⚫ Scout 판정 중단",
            "reason": "필수 시장 데이터가 부족하거나 오래됐습니다.",
            "candidate_screening_allowed": False,
        }
    if falling_knife:
        return {
            "state": "FALLING_KNIFE",
            "label": "🔴 Falling Knife",
            "reason": "낙하 속도가 멈추지 않아 Scout도 0%입니다.",
            "candidate_screening_allowed": False,
        }
    if systemic_risk:
        return {
            "state": "SYSTEMIC_RISK",
            "label": "🔴 시스템 위험 차단",
            "reason": "시장·신용 위험이 높아 Value Zone보다 자본 보존이 우선입니다.",
            "candidate_screening_allowed": False,
        }
    if trend_confirmed:
        return {
            "state": "TREND_HANDOFF",
            "label": "🟡 본대 규칙으로 전환",
            "reason": "추세 확인이 끝났으므로 Scout가 아니라 기존 ORION 분할 규칙을 적용합니다.",
            "candidate_screening_allowed": False,
        }
    if score < SCOUT_SCORE_MIN:
        return {
            "state": "SCORE_WAIT",
            "label": "⚪ Value Zone 대기",
            "reason": f"바닥점수 {score:.0f}점으로 Scout 기준 {SCOUT_SCORE_MIN:.0f}점에 미달합니다.",
            "candidate_screening_allowed": False,
        }
    return {
        "state": "CANDIDATE_SCREENING",
        "label": "🟠 Value Zone · 후보 선별 허용",
        "reason": "본대 진입 전 우량 자산의 Scout 적격성만 검토할 수 있습니다. 아직 주문 신호는 아닙니다.",
        "candidate_screening_allowed": True,
    }


def calculate_scout_budget(
    *,
    target_weight_pct: float,
    existing_asset_scout_pct: float = 0.0,
    aggregate_scout_pct: float = 0.0,
    total_assets: Optional[float] = None,
) -> dict[str, Any]:
    """Apply per-asset, aggregate, and target-position Scout caps."""
    target = float(np.clip(_safe_float(target_weight_pct, 0.0), 0.0, 100.0))
    existing_asset = float(np.clip(_safe_float(existing_asset_scout_pct, 0.0), 0.0, 100.0))
    aggregate = float(np.clip(_safe_float(aggregate_scout_pct, 0.0), 0.0, 100.0))

    asset_cap = min(target * SCOUT_TARGET_FRACTION, SCOUT_PER_ASSET_CAP_PCT)
    remaining_asset = max(asset_cap - existing_asset, 0.0)
    remaining_aggregate = max(SCOUT_AGGREGATE_CAP_PCT - aggregate, 0.0)
    max_new_weight = min(remaining_asset, remaining_aggregate, 5.0)

    assets = _safe_float(total_assets)
    max_order_amount = (
        max(assets, 0.0) * max_new_weight / 100
        if np.isfinite(assets)
        else None
    )
    return {
        "asset_cap_pct": round(asset_cap, 2),
        "aggregate_cap_pct": SCOUT_AGGREGATE_CAP_PCT,
        "max_new_weight_pct": round(max_new_weight, 2),
        "max_order_amount": round(max_order_amount, 1) if max_order_amount is not None else None,
    }


def evaluate_scout_candidate(
    stock: dict[str, Any],
    market_gate: dict[str, Any],
    *,
    target_weight_pct: float = 10.0,
    existing_asset_scout_pct: float = 0.0,
    aggregate_scout_pct: float = 0.0,
    total_assets: Optional[float] = None,
) -> dict[str, Any]:
    """Evaluate one candidate after the independent market gate is open."""
    asset_type = infer_scout_asset_type(stock)
    fundamentals = score_scout_fundamentals(stock)
    diversified_etf = asset_type == "broad_etf"
    quality_confirmed = diversified_etf or fundamentals["quality_confirmed"]

    drawdown = _safe_float(stock.get("Gap_High"))
    daily_change = _safe_float(stock.get("Change"), 0.0)
    price = _safe_float(stock.get("Price"))
    ma5 = _safe_float(stock.get("MA5"))
    ma5_gap = (price / ma5 - 1) * 100 if np.isfinite(price) and np.isfinite(ma5) and ma5 else np.nan
    rsi = _safe_float(stock.get("RSI_14"))
    ma20_gap = _safe_float(stock.get("MA20_gap"))

    stock_falling_knife = daily_change <= -4.0 or (np.isfinite(ma5_gap) and ma5_gap <= -4.0)
    overheat = (np.isfinite(rsi) and rsi >= 70.0) or (np.isfinite(ma20_gap) and ma20_gap >= 12.0)
    drawdown_threshold = -15.0 if diversified_etf else -25.0
    value_zone = np.isfinite(drawdown) and drawdown <= drawdown_threshold
    budget = calculate_scout_budget(
        target_weight_pct=target_weight_pct,
        existing_asset_scout_pct=existing_asset_scout_pct,
        aggregate_scout_pct=aggregate_scout_pct,
        total_assets=total_assets,
    )

    state = "SCOUT_ALLOWED"
    label = "🟠 Scout 허용"
    reason = "시장·가치·품질 조건을 통과했습니다. 별도 Scout 예산 안에서만 검토합니다."

    if not market_gate.get("candidate_screening_allowed", False):
        state = "MARKET_BLOCKED"
        label = "⛔ Scout 0%"
        reason = market_gate.get("reason", "시장 게이트가 닫혀 있습니다.")
    elif stock_falling_knife:
        state = "FALLING_KNIFE"
        label = "🔴 Scout 0%"
        reason = "종목 자체가 낙하 중입니다. 종가 기준 급락·5일선 이격이 진정될 때까지 기다립니다."
    elif overheat:
        state = "OVERHEAT"
        label = "🔥 Scout 0%"
        reason = "RSI 또는 20일선 이격이 과열입니다. Value Scout로 추격하지 않습니다."
    elif not quality_confirmed:
        state = "QUALITY_REVIEW"
        label = "⚪ 펀더멘털 확인 필요"
        reason = "개별 종목은 5개 품질 항목 중 4개 이상과 충분한 데이터가 확인돼야 합니다."
    elif not value_zone:
        state = "VALUE_WAIT"
        label = "⚪ 가격 매력 대기"
        reason = f"52주 고점 대비 낙폭이 Scout 기준 {drawdown_threshold:.0f}%에 도달하지 않았습니다."
    elif budget["max_new_weight_pct"] <= 0:
        state = "BUDGET_FULL"
        label = "🔵 Scout 예산 소진"
        reason = "종목별 또는 전체 Scout 한도에 도달했습니다. 추가 주문은 0%입니다."

    allowed = state == "SCOUT_ALLOWED"
    return {
        "state": state,
        "label": label,
        "reason": reason,
        "allowed": allowed,
        "asset_type": asset_type,
        "drawdown_pct": round(drawdown, 1) if np.isfinite(drawdown) else None,
        "drawdown_threshold_pct": drawdown_threshold,
        "stock_falling_knife": stock_falling_knife,
        "overheat": overheat,
        "fundamentals": fundamentals,
        "budget": budget,
        "max_new_weight_pct": budget["max_new_weight_pct"] if allowed else 0.0,
        "max_order_amount": budget["max_order_amount"] if allowed else 0.0 if total_assets is not None else None,
        "execution": "종가 확인 후 다음 거래일 분할 실행",
        "invalidation": "기업가치 훼손, 시장 위험 차단, 낙하 칼날 재발, 전체 Scout 5%p 소진 중 하나가 확인되면 신규 Scout를 중단합니다.",
    }
