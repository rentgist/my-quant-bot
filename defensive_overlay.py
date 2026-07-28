"""Low-complexity defensive allocation helpers.

The policy is intentionally long-only.  It combines a volatility-scaled
equity weight, a slow trend cap, cash, and staged re-entry.  It does not use
leverage, options, or synthetic short positions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class DefensiveParameters:
    target_volatility: float = 0.12
    trend_days: int = 200
    defensive_cap: float = 0.55
    rebalance_days: int = 5
    minimum_equity: float = 0.20
    max_rebalance_step: float = 0.10


def _column(frame: pd.DataFrame, name: str) -> pd.Series:
    """Return a numeric Series from flat or yfinance MultiIndex columns."""

    if frame is None or frame.empty:
        return pd.Series(dtype=float)
    if name in frame.columns:
        values = frame[name]
    elif isinstance(frame.columns, pd.MultiIndex) and name in frame.columns.get_level_values(0):
        values = frame.xs(name, axis=1, level=0)
    else:
        return pd.Series(dtype=float)
    if isinstance(values, pd.DataFrame):
        values = values.iloc[:, 0]
    result = pd.to_numeric(values, errors="coerce")
    result.index = pd.to_datetime(result.index)
    return result.sort_index()


def _rsi(close: pd.Series, days: int = 14) -> pd.Series:
    change = close.diff()
    gain = change.clip(lower=0).rolling(days).mean()
    loss = (-change.clip(upper=0)).rolling(days).mean()
    relative_strength = gain / loss.replace(0, np.nan)
    return (100 - 100 / (1 + relative_strength)).fillna(50.0)


def build_defensive_features(
    kospi_hist: pd.DataFrame,
    *,
    target_volatility: float = 0.12,
    trend_days: int = 200,
    defensive_cap: float = 0.55,
    rebalance_days: int = 5,
    minimum_equity: float = 0.20,
    max_rebalance_step: float = 0.10,
) -> pd.DataFrame:
    """Build close-of-day signals and a realistic, step-limited equity weight."""

    close = _column(kospi_hist, "Close")
    open_price = _column(kospi_hist, "Open")
    if open_price.empty:
        open_price = close.copy()
    market = pd.concat(
        [open_price.rename("Open"), close.rename("Close")],
        axis=1,
    ).dropna()
    if len(market) < max(int(trend_days), 60) + 25:
        return pd.DataFrame()

    target_volatility = float(np.clip(target_volatility, 0.04, 0.30))
    defensive_cap = float(np.clip(defensive_cap, 0.10, 1.0))
    minimum_equity = float(np.clip(minimum_equity, 0.0, defensive_cap))
    max_rebalance_step = float(np.clip(max_rebalance_step, 0.01, 1.0))
    rebalance_days = max(int(rebalance_days), 1)

    close_return = market["Close"].pct_change()
    hv20 = close_return.rolling(20).std() * np.sqrt(252)
    hv_rank = hv20.rolling(504, min_periods=126).rank(pct=True)
    trend_ma = market["Close"].rolling(int(trend_days)).mean()
    vol_weight = (target_volatility / hv20.replace(0, np.nan)).clip(
        lower=minimum_equity,
        upper=1.0,
    )
    trend_weight = pd.Series(
        np.where(market["Close"] >= trend_ma, 1.0, defensive_cap),
        index=market.index,
        dtype=float,
    )
    raw_target = pd.concat([vol_weight, trend_weight], axis=1).min(axis=1)
    raw_target = raw_target.clip(lower=minimum_equity, upper=1.0)

    features = market.copy()
    features["Return1D"] = close_return
    features["HV20"] = hv20
    features["HVRank"] = hv_rank
    features["MA5"] = market["Close"].rolling(5).mean()
    features["MA20"] = market["Close"].rolling(20).mean()
    features["MA60"] = market["Close"].rolling(60).mean()
    features["TrendMA"] = trend_ma
    features["RSI"] = _rsi(market["Close"])
    features["RawTargetWeight"] = raw_target
    features = features.dropna(
        subset=["HV20", "MA5", "MA20", "MA60", "TrendMA", "RawTargetWeight"]
    ).copy()
    if features.empty:
        return features

    weights: list[float] = []
    previous_weight = float(features["RawTargetWeight"].iloc[0])
    for row_number, (_, row) in enumerate(features.iterrows()):
        if row_number == 0:
            previous_weight = float(row["RawTargetWeight"])
        elif row_number % rebalance_days == 0:
            panic_session = bool(
                row["RSI"] <= 32
                or row["Return1D"] <= -0.04
                or row["HVRank"] >= 0.95
            )
            if not panic_session:
                desired = float(row["RawTargetWeight"])
                lower = previous_weight - max_rebalance_step
                upper = previous_weight + max_rebalance_step
                previous_weight = float(np.clip(desired, lower, upper))
        weights.append(float(np.clip(previous_weight, minimum_equity, 1.0)))

    features["EquityWeight"] = weights
    features["CashWeight"] = 1 - features["EquityWeight"]
    # A signal observed at today's close is executed at the next open and held
    # until the following open.  This avoids same-close look-ahead.
    features["ForwardMarketReturn"] = (
        features["Open"].shift(-2) / features["Open"].shift(-1) - 1
    )
    return features


def _max_drawdown(returns: pd.Series) -> float:
    if returns.empty:
        return 0.0
    curve = (1 + returns.fillna(0)).cumprod()
    return float((curve / curve.cummax() - 1).min())


def _annual_return(returns: pd.Series) -> float:
    clean = returns.dropna()
    if clean.empty:
        return 0.0
    total = float((1 + clean).prod())
    if total <= 0:
        return -1.0
    return float(total ** (252 / len(clean)) - 1)


def _annual_volatility(returns: pd.Series) -> float:
    clean = returns.dropna()
    return float(clean.std(ddof=0) * np.sqrt(252)) if len(clean) > 1 else 0.0


def _sharpe(returns: pd.Series) -> float:
    volatility = _annual_volatility(returns)
    return _annual_return(returns) / volatility if volatility > 0 else 0.0


def _window_defense_rate(
    strategy_returns: pd.Series,
    benchmark_returns: pd.Series,
    window: int = 20,
) -> tuple[float, int]:
    strategy_window = (1 + strategy_returns).rolling(window).apply(np.prod, raw=True) - 1
    benchmark_window = (1 + benchmark_returns).rolling(window).apply(np.prod, raw=True) - 1
    falling = benchmark_window < 0
    observations = int(falling.sum())
    if observations == 0:
        return 0.0, 0
    success = strategy_window[falling] >= benchmark_window[falling]
    return float(success.mean() * 100), observations


def run_defensive_backtest(
    kospi_hist: pd.DataFrame,
    *,
    target_volatility: float = 0.12,
    trend_days: int = 200,
    defensive_cap: float = 0.55,
    rebalance_days: int = 5,
    minimum_equity: float = 0.20,
    max_rebalance_step: float = 0.10,
    transaction_cost_bps: float = 15.0,
    evaluation_start: Any | None = None,
    evaluation_end: Any | None = None,
) -> dict[str, Any]:
    """Backtest a cash/equity defensive overlay against 100% KOSPI."""

    features = build_defensive_features(
        kospi_hist,
        target_volatility=target_volatility,
        trend_days=trend_days,
        defensive_cap=defensive_cap,
        rebalance_days=rebalance_days,
        minimum_equity=minimum_equity,
        max_rebalance_step=max_rebalance_step,
    )
    if features.empty:
        return {
            "status": "insufficient_data",
            "message": "방어 조합 검증에는 최소 1년 이상의 KOSPI 가격이 필요합니다.",
        }

    evaluation = features.dropna(subset=["ForwardMarketReturn"]).copy()
    if evaluation_start is not None:
        evaluation = evaluation[evaluation.index >= pd.Timestamp(evaluation_start)]
    if evaluation_end is not None:
        evaluation = evaluation[evaluation.index <= pd.Timestamp(evaluation_end)]
    if len(evaluation) < 40:
        return {
            "status": "insufficient_data",
            "message": "선택한 검증 구간의 거래일이 40일 미만입니다.",
        }

    turnover = evaluation["EquityWeight"].diff().abs().fillna(0)
    cost = max(float(transaction_cost_bps), 0.0) / 10_000
    strategy_return = (
        evaluation["EquityWeight"] * evaluation["ForwardMarketReturn"]
        - turnover * cost
    )
    benchmark_return = evaluation["ForwardMarketReturn"]

    strategy_mdd = _max_drawdown(strategy_return)
    benchmark_mdd = _max_drawdown(benchmark_return)
    strategy_vol = _annual_volatility(strategy_return)
    benchmark_vol = _annual_volatility(benchmark_return)
    defense_rate, defense_windows = _window_defense_rate(
        strategy_return,
        benchmark_return,
    )
    metrics = {
        "strategy_total_return": float(((1 + strategy_return).prod() - 1) * 100),
        "benchmark_total_return": float(((1 + benchmark_return).prod() - 1) * 100),
        "strategy_annual_return": _annual_return(strategy_return) * 100,
        "benchmark_annual_return": _annual_return(benchmark_return) * 100,
        "strategy_mdd": strategy_mdd * 100,
        "benchmark_mdd": benchmark_mdd * 100,
        "mdd_improvement": (strategy_mdd - benchmark_mdd) * 100,
        "strategy_volatility": strategy_vol * 100,
        "benchmark_volatility": benchmark_vol * 100,
        "volatility_reduction": (
            (1 - strategy_vol / benchmark_vol) * 100 if benchmark_vol > 0 else 0.0
        ),
        "strategy_sharpe": _sharpe(strategy_return),
        "benchmark_sharpe": _sharpe(benchmark_return),
        "defense_rate": defense_rate,
        "defense_windows": defense_windows,
        "average_equity_weight": float(evaluation["EquityWeight"].mean() * 100),
        "average_cash_weight": float((1 - evaluation["EquityWeight"]).mean() * 100),
        "annual_turnover": float(turnover.sum() * 252 / len(evaluation) * 100),
        "worst_day": float(strategy_return.min() * 100),
        "benchmark_worst_day": float(benchmark_return.min() * 100),
        "evaluation_start": str(evaluation.index.min().date()),
        "evaluation_end": str(evaluation.index.max().date()),
        "observations": int(len(evaluation)),
    }
    curve = pd.DataFrame(
        {
            "KOSPI 100%": (1 + benchmark_return).cumprod(),
            "안전 방어조합": (1 + strategy_return).cumprod(),
        },
        index=evaluation.index,
    )
    return {
        "status": "ok",
        "metrics": metrics,
        "equity_curve": curve,
        "features": features,
        "returns": pd.DataFrame(
            {"strategy": strategy_return, "benchmark": benchmark_return}
        ),
    }


def optimize_defensive_parameters(
    kospi_hist: pd.DataFrame,
    *,
    transaction_cost_bps: float = 15.0,
    train_fraction: float = 0.70,
) -> dict[str, Any]:
    """Select on the older sample and validate once on the recent sample."""

    close = _column(kospi_hist, "Close").dropna()
    if len(close) < 650:
        return {
            "status": "insufficient_data",
            "passed": False,
            "message": "시간순 최적화에는 최소 650거래일의 KOSPI 데이터가 필요합니다.",
        }

    usable = close.iloc[220:-2]
    split_position = int(len(usable) * float(np.clip(train_fraction, 0.55, 0.85)))
    if split_position < 300 or len(usable) - split_position < 120:
        return {
            "status": "insufficient_data",
            "passed": False,
            "message": "앞구간과 최근 검증구간을 나누기에 데이터가 부족합니다.",
        }
    holdout_start = usable.index[split_position]
    train_end = usable.index[split_position - 1]

    candidates: list[tuple[float, dict[str, Any], dict[str, Any]]] = []
    for target_volatility in (0.10, 0.12, 0.15):
        for trend_days in (120, 200):
            for defensive_cap in (0.40, 0.55, 0.70):
                for rebalance_days in (5, 10):
                    parameters = {
                        "target_volatility": target_volatility,
                        "trend_days": trend_days,
                        "defensive_cap": defensive_cap,
                        "rebalance_days": rebalance_days,
                        "minimum_equity": 0.20,
                        "max_rebalance_step": 0.10,
                    }
                    training = run_defensive_backtest(
                        kospi_hist,
                        **parameters,
                        transaction_cost_bps=transaction_cost_bps,
                        evaluation_end=train_end,
                    )
                    if training.get("status") != "ok":
                        continue
                    metrics = training["metrics"]
                    if (
                        metrics["mdd_improvement"] < 2.0
                        or metrics["volatility_reduction"] < 5.0
                        or metrics["average_equity_weight"] < 35.0
                    ):
                        continue
                    score = (
                        metrics["strategy_annual_return"]
                        + 0.45 * metrics["mdd_improvement"]
                        + 0.15 * metrics["volatility_reduction"]
                        + 1.5 * (metrics["strategy_sharpe"] - metrics["benchmark_sharpe"])
                        - 0.01 * metrics["annual_turnover"]
                    )
                    candidates.append((float(score), parameters, training))

    if not candidates:
        return {
            "status": "no_candidate",
            "passed": False,
            "message": "과거 앞구간에서 낙폭·변동성 개선 기준을 통과한 조합이 없습니다.",
        }

    _, best_parameters, training = max(candidates, key=lambda item: item[0])
    holdout = run_defensive_backtest(
        kospi_hist,
        **best_parameters,
        transaction_cost_bps=transaction_cost_bps,
        evaluation_start=holdout_start,
    )
    full = run_defensive_backtest(
        kospi_hist,
        **best_parameters,
        transaction_cost_bps=transaction_cost_bps,
    )
    if holdout.get("status") != "ok" or full.get("status") != "ok":
        return {
            "status": "insufficient_data",
            "passed": False,
            "message": "최근 검증구간의 결과를 계산하지 못했습니다.",
        }

    holdout_metrics = holdout["metrics"]
    passed = bool(
        holdout_metrics["mdd_improvement"] >= 1.0
        and holdout_metrics["volatility_reduction"] >= 5.0
        and holdout_metrics["strategy_annual_return"] > 0
        and holdout_metrics["strategy_sharpe"]
        >= holdout_metrics["benchmark_sharpe"]
        and holdout_metrics["average_equity_weight"] >= 25.0
    )
    return {
        "status": "ok",
        "passed": passed,
        "best_parameters": best_parameters,
        "train_end": str(pd.Timestamp(train_end).date()),
        "holdout_start": str(pd.Timestamp(holdout_start).date()),
        "training_metrics": training["metrics"],
        "holdout_metrics": holdout_metrics,
        "full_metrics": full["metrics"],
        "equity_curve": full["equity_curve"],
        "features": full["features"],
        "message": (
            "최근 미사용 구간에서도 낙폭·변동성·위험 대비 수익 기준을 통과했습니다."
            if passed
            else "최근 미사용 구간에서 방어력과 위험 대비 수익 기준을 함께 통과하지 못했습니다."
        ),
    }


def current_defensive_state(
    kospi_hist: pd.DataFrame,
    parameters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Describe today's risk target and the four-step re-entry stage."""

    parameters = parameters or {
        "target_volatility": 0.12,
        "trend_days": 200,
        "defensive_cap": 0.55,
        "rebalance_days": 5,
        "minimum_equity": 0.20,
        "max_rebalance_step": 0.10,
    }
    features = build_defensive_features(kospi_hist, **parameters)
    if features.empty:
        return {
            "status": "insufficient_data",
            "message": "현재 방어 비중을 계산할 KOSPI 데이터가 부족합니다.",
        }

    latest = features.iloc[-1]
    previous = features.iloc[-2] if len(features) > 1 else latest
    close = float(latest["Close"])
    two_days_above_ma5 = bool(
        close > latest["MA5"] and previous["Close"] > previous["MA5"]
    )
    if (
        close > latest["TrendMA"]
        and close > latest["MA60"]
        and latest["HVRank"] < 0.60
    ):
        stage = 4
    elif close > latest["MA60"] and close > latest["MA20"] and latest["HVRank"] < 0.75:
        stage = 3
    elif close > latest["MA20"]:
        stage = 2
    elif two_days_above_ma5 and latest["RSI"] > 32:
        stage = 1
    else:
        stage = 0

    stage_labels = {
        0: "바닥 확인 전 — 새 매수 대기",
        1: "1차 안정 — 예비현금의 10%까지",
        2: "20일선 회복 — 누적 30%까지",
        3: "중기 추세 회복 — 누적 60%까지",
        4: "정상화 확인 — 계획 비중까지",
    }
    stage_release = {0: 0, 1: 10, 2: 30, 3: 60, 4: 100}
    panic_freeze = bool(
        latest["RSI"] <= 32
        or latest["Return1D"] <= -0.04
        or latest["HVRank"] >= 0.95
    )
    return {
        "status": "ok",
        "as_of": str(features.index[-1].date()),
        "target_equity_weight": float(latest["RawTargetWeight"]),
        "model_equity_weight": float(latest["EquityWeight"]),
        "target_cash_weight": float(1 - latest["RawTargetWeight"]),
        "realized_volatility": float(latest["HV20"]),
        "volatility_percentile": float(latest["HVRank"]),
        "above_trend": bool(close >= latest["TrendMA"]),
        "trend_days": int(parameters.get("trend_days", 200)),
        "rsi": float(latest["RSI"]),
        "daily_return": float(latest["Return1D"]),
        "panic_freeze": panic_freeze,
        "reentry_stage": stage,
        "reentry_label": stage_labels[stage],
        "dry_powder_release_pct": stage_release[stage],
    }


