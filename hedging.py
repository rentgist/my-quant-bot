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
) -> HedgeDecision:
    """Return a position-aware hedge decision.

    ``position_status`` must be one of ``none``, ``inverse1x``, or
    ``inverse2x``.  A positive foreign-futures number is treated as a potential
    rebound/short-cover warning, not as a fresh short entry.
    """

    policy = get_horizon_policy(horizon_key)
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
                max_holding_days=policy.max_days,
                allow_new_entry=False,
                urgency="high",
            )
        if holding_days >= policy.max_days:
            return HedgeDecision(
                action="EXIT_TIME",
                headline="보유기간 만료 — 청산",
                reason=f"선택한 전략의 최대 보유기간 {policy.max_days}거래일에 도달했습니다. 재진입은 새 신호로 다시 판단해야 합니다.",
                product=policy.product,
                max_holding_days=policy.max_days,
                allow_new_entry=False,
                urgency="high",
            )
        if exit_score >= 60:
            return HedgeDecision(
                action="EXIT",
                headline="인버스 전량 청산 검토",
                reason=f"청산 점수 {exit_score:.0f}점으로 반등·공포 피크아웃 조건이 강하게 겹쳤습니다.",
                product=policy.product,
                max_holding_days=policy.max_days,
                allow_new_entry=False,
                urgency="high",
            )
        if (
            exit_score >= 35
            or (rsi_value is not None and rsi_value <= 32)
            or (futures_value is not None and futures_value > 0)
        ):
            return HedgeDecision(
                action="REDUCE",
                headline="인버스 50% 축소",
                reason="과매도 또는 외국인 선물 매수 전환이 확인돼 급반등 위험이 커졌습니다. 남은 물량은 시간 제한을 적용합니다.",
                product=policy.product,
                max_holding_days=policy.max_days,
                allow_new_entry=False,
                urgency="medium",
            )
        return HedgeDecision(
            action="HOLD",
            headline="기존 헷지 유지",
            reason=f"청산 조건은 아직 부족합니다. 단, 최대 {policy.max_days}거래일까지만 유지합니다.",
            product=policy.product,
            max_holding_days=policy.max_days,
            allow_new_entry=False,
            urgency="low",
        )

    if data_quality == "unavailable":
        return HedgeDecision(
            action="BLOCK_DATA",
            headline="신규 헷지 금지 — 데이터 확인 필요",
            reason="핵심 변동성 또는 가격 데이터가 없어 레버리지 신호를 계산할 수 없습니다.",
            product=policy.product,
            max_holding_days=policy.max_days,
            allow_new_entry=False,
            urgency="high",
        )
    if data_quality == "proxy" and horizon_key == "tactical":
        return HedgeDecision(
            action="BLOCK_PROXY_2X",
            headline="2배 인버스 금지 — VKOSPI 프록시 사용 중",
            reason="실제 옵션 내재변동성이 아닌 후행 실현변동성 프록시로는 초단기 2배 진입을 허용하지 않습니다.",
            product=policy.product,
            max_holding_days=policy.max_days,
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
            max_holding_days=policy.max_days,
            allow_new_entry=False,
            urgency="medium",
        )

    if entry_score < policy.entry_threshold:
        return HedgeDecision(
            action="WAIT",
            headline="신규 헷지 대기",
            reason=f"진입 점수 {entry_score:.0f}점이 {policy.entry_threshold}점 기준에 미달합니다.",
            product=policy.product,
            max_holding_days=policy.max_days,
            allow_new_entry=False,
            urgency="low",
        )

    if horizon_key == "defensive":
        return HedgeDecision(
            action="REDUCE_BETA",
            headline="중단기 위험자산 베타 축소",
            reason="중단기 방어에서는 2배 인버스 대신 현금 확대와 1배 인버스를 조합합니다.",
            product=policy.product,
            max_holding_days=policy.max_days,
            allow_new_entry=True,
            urgency="medium",
        )

    return HedgeDecision(
        action="ENTER_PARTIAL",
        headline="보호성 헷지 1차 진입",
        reason=f"{policy.label} 기준을 충족했습니다. 정책 상한의 50%만 먼저 진입하고 다음 거래일에 재평가합니다.",
        product=policy.product,
        max_holding_days=policy.max_days,
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
) -> dict[str, Any]:
    """Backtest a hedge overlay using next-session open-to-open returns.

    Signals are computed at session ``t`` close.  The position changes at the
    next session's open and earns the following open-to-open ETF return.  This
    avoids filling a trade at a close that was already used to calculate the
    signal.
    """

    policy = get_horizon_policy(horizon_key)
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
                row["ExitScore"] >= 35
                or holding_days >= policy.max_days
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
            if row["EntryScore"] >= policy.entry_threshold and not panic_reversal:
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
