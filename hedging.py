"""Pure hedge-policy, sizing, and backtest helpers.

The dashboard deliberately keeps these functions independent from Streamlit so
the trading rules can be unit-tested without loading network data or UI state.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class HedgeHorizon:
    key: str
    label: str
    min_days: int
    max_days: int
    product: str
    leverage: float
    entry_threshold: int
    max_allocation: float
    description: str


HEDGE_HORIZONS: dict[str, HedgeHorizon] = {
    "tactical": HedgeHorizon(
        key="tactical",
        label="초단기 방어 (1~3거래일)",
        min_days=1,
        max_days=3,
        product="KODEX 200선물인버스2X (252670)",
        leverage=2.0,
        entry_threshold=75,
        max_allocation=0.10,
        description="급락이 시작되기 전 또는 초기의 연속 하락만 방어합니다. 과매도 추격 진입은 차단합니다.",
    ),
    "short": HedgeHorizon(
        key="short",
        label="단기 방어 (4~10거래일)",
        min_days=4,
        max_days=10,
        product="KODEX 인버스 (114800)",
        leverage=1.0,
        entry_threshold=70,
        max_allocation=0.20,
        description="2배 상품 대신 1배 인버스를 사용해 일간 재설정과 휩쏘 손실을 낮춥니다.",
    ),
    "defensive": HedgeHorizon(
        key="defensive",
        label="중단기 위험축소 (11~60거래일)",
        min_days=11,
        max_days=60,
        product="현금 비중 확대 + 필요 시 1배 인버스",
        leverage=1.0,
        entry_threshold=65,
        max_allocation=0.30,
        description="레버리지 상품을 사용하지 않고 주식 베타 축소를 우선합니다.",
    ),
}


@dataclass(frozen=True)
class HedgeDecision:
    action: str
    headline: str
    reason: str
    product: str
    max_holding_days: int
    allow_new_entry: bool
    urgency: str


def get_horizon_policy(horizon_key: str) -> HedgeHorizon:
    if horizon_key not in HEDGE_HORIZONS:
        raise ValueError(f"Unknown hedge horizon: {horizon_key}")
    return HEDGE_HORIZONS[horizon_key]


def evaluate_hedge_state(
    *,
    horizon_key: str,
    position_status: str,
    entry_score: float,
    exit_score: float,
    rsi: float | None,
    foreign_futures: float | None,
    holding_days: int = 0,
    data_quality: str = "live",
    entry_threshold: float | None = None,
    exit_threshold: float | None = None,
    max_holding_days: int | None = None,
    validation_passed: bool = True,
) -> HedgeDecision:
    """Return a position-aware hedge decision.

    ``position_status`` must be one of ``none``, ``inverse1x``, or
    ``inverse2x``.  A positive foreign-futures number is treated as a potential
    rebound/short-cover warning, not as a fresh short entry.
    """

    policy = get_horizon_policy(horizon_key)
    entry_gate = (
        float(policy.entry_threshold)
        if entry_threshold is None
        else float(entry_threshold)
    )
    exit_gate = 35.0 if exit_threshold is None else float(exit_threshold)
    max_days = (
        policy.max_days
        if max_holding_days is None
        else max(1, int(max_holding_days))
    )
    if position_status not in {"none", "inverse1x", "inverse2x"}:
        raise ValueError(f"Unknown position status: {position_status}")

    rsi_value = None if rsi is None or pd.isna(rsi) else float(rsi)
    futures_value = (
        None
        if foreign_futures is None or pd.isna(foreign_futures)
        else float(foreign_futures)
    )
    is_holding = position_status != "none"

    if is_holding:
        if position_status == "inverse2x" and horizon_key != "tactical":
            return HedgeDecision(
                action="EXIT_2X_HORIZON",
                headline="2배 인버스 축소·청산",
                reason="선택한 기간은 2배 인버스의 일간 재설정 위험과 맞지 않습니다. 1배 인버스 또는 현금 방어로 전환하십시오.",
                product=policy.product,
                max_holding_days=max_days,
                allow_new_entry=False,
                urgency="high",
            )
        if holding_days >= max_days:
            return HedgeDecision(
                action="EXIT_TIME",
                headline="보유기간 만료 — 청산",
                reason=f"선택한 전략의 최대 보유기간 {max_days}거래일에 도달했습니다. 재진입은 새 신호로 다시 판단해야 합니다.",
                product=policy.product,
                max_holding_days=max_days,
                allow_new_entry=False,
                urgency="high",
            )
        if exit_score >= min(exit_gate + 25, 70):
            return HedgeDecision(
                action="EXIT",
                headline="인버스 전량 청산 검토",
                reason=f"청산 점수 {exit_score:.0f}점으로 반등·공포 피크아웃 조건이 강하게 겹쳤습니다.",
                product=policy.product,
                max_holding_days=max_days,
                allow_new_entry=False,
                urgency="high",
            )
        if (
            exit_score >= exit_gate
            or (rsi_value is not None and rsi_value <= 32)
            or (futures_value is not None and futures_value > 0)
        ):
            return HedgeDecision(
                action="REDUCE",
                headline="인버스 50% 축소",
                reason="과매도 또는 외국인 선물 매수 전환이 확인돼 급반등 위험이 커졌습니다. 남은 물량은 시간 제한을 적용합니다.",
                product=policy.product,
                max_holding_days=max_days,
                allow_new_entry=False,
                urgency="medium",
            )
        return HedgeDecision(
            action="HOLD",
            headline="기존 헷지 유지",
            reason=f"청산 조건은 아직 부족합니다. 단, 최대 {max_days}거래일까지만 유지합니다.",
            product=policy.product,
            max_holding_days=max_days,
            allow_new_entry=False,
            urgency="low",
        )

    if data_quality == "unavailable":
        return HedgeDecision(
            action="BLOCK_DATA",
            headline="신규 헷지 금지 — 데이터 확인 필요",
            reason="핵심 변동성 또는 가격 데이터가 없어 레버리지 신호를 계산할 수 없습니다.",
            product=policy.product,
            max_holding_days=max_days,
            allow_new_entry=False,
            urgency="high",
        )
    if horizon_key != "defensive" and not validation_passed:
        return HedgeDecision(
            action="BLOCK_VALIDATION",
            headline="인버스 신규 진입 사용 중지 — 백테스트 탈락",
            reason="최근 별도 검증에서 평균수익과 계좌 손실 방어 기준을 함께 통과하지 못했습니다. 시장 점수와 관계없이 신규 매수하지 않습니다.",
            product=policy.product,
            max_holding_days=max_days,
            allow_new_entry=False,
            urgency="high",
        )
    if data_quality == "proxy" and horizon_key == "tactical":
        return HedgeDecision(
            action="BLOCK_PROXY_2X",
            headline="2배 인버스 금지 — VKOSPI 프록시 사용 중",
            reason="실제 옵션 내재변동성이 아닌 후행 실현변동성 프록시로는 초단기 2배 진입을 허용하지 않습니다.",
            product=policy.product,
            max_holding_days=max_days,
            allow_new_entry=False,
            urgency="high",
        )

    rebound_risk = (
        (rsi_value is not None and rsi_value <= 32)
        or (futures_value is not None and futures_value > 0)
    )
    if rebound_risk:
        return HedgeDecision(
            action="WAIT_REVERSAL",
            headline="신규 인버스 보류 — 급반등 위험",
            reason="극단적 과매도 또는 외국인 선물 순매수 전환이 나타났습니다. 폭락 후 추격 숏보다 다음 거래일 확인이 우선입니다.",
            product=policy.product,
            max_holding_days=max_days,
            allow_new_entry=False,
            urgency="medium",
        )

    if entry_score < entry_gate:
        return HedgeDecision(
            action="WAIT",
            headline="신규 헷지 대기",
            reason=f"진입 점수 {entry_score:.0f}점이 {entry_gate:.0f}점 기준에 미달합니다.",
            product=policy.product,
            max_holding_days=max_days,
            allow_new_entry=False,
            urgency="low",
        )

    if horizon_key == "defensive":
        return HedgeDecision(
            action="REDUCE_BETA",
            headline="중단기 위험자산 베타 축소",
            reason="중단기 방어에서는 2배 인버스 대신 현금 확대와 1배 인버스를 조합합니다.",
            product=policy.product,
            max_holding_days=max_days,
            allow_new_entry=True,
            urgency="medium",
        )

    return HedgeDecision(
        action="ENTER_PARTIAL",
        headline="보호성 헷지 1차 진입",
        reason=f"{policy.label} 기준을 충족했습니다. 정책 상한의 50%만 먼저 진입하고 다음 거래일에 재평가합니다.",
        product=policy.product,
        max_holding_days=max_days,
        allow_new_entry=True,
        urgency="medium",
    )


def calculate_beta_hedge_size(
    *,
    total_assets: float,
    equity_weight: float,
    portfolio_beta: float,
    target_coverage: float,
    horizon_key: str,
) -> dict[str, float]:
    """Size a hedge from beta exposure instead of an assumed Kelly win rate."""

    policy = get_horizon_policy(horizon_key)
    total_assets = max(float(total_assets), 0.0)
    equity_weight = float(np.clip(equity_weight, 0.0, 1.0))
    portfolio_beta = max(float(portfolio_beta), 0.0)
    target_coverage = float(np.clip(target_coverage, 0.0, 1.0))

    beta_exposure = total_assets * equity_weight * portfolio_beta
    target_notional = beta_exposure * target_coverage
    raw_allocation = target_notional / policy.leverage
    policy_cap = total_assets * policy.max_allocation
    recommended_allocation = min(raw_allocation, policy_cap)
    achieved_coverage = (
        recommended_allocation * policy.leverage / beta_exposure
        if beta_exposure > 0
        else 0.0
    )

    return {
        "beta_exposure": beta_exposure,
        "target_notional": target_notional,
        "raw_allocation": raw_allocation,
        "policy_cap": policy_cap,
        "recommended_allocation": recommended_allocation,
        "achieved_coverage": achieved_coverage,
        "max_allocation_pct": policy.max_allocation,
        "leverage": policy.leverage,
    }


def build_plain_action_plan(
    *,
    decision: HedgeDecision,
    position_status: str,
    holding_amount: float,
    recommended_allocation: float,
    policy_cap: float,
    entry_score: float,
    entry_threshold: float,
    exit_score: float,
    exit_threshold: float,
) -> dict[str, Any]:
    """Translate an engine decision into an amount-first user checklist."""

    holding_amount = max(float(holding_amount), 0.0)
    recommended_allocation = max(float(recommended_allocation), 0.0)
    policy_cap = max(float(policy_cap), 0.0)
    reserve_amount = min(recommended_allocation, policy_cap)
    remaining_days = max(decision.max_holding_days, 1)
    next_check = "다음 거래일 종가 후"

    if decision.action == "ENTER_PARTIAL":
        first_order = reserve_amount * 0.5
        title = f"오늘은 {decision.product}을 {first_order:,.0f}만원만 1차 매수하세요"
        amount_label = "오늘 주문 상한"
        amount_value = f"{first_order:,.0f}만원"
        steps = [
            f"한 번에 전부 사지 말고 계산된 한도 {reserve_amount:,.0f}만원의 절반만 매수합니다.",
            "다음 거래일 종가 후 신호가 유지될 때만 나머지 절반을 검토합니다.",
            f"어떤 경우에도 {decision.max_holding_days}거래일을 넘겨 보유하지 않습니다.",
        ]
    elif decision.action == "REDUCE_BETA" and position_status == "none":
        title = f"오늘은 국내 주식을 최대 {reserve_amount:,.0f}만원 줄여 현금으로 옮기세요"
        amount_label = "현금 전환 상한"
        amount_value = f"{reserve_amount:,.0f}만원"
        steps = [
            "수익이 많이 난 종목과 시장 민감도가 높은 종목부터 나눠서 줄입니다.",
            "2배 인버스는 사용하지 않습니다.",
            "하루에 전부 바꾸지 말고 2~3회로 나눠 실행합니다.",
        ]
    elif decision.action == "REDUCE":
        reduce_amount = holding_amount * 0.5
        title = (
            f"오늘은 보유 인버스 {reduce_amount:,.0f}만원을 매도하세요"
            if holding_amount > 0
            else "오늘은 보유 인버스의 50%를 매도하세요"
        )
        amount_label = "오늘 줄일 비중"
        amount_value = f"{reduce_amount:,.0f}만원" if holding_amount > 0 else "보유량의 50%"
        steps = [
            "장 시작 직후 추격 주문보다 가격이 안정된 뒤 분할 매도합니다.",
            "남은 물량도 최대 보유기간을 넘기지 않습니다.",
            "신규 인버스 추가매수는 하지 않습니다.",
        ]
    elif decision.action in {"EXIT", "EXIT_TIME", "EXIT_2X_HORIZON"}:
        title = (
            f"오늘은 보유 인버스 {holding_amount:,.0f}만원을 전부 정리하세요"
            if holding_amount > 0
            else "오늘은 보유 인버스를 전부 정리하세요"
        )
        amount_label = "오늘 정리할 금액"
        amount_value = f"{holding_amount:,.0f}만원" if holding_amount > 0 else "보유량 전부"
        steps = [
            "새 인버스로 바로 갈아타지 않습니다.",
            "매도 후 현금으로 두고 다음 거래일 종가에 다시 판단합니다.",
            "손실 만회를 위한 비중 확대는 하지 않습니다.",
        ]
    elif decision.action == "HOLD":
        title = "오늘은 기존 인버스를 추가매수 없이 그대로 유지하세요"
        amount_label = "오늘 추가 주문"
        amount_value = "0원"
        steps = [
            "보유 수량은 늘리지 않습니다.",
            f"최대 {remaining_days}거래일 제한을 지킵니다.",
            f"청산 점수가 {exit_threshold:.0f}점 이상이면 절반을 줄입니다.",
        ]
    elif decision.action == "BLOCK_VALIDATION":
        title = "오늘 인버스 신규 주문은 0원입니다"
        amount_label = "오늘 신규 주문"
        amount_value = "0원"
        next_check = "전략 재검증 후"
        steps = [
            "평균수익 또는 계좌 손실 방어 기준을 통과하지 못해 신규 매수하지 않습니다.",
            "하락방어 점수는 시장이 위험한 정도이며 인버스 매수 허가가 아닙니다.",
            "전략이 새 검증을 통과할 때까지 현금으로 유지합니다.",
        ]
    else:
        title = "오늘은 인버스를 새로 사지 마세요"
        amount_label = "오늘 신규 주문"
        amount_value = "0원"
        steps = [
            "인버스·곱버스 신규 주문은 넣지 않습니다.",
            f"인버스 최대 한도는 {policy_cap:,.0f}만원이지만 현재 배정은 0원입니다.",
            "다음 거래일 종가 후 조건을 다시 확인합니다.",
        ]

    return {
        "title": title,
        "amount_label": amount_label,
        "amount_value": amount_value,
        "steps": steps,
        "next_check": next_check,
        "entry_progress": (
            min(max(float(entry_score), 0.0) / max(float(entry_threshold), 1.0), 1.0)
        ),
        "exit_progress": (
            min(max(float(exit_score), 0.0) / max(float(exit_threshold), 1.0), 1.0)
        ),
    }


def build_inverse_validation_summary(
    optimization: dict[str, Any],
) -> dict[str, Any]:
    """Turn holdout metrics into a plain-language use/stop gate."""

    if (
        optimization.get("status") != "ok"
        or not isinstance(optimization.get("holdout_metrics"), dict)
    ):
        return {
            "state": "UNAVAILABLE",
            "usable": False,
            "label": "사용 중지",
            "headline": "검증 자료가 부족해 이 전략을 사용하지 않습니다",
            "reason": "과거 결과를 확인할 수 없으면 인버스 신규 주문은 0원입니다.",
            "checks": [],
        }

    metrics = optimization["holdout_metrics"]
    trades = int(metrics.get("trades", 0))
    average = float(metrics.get("avg_trade_return", 0.0))
    profit_factor = float(metrics.get("profit_factor", 0.0))
    mdd_improvement = float(metrics.get("mdd_improvement", 0.0))
    checks = [
        {
            "label": "거래당 평균",
            "value": f"{average:+.2f}%",
            "passed": average > 0,
            "rule": "0%보다 커야 사용",
        },
        {
            "label": "수익/손실 비율",
            "value": f"{profit_factor:.2f}",
            "passed": profit_factor > 1,
            "rule": "1.00보다 커야 사용",
        },
        {
            "label": "계좌 낙폭 개선",
            "value": f"{mdd_improvement:+.1f}%p",
            "passed": mdd_improvement > 0,
            "rule": "0%p보다 커야 사용",
        },
        {
            "label": "검증 거래",
            "value": f"{trades}회",
            "passed": trades >= 3,
            "rule": "최소 3회 필요",
        },
    ]
    usable = bool(optimization.get("passed", False)) and all(
        check["passed"] for check in checks
    )

    if usable:
        return {
            "state": "PASSED",
            "usable": True,
            "label": "조건부 사용 가능",
            "headline": "과거 검증을 통과했습니다 — 오늘 조건을 추가 확인하세요",
            "reason": "백테스트 통과는 매수 확정이 아닙니다. 오늘 시장 조건까지 통과할 때만 소액 분할 진입합니다.",
            "checks": checks,
        }

    if average <= 0:
        reason = (
            f"최근 별도 검증에서 거래당 평균이 {average:+.2f}%였습니다. "
            "평균적으로 손해 본 전략이므로 신규 진입에 사용하지 않습니다."
        )
    elif profit_factor <= 1:
        reason = (
            f"벌었을 때와 잃었을 때를 합산한 수익/손실 비율이 {profit_factor:.2f}로 "
            "기준 1.00을 넘지 못했습니다."
        )
    elif mdd_improvement <= 0:
        reason = (
            f"인버스를 사용해도 계좌 최대낙폭 개선이 {mdd_improvement:+.1f}%p로 "
            "실제 방어 효과가 확인되지 않았습니다."
        )
    else:
        reason = f"검증 거래가 {trades}회뿐이라 전략을 사용할 근거가 부족합니다."

    return {
        "state": "FAILED",
        "usable": False,
        "label": "사용 중지",
        "headline": "백테스트 탈락 — 오늘 인버스 신규 주문은 0원입니다",
        "reason": reason,
        "checks": checks,
    }


def _close_series(df: pd.DataFrame | None, name: str) -> pd.Series:
    if df is None or df.empty or "Close" not in df.columns:
        return pd.Series(dtype=float, name=name)
    series = pd.to_numeric(df["Close"], errors="coerce").dropna().copy()
    series.index = pd.to_datetime(series.index).tz_localize(None).normalize()
    series = series[~series.index.duplicated(keep="last")].sort_index()
    series.name = name
    return series


def _open_series(df: pd.DataFrame | None, name: str) -> pd.Series:
    if df is None or df.empty:
        return pd.Series(dtype=float, name=name)
    column = "Open" if "Open" in df.columns else "Close"
    series = pd.to_numeric(df[column], errors="coerce").dropna().copy()
    series.index = pd.to_datetime(series.index).tz_localize(None).normalize()
    series = series[~series.index.duplicated(keep="last")].sort_index()
    series.name = name
    return series


def build_daily_hedge_features(
    kospi_hist: pd.DataFrame,
    vkospi_hist: pd.DataFrame,
    usdkrw_hist: pd.DataFrame,
) -> pd.DataFrame:
    """Build close-only signals that can be reproduced historically."""

    df = pd.concat(
        [
            _close_series(kospi_hist, "KOSPI"),
            _close_series(vkospi_hist, "VKOSPI"),
            _close_series(usdkrw_hist, "USDKRW"),
        ],
        axis=1,
    ).ffill().dropna()
    if len(df) < 80:
        return pd.DataFrame()

    close = df["KOSPI"]
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    df["RSI"] = 100 - (100 / (1 + rs))
    df["MA5"] = close.rolling(5).mean()
    df["MA20"] = close.rolling(20).mean()
    df["RET5"] = close.pct_change(5) * 100
    df["USDKRW_Z60"] = (
        (df["USDKRW"] - df["USDKRW"].rolling(60).mean())
        / df["USDKRW"].rolling(60).std().replace(0, np.nan)
    )
    df["USDKRW_RET5"] = df["USDKRW"].pct_change(5) * 100
    df["VK_5D_HIGH"] = df["VKOSPI"].rolling(5).max()
    df["VK_RANK252"] = df["VKOSPI"].rolling(252, min_periods=60).apply(
        lambda values: float(np.mean(values <= values[-1])),
        raw=True,
    )

    entry_score = np.zeros(len(df))
    entry_score += np.where(close < df["MA5"], 20, 0)
    entry_score += np.where(close < df["MA20"], 10, 0)
    entry_score += np.where(df["RET5"] <= -5, 15, np.where(df["RET5"] <= -2, 8, 0))
    entry_score += np.where(
        df["VK_RANK252"] >= 0.95,
        30,
        np.where(df["VK_RANK252"] >= 0.85, 15, 0),
    )
    entry_score += np.where(
        df["USDKRW_Z60"] >= 2.0,
        20,
        np.where(df["USDKRW_Z60"] >= 1.0, 10, 0),
    )
    df["EntryScore"] = np.clip(entry_score, 0, 100)

    exit_score = np.zeros(len(df))
    exit_score += np.where(df["RSI"] < 25, 40, np.where(df["RSI"] < 32, 20, 0))
    exit_score += np.where(close > df["MA5"], 25, 0)
    exit_score += np.where(df["VKOSPI"] < df["VK_5D_HIGH"] * 0.92, 25, 0)
    exit_score += np.where(df["USDKRW_RET5"] < -0.5, 10, 0)
    df["ExitScore"] = np.clip(exit_score, 0, 100)

    return df.dropna(
        subset=["RSI", "MA5", "MA20", "USDKRW_Z60", "VK_RANK252"]
    )


def _max_drawdown(equity: pd.Series) -> float:
    if equity.empty:
        return 0.0
    drawdown = equity / equity.cummax() - 1
    return float(drawdown.min() * 100)


def run_hedge_backtest(
    *,
    kospi_hist: pd.DataFrame,
    vkospi_hist: pd.DataFrame,
    usdkrw_hist: pd.DataFrame,
    inverse1x_hist: pd.DataFrame,
    inverse2x_hist: pd.DataFrame,
    horizon_key: str,
    transaction_cost_bps: float = 15.0,
    entry_threshold: float | None = None,
    exit_threshold: float = 35.0,
    max_holding_days: int | None = None,
    evaluation_start: pd.Timestamp | str | None = None,
    evaluation_end: pd.Timestamp | str | None = None,
) -> dict[str, Any]:
    """Backtest a hedge overlay using next-session open-to-open returns.

    Signals are computed at session ``t`` close.  The position changes at the
    next session's open and earns the following open-to-open ETF return.  This
    avoids filling a trade at a close that was already used to calculate the
    signal.
    """

    policy = get_horizon_policy(horizon_key)
    entry_gate = (
        float(policy.entry_threshold)
        if entry_threshold is None
        else float(entry_threshold)
    )
    exit_gate = float(exit_threshold)
    max_days = (
        policy.max_days
        if max_holding_days is None
        else max(1, int(max_holding_days))
    )
    features = build_daily_hedge_features(kospi_hist, vkospi_hist, usdkrw_hist)
    etf_hist = inverse2x_hist if horizon_key == "tactical" else inverse1x_hist
    etf_open = _open_series(etf_hist, "ETF_OPEN")
    kospi_open = _open_series(kospi_hist, "KOSPI_OPEN")

    df = features.join(etf_open, how="inner").join(kospi_open, how="inner")
    if len(df) < 120:
        return {
            "status": "insufficient_data",
            "message": f"{policy.product} 백테스트에 필요한 공통 거래일 데이터가 부족합니다.",
            "policy": asdict(policy),
        }

    df["ETF_FWD_RET"] = df["ETF_OPEN"].shift(-2) / df["ETF_OPEN"].shift(-1) - 1
    df["KOSPI_FWD_RET"] = (
        df["KOSPI_OPEN"].shift(-2) / df["KOSPI_OPEN"].shift(-1) - 1
    )
    df = df.dropna(subset=["ETF_FWD_RET", "KOSPI_FWD_RET"])
    if evaluation_start is not None:
        df = df.loc[df.index >= pd.Timestamp(evaluation_start)]
    if evaluation_end is not None:
        df = df.loc[df.index <= pd.Timestamp(evaluation_end)]
    if len(df) < 20:
        return {
            "status": "insufficient_data",
            "message": "선택한 검증 구간의 거래일 데이터가 부족합니다.",
            "policy": asdict(policy),
        }

    cost = max(float(transaction_cost_bps), 0.0) / 10_000
    allocation = policy.max_allocation
    position = False
    holding_days = 0
    trade_growth = 1.0
    trade_start: pd.Timestamp | None = None
    trades: list[dict[str, Any]] = []
    hedged_equity = 1.0
    unhedged_equity = 1.0
    curve_rows: list[dict[str, Any]] = []

    for date, row in df.iterrows():
        entry_cost = 0.0
        exit_cost = 0.0
        exited_this_signal = False

        if position:
            should_exit = (
                row["ExitScore"] >= exit_gate
                or holding_days >= max_days
            )
            if should_exit:
                exit_cost = cost
                trade_growth *= 1 - cost
                trades.append(
                    {
                        "EntryDate": trade_start,
                        "ExitSignalDate": date,
                        "HoldingDays": holding_days,
                        "ReturnPct": (trade_growth - 1) * 100,
                    }
                )
                position = False
                holding_days = 0
                trade_growth = 1.0
                trade_start = None
                exited_this_signal = True

        if not position and not exited_this_signal:
            panic_reversal = row["RSI"] <= 32
            if row["EntryScore"] >= entry_gate and not panic_reversal:
                position = True
                holding_days = 0
                trade_start = date
                entry_cost = cost
                trade_growth = 1 - cost

        etf_return = float(row["ETF_FWD_RET"]) if position else 0.0
        kospi_return = float(row["KOSPI_FWD_RET"])
        if position:
            holding_days += 1
            trade_growth *= 1 + etf_return

        overlay_return = (
            kospi_return
            + allocation * etf_return
            - allocation * (entry_cost + exit_cost)
        )
        hedged_equity *= 1 + overlay_return
        unhedged_equity *= 1 + kospi_return
        curve_rows.append(
            {
                "Date": date,
                "무헷지": unhedged_equity,
                "헷지 적용": hedged_equity,
                "Position": int(position),
                "EntryScore": float(row["EntryScore"]),
                "ExitScore": float(row["ExitScore"]),
            }
        )

    if position:
        trade_growth *= 1 - cost
        hedged_equity *= 1 - allocation * cost
        if curve_rows:
            curve_rows[-1]["헷지 적용"] = hedged_equity
            curve_rows[-1]["Position"] = 0
        trades.append(
            {
                "EntryDate": trade_start,
                "ExitSignalDate": df.index[-1],
                "HoldingDays": holding_days,
                "ReturnPct": (trade_growth - 1) * 100,
            }
        )

    curve = pd.DataFrame(curve_rows).set_index("Date")
    trades_df = pd.DataFrame(trades)
    trade_returns = (
        pd.to_numeric(trades_df["ReturnPct"], errors="coerce").dropna()
        if not trades_df.empty
        else pd.Series(dtype=float)
    )
    gains = trade_returns[trade_returns > 0].sum()
    losses = -trade_returns[trade_returns < 0].sum()
    profit_factor = float(gains / losses) if losses > 0 else (float("inf") if gains > 0 else 0.0)

    metrics = {
        "trades": int(len(trades_df)),
        "win_rate": float((trade_returns > 0).mean() * 100) if len(trade_returns) else 0.0,
        "avg_trade_return": float(trade_returns.mean()) if len(trade_returns) else 0.0,
        "worst_trade_return": float(trade_returns.min()) if len(trade_returns) else 0.0,
        "avg_holding_days": float(trades_df["HoldingDays"].mean()) if not trades_df.empty else 0.0,
        "profit_factor": profit_factor,
        "unhedged_return": float((curve["무헷지"].iloc[-1] - 1) * 100),
        "hedged_return": float((curve["헷지 적용"].iloc[-1] - 1) * 100),
        "unhedged_mdd": _max_drawdown(curve["무헷지"]),
        "hedged_mdd": _max_drawdown(curve["헷지 적용"]),
        "entry_threshold": entry_gate,
        "exit_threshold": exit_gate,
        "max_holding_days": max_days,
        "evaluation_start": curve.index.min().strftime("%Y-%m-%d"),
        "evaluation_end": curve.index.max().strftime("%Y-%m-%d"),
    }
    metrics["mdd_improvement"] = (
        abs(metrics["unhedged_mdd"]) - abs(metrics["hedged_mdd"])
    )

    return {
        "status": "ok",
        "policy": asdict(policy),
        "metrics": metrics,
        "equity_curve": curve,
        "trades": trades_df,
    }


def optimize_hedge_parameters(
    *,
    kospi_hist: pd.DataFrame,
    vkospi_hist: pd.DataFrame,
    usdkrw_hist: pd.DataFrame,
    inverse1x_hist: pd.DataFrame,
    inverse2x_hist: pd.DataFrame,
    horizon_key: str,
    transaction_cost_bps: float = 15.0,
    train_ratio: float = 0.70,
) -> dict[str, Any]:
    """Select parameters on an older segment and report untouched holdout results.

    The newest observations are never used to select the parameters.  A
    strategy is marked ``passed`` only when the holdout has positive average
    trade return, profit factor above one, and drawdown improvement.
    """

    policy = get_horizon_policy(horizon_key)
    features = build_daily_hedge_features(kospi_hist, vkospi_hist, usdkrw_hist)
    etf_hist = inverse2x_hist if horizon_key == "tactical" else inverse1x_hist
    common_index = (
        features.index
        .intersection(_open_series(etf_hist, "ETF_OPEN").index)
        .intersection(_open_series(kospi_hist, "KOSPI_OPEN").index)
        .sort_values()
    )
    if len(common_index) < 500:
        return {
            "status": "insufficient_data",
            "message": "시간 순서 검증에 필요한 데이터가 부족합니다.",
            "policy": asdict(policy),
        }

    split_position = int(len(common_index) * float(np.clip(train_ratio, 0.60, 0.85)))
    split_position = min(max(split_position, 300), len(common_index) - 120)
    train_end = common_index[split_position - 1]
    holdout_start = common_index[split_position]

    grids = {
        "tactical": {
            "entry": (65, 70, 75, 80, 85),
            "exit": (25, 35, 45, 55),
            "days": (1, 2, 3),
        },
        "short": {
            "entry": (60, 65, 70, 75, 80),
            "exit": (25, 35, 45, 55),
            "days": (4, 6, 8, 10),
        },
        "defensive": {
            "entry": (60, 65, 70, 75, 80),
            "exit": (25, 35, 45, 55),
            "days": (10, 15, 20, 30),
        },
    }

    candidates: list[dict[str, Any]] = []
    grid = grids[horizon_key]
    for entry_gate in grid["entry"]:
        for exit_gate in grid["exit"]:
            for max_days in grid["days"]:
                result = run_hedge_backtest(
                    kospi_hist=kospi_hist,
                    vkospi_hist=vkospi_hist,
                    usdkrw_hist=usdkrw_hist,
                    inverse1x_hist=inverse1x_hist,
                    inverse2x_hist=inverse2x_hist,
                    horizon_key=horizon_key,
                    transaction_cost_bps=transaction_cost_bps,
                    entry_threshold=entry_gate,
                    exit_threshold=exit_gate,
                    max_holding_days=max_days,
                    evaluation_end=train_end,
                )
                if result.get("status") != "ok":
                    continue
                metrics = result["metrics"]
                if (
                    metrics["trades"] < 6
                    or metrics["avg_trade_return"] <= 0
                    or metrics["profit_factor"] <= 1
                    or metrics["mdd_improvement"] <= 0
                ):
                    continue
                robustness_score = (
                    metrics["mdd_improvement"]
                    + 0.40 * metrics["avg_trade_return"]
                    + 0.02 * (metrics["win_rate"] - 50)
                    + 0.15 * min(metrics["profit_factor"] - 1, 2)
                    - 0.02 * abs(metrics["worst_trade_return"])
                )
                candidates.append(
                    {
                        "entry_threshold": entry_gate,
                        "exit_threshold": exit_gate,
                        "max_holding_days": max_days,
                        "score": float(robustness_score),
                        "train_metrics": metrics,
                    }
                )

    if not candidates:
        fallback_parameters = {
            "entry_threshold": policy.entry_threshold,
            "exit_threshold": 35,
            "max_holding_days": policy.max_days,
        }
        fallback_train = run_hedge_backtest(
            kospi_hist=kospi_hist,
            vkospi_hist=vkospi_hist,
            usdkrw_hist=usdkrw_hist,
            inverse1x_hist=inverse1x_hist,
            inverse2x_hist=inverse2x_hist,
            horizon_key=horizon_key,
            transaction_cost_bps=transaction_cost_bps,
            evaluation_end=train_end,
            **fallback_parameters,
        )
        fallback_holdout = run_hedge_backtest(
            kospi_hist=kospi_hist,
            vkospi_hist=vkospi_hist,
            usdkrw_hist=usdkrw_hist,
            inverse1x_hist=inverse1x_hist,
            inverse2x_hist=inverse2x_hist,
            horizon_key=horizon_key,
            transaction_cost_bps=transaction_cost_bps,
            evaluation_start=holdout_start,
            **fallback_parameters,
        )
        if (
            fallback_train.get("status") == "ok"
            and fallback_holdout.get("status") == "ok"
        ):
            return {
                "status": "ok",
                "passed": False,
                "selection_status": "no_training_candidate",
                "message": "과거 앞구간에서도 수익성과 손실방어를 함께 통과한 조합이 없었습니다.",
                "best_parameters": fallback_parameters,
                "train_metrics": fallback_train["metrics"],
                "holdout_metrics": fallback_holdout["metrics"],
                "holdout_equity_curve": fallback_holdout["equity_curve"],
                "holdout_trades": fallback_holdout["trades"],
                "train_end": train_end.strftime("%Y-%m-%d"),
                "holdout_start": holdout_start.strftime("%Y-%m-%d"),
                "candidate_count": 0,
            }
        return {
            "status": "insufficient_signals",
            "message": "학습 구간에서 비교할 만큼 신호가 발생하지 않았습니다.",
            "policy": asdict(policy),
            "train_end": train_end.strftime("%Y-%m-%d"),
            "holdout_start": holdout_start.strftime("%Y-%m-%d"),
        }

    best = max(candidates, key=lambda item: item["score"])
    holdout_result = run_hedge_backtest(
        kospi_hist=kospi_hist,
        vkospi_hist=vkospi_hist,
        usdkrw_hist=usdkrw_hist,
        inverse1x_hist=inverse1x_hist,
        inverse2x_hist=inverse2x_hist,
        horizon_key=horizon_key,
        transaction_cost_bps=transaction_cost_bps,
        entry_threshold=best["entry_threshold"],
        exit_threshold=best["exit_threshold"],
        max_holding_days=best["max_holding_days"],
        evaluation_start=holdout_start,
    )
    if holdout_result.get("status") != "ok":
        return {
            "status": "insufficient_holdout",
            "message": holdout_result.get("message", "검증 구간 데이터 부족"),
            "best_parameters": {
                "entry_threshold": best["entry_threshold"],
                "exit_threshold": best["exit_threshold"],
                "max_holding_days": best["max_holding_days"],
            },
            "train_metrics": best["train_metrics"],
            "train_end": train_end.strftime("%Y-%m-%d"),
            "holdout_start": holdout_start.strftime("%Y-%m-%d"),
        }

    holdout_metrics = holdout_result["metrics"]
    passed = (
        holdout_metrics["trades"] >= 3
        and holdout_metrics["avg_trade_return"] > 0
        and holdout_metrics["profit_factor"] > 1
        and holdout_metrics["mdd_improvement"] > 0
    )
    return {
        "status": "ok",
        "passed": passed,
        "selection_status": "optimized",
        "best_parameters": {
            "entry_threshold": best["entry_threshold"],
            "exit_threshold": best["exit_threshold"],
            "max_holding_days": best["max_holding_days"],
        },
        "train_metrics": best["train_metrics"],
        "holdout_metrics": holdout_metrics,
        "holdout_equity_curve": holdout_result["equity_curve"],
        "holdout_trades": holdout_result["trades"],
        "train_end": train_end.strftime("%Y-%m-%d"),
        "holdout_start": holdout_start.strftime("%Y-%m-%d"),
        "candidate_count": len(candidates),
    }