def build_defensive_action_plan(
    *,
    total_assets: float,
    current_equity_amount: float,
    state: dict[str, Any],
    validation_passed: bool,
    max_today_step: float = 0.10,
) -> dict[str, Any]:
    """Translate the defensive state into a capped, plain-language order."""

    total_assets = max(float(total_assets), 0.0)
    current_equity_amount = float(np.clip(current_equity_amount, 0, total_assets))
    if state.get("status") != "ok" or total_assets <= 0:
        return {
            "action": "WAIT_DATA",
            "title": "오늘은 비중을 바꾸지 마세요",
            "amount": 0.0,
            "amount_label": "주문 금액",
            "reason": "검증 데이터 또는 총자산 입력이 부족합니다.",
            "target_equity_amount": current_equity_amount,
            "target_cash_amount": total_assets - current_equity_amount,
            "steps": ["현금과 기존 주식을 그대로 둡니다.", "데이터가 복구된 뒤 다시 계산합니다."],
        }

    target_weight = float(np.clip(state["target_equity_weight"], 0, 1))
    target_equity = total_assets * target_weight
    target_cash = total_assets - target_equity
    maximum_order = total_assets * float(np.clip(max_today_step, 0.01, 0.25))
    gap = target_equity - current_equity_amount

    if not validation_passed:
        return {
            "action": "HOLD_VALIDATION",
            "title": "오늘은 자동 비중조절을 실행하지 마세요",
            "amount": 0.0,
            "amount_label": "주문 금액",
            "reason": "최근 미사용 구간에서 방어 조합이 검증 기준을 통과하지 못했습니다.",
            "target_equity_amount": target_equity,
            "target_cash_amount": target_cash,
            "steps": [
                "신규 인버스와 기계적 주식 매도를 모두 보류합니다.",
                "현재 현금을 유지하고 다음 종가에 다시 확인합니다.",
            ],
        }

    if state.get("panic_freeze"):
        return {
            "action": "PANIC_FREEZE",
            "title": "오늘은 폭락 뒤 추가 매도·추격 매수를 모두 멈추세요",
            "amount": 0.0,
            "amount_label": "오늘 주문",
            "reason": "극단적 과매도/고변동성 구간이라 지금 비중을 크게 바꾸면 저점 매도나 휩쏘 위험이 큽니다.",
            "target_equity_amount": target_equity,
            "target_cash_amount": target_cash,
            "steps": [
                "새 인버스·곱버스 주문을 넣지 않습니다.",
                f"현재 현금 {total_assets - current_equity_amount:,.0f}만원을 그대로 둡니다.",
                "KOSPI가 5일선 위에서 이틀 유지되는지 다음 종가에 확인합니다.",
            ],
        }

    if gap < -1:
        amount = min(abs(gap), maximum_order)
        return {
            "action": "REDUCE_EQUITY",
            "title": f"오늘 국내 주식을 {amount:,.0f}만원만 줄이세요",
            "amount": amount,
            "amount_label": "주식 매도",
            "reason": "목표 비중까지 한 번에 팔지 않고 총자산의 10% 이내로 천천히 줄입니다.",
            "target_equity_amount": target_equity,
            "target_cash_amount": target_cash,
            "steps": [
                "고베타·저품질 종목부터 정리하고 코어 우량주는 마지막에 조정합니다.",
                f"현재 방어 목표는 주식 {target_equity:,.0f}만원·현금 {target_cash:,.0f}만원입니다.",
                "다음 주간 재조정일까지 추가 매도를 반복하지 않습니다.",
            ],
        }

    if gap > 1 and int(state.get("reentry_stage", 0)) > 0:
        release_fraction = {
            1: 0.10,
            2: 0.30,
            3: 0.60,
            4: 1.00,
        }.get(int(state.get("reentry_stage", 0)), 0.0)
        available_cash = max(total_assets - current_equity_amount, 0.0)
        amount = min(gap, maximum_order, available_cash * release_fraction)
        return {
            "action": "ADD_EQUITY",
            "title": f"오늘 국내 주식을 {amount:,.0f}만원까지만 분할 매수하세요",
            "amount": amount,
            "amount_label": "주식 매수",
            "reason": state["reentry_label"],
            "target_equity_amount": target_equity,
            "target_cash_amount": target_cash,
            "steps": [
                "지수 ETF나 실적이 확인된 코어 우량주만 사용합니다.",
                "오후 종가 부근에 한 번만 실행하고 장중 급등은 따라가지 않습니다.",
                "다음 회복 단계가 확인되기 전에는 추가 매수하지 않습니다.",
            ],
        }

    return {
        "action": "HOLD",
        "title": "오늘은 현재 주식·현금 비중을 유지하세요",
        "amount": 0.0,
        "amount_label": "오늘 주문",
        "reason": state.get("reentry_label", "목표 비중과 현재 비중의 차이가 작습니다."),
        "target_equity_amount": target_equity,
        "target_cash_amount": target_cash,
        "steps": [
            "신규 인버스·곱버스를 사지 않습니다.",
            f"현금 {total_assets - current_equity_amount:,.0f}만원을 바닥 확인용으로 남깁니다.",
            "다음 종가에 재진입 단계를 다시 확인합니다.",
        ],
    }


def evaluate_usd_diversifier(
    kospi_hist: pd.DataFrame,
    usdkrw_hist: pd.DataFrame,
) -> dict[str, Any]:
    """Screen USD/KRW as a small diversifier; this is not a product order."""

    kospi = _column(kospi_hist, "Close").rename("KOSPI")
    usdkrw = _column(usdkrw_hist, "Close").rename("USDKRW")
    aligned = pd.concat([kospi, usdkrw], axis=1).dropna()
    if len(aligned) < 120:
        return {
            "status": "insufficient_data",
            "eligible": False,
            "allocation_cap": 0.0,
            "message": "원/달러 분산효과를 확인할 데이터가 부족합니다.",
        }
    returns = aligned.pct_change()
    correlation = float(returns["KOSPI"].tail(60).corr(returns["USDKRW"].tail(60)))
    usd_above_ma60 = bool(
        aligned["USDKRW"].iloc[-1] > aligned["USDKRW"].rolling(60).mean().iloc[-1]
    )
    eligible = bool(correlation <= -0.15 and usd_above_ma60)
    return {
        "status": "ok",
        "eligible": eligible,
        "allocation_cap": 0.05 if eligible else 0.0,
        "correlation_60d": correlation,
        "usd_above_ma60": usd_above_ma60,
        "message": (
            f"최근 60일 상관계수 {correlation:+.2f}이고 원/달러 추세도 강해 총자산 5% 이내의 분산 후보입니다."
            if eligible
            else f"최근 60일 상관계수 {correlation:+.2f} 또는 원/달러 추세가 기준에 못 미쳐 지금은 추가하지 않습니다."
        ),
    }
