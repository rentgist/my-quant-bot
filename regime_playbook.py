"""Long-only market-regime playbook for the ORION dashboard.

The module deliberately keeps inverse, leverage, derivatives, and market-neutral
strategies outside the default path.  Signals are calculated at the close and any
allocation change is intended for the next trading session.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


REGIME_POLICIES = {
    "CRASH": {
        "label": "폭락·하락 진행",
        "icon": "🔴",
        "color": "#b91c1c",
        "equity_band": (0.40, 0.60),
        "earning_method": "현금·단기자금의 이자와 낙폭 회피",
        "core_strategy": "패닉 매도 동결 → 진정 확인 뒤에만 약한 종목부터 축소",
        "avoid": "인버스 추격, 레버리지, 투매 손절, 물타기",
    },
    "BOTTOM_RECOVERY": {
        "label": "바닥 확인 후 반등",
        "icon": "🟠",
        "color": "#d97706",
        "equity_band": (0.50, 0.75),
        "earning_method": "시장 전체·우량주를 3회로 나눈 재진입",
        "core_strategy": "5일선 → 20일선 → 60일선 회복 순서로 현금 투입",
        "avoid": "첫 반등일 몰빵, 2배 레버리지, 적자기업 저점 추격",
    },
    "UPTREND": {
        "label": "완만한 상승",
        "icon": "🟢",
        "color": "#15803d",
        "equity_band": (0.70, 0.90),
        "earning_method": "우량주·시장지수의 장기 상승 추세 보유",
        "core_strategy": "핵심 보유 유지, 새 돈은 눌림목·비중 이탈 때 투입",
        "avoid": "잦은 매매, 상승 종목 전량 익절, 과도한 현금 대기",
    },
    "SIDEWAYS": {
        "label": "횡보·방향 탐색",
        "icon": "🔵",
        "color": "#2563eb",
        "equity_band": (0.50, 0.70),
        "earning_method": "현금 이자 + 우량주·지수의 범위 재조정",
        "core_strategy": "비중이 범위를 벗어날 때만 5%p씩 리밸런싱",
        "avoid": "돌파 전 추격, 잦은 단타, 페어트레이딩·옵션 매도",
    },
}


def _safe_float(value: Any, default: float = np.nan) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if np.isfinite(number) else default


def _rsi(close: pd.Series, days: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(days).mean()
    loss = (-delta.clip(upper=0)).rolling(days).mean()
    relative_strength = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + relative_strength))
    return rsi.where(loss.ne(0), 100.0)


def _percentile_rank(values: np.ndarray) -> float:
    series = pd.Series(values).dropna()
    if series.empty:
        return np.nan
    return float((series <= series.iloc[-1]).mean())


def build_market_features(kospi_history: pd.DataFrame) -> pd.DataFrame:
    """Build close-only features without future data."""
    if kospi_history is None or kospi_history.empty or "Close" not in kospi_history:
        return pd.DataFrame()

    features = pd.DataFrame(index=kospi_history.index.copy())
    features["Close"] = pd.to_numeric(kospi_history["Close"], errors="coerce")
    features = features.dropna(subset=["Close"]).sort_index()
    if features.empty:
        return features

    close = features["Close"]
    returns = close.pct_change()
    features["RET1"] = returns
    for days in (5, 20, 60):
        features[f"RET{days}"] = close.pct_change(days)
    for days in (5, 20, 60, 120):
        features[f"MA{days}"] = close.rolling(days).mean()

    features["MA20Slope10"] = features["MA20"].pct_change(10)
    features["HV20"] = returns.rolling(20).std() * np.sqrt(252)
    features["HVRank"] = features["HV20"].rolling(504, min_periods=126).apply(
        _percentile_rank,
        raw=True,
    )
    features["RSI14"] = _rsi(close)
    features["BandWidth20"] = (
        4 * close.rolling(20).std() / features["MA20"].replace(0, np.nan)
    )
    features["AboveMA5TwoDays"] = (
        close.gt(features["MA5"]) & close.shift(1).gt(features["MA5"].shift(1))
    )
    return features


def _row_regime(row: pd.Series, bottom_score: float = 0.0) -> tuple[str, bool, int]:
    ret1 = _safe_float(row.get("RET1"), 0.0)
    ret20 = _safe_float(row.get("RET20"), 0.0)
    ret60 = _safe_float(row.get("RET60"), 0.0)
    rsi = _safe_float(row.get("RSI14"), 50.0)
    hv_rank = _safe_float(row.get("HVRank"), 0.5)
    close = _safe_float(row.get("Close"))
    ma5 = _safe_float(row.get("MA5"))
    ma20 = _safe_float(row.get("MA20"))
    ma60 = _safe_float(row.get("MA60"))
    ma120 = _safe_float(row.get("MA120"))
    slope = _safe_float(row.get("MA20Slope10"), 0.0)
    above_ma5_two_days = bool(row.get("AboveMA5TwoDays", False))

    panic = (
        ret1 <= -0.04
        or hv_rank >= 0.97
        or (rsi <= 32 and hv_rank >= 0.85)
    )
    confirmed_downtrend = (
        np.isfinite(close)
        and np.isfinite(ma20)
        and np.isfinite(ma60)
        and close < ma60
        and ma20 < ma60
        and ret20 < 0
    )
    recovery = (
        not panic
        and not confirmed_downtrend
        and (
            (above_ma5_two_days and rsi > 32 and bottom_score >= 50)
            or (
                np.isfinite(close)
                and np.isfinite(ma20)
                and close > ma20
                and slope > 0
                and (ret60 <= 0 or (np.isfinite(ma120) and close < ma120))
            )
        )
    )
    uptrend = (
        not panic
        and np.isfinite(close)
        and np.isfinite(ma20)
        and np.isfinite(ma60)
        and close > ma60
        and ma20 > ma60
        and slope > 0
        and ret60 > 0
    )

    if panic or confirmed_downtrend:
        confirmations = sum(
            [
                panic,
                confirmed_downtrend,
                ret20 < 0,
                rsi < 40,
                hv_rank >= 0.85,
            ]
        )
        return "CRASH", panic, confirmations
    if recovery:
        confirmations = sum(
            [
                above_ma5_two_days,
                close > ma20 if np.isfinite(ma20) else False,
                slope > 0,
                rsi > 32,
                bottom_score >= 50,
            ]
        )
        return "BOTTOM_RECOVERY", False, confirmations
    if uptrend:
        confirmations = sum(
            [close > ma20, close > ma60, ma20 > ma60, slope > 0, ret60 > 0]
        )
        return "UPTREND", False, confirmations
    return "SIDEWAYS", False, 3


def classify_market_regime(
    kospi_history: pd.DataFrame,
    bottom_score: float = 0.0,
) -> dict[str, Any]:
    """Classify the current market into one of four user-facing regimes."""
    features = build_market_features(kospi_history)
    if len(features) < 120:
        return {
            "status": "unavailable",
            "code": "SIDEWAYS",
            **REGIME_POLICIES["SIDEWAYS"],
            "panic_freeze": False,
            "confidence": 0,
            "as_of": None,
            "message": "국면 판별에 필요한 KOSPI 120거래일 데이터가 부족합니다.",
            "indicators": {},
        }

    latest = features.iloc[-1]
    code, panic, confirmations = _row_regime(latest, bottom_score=bottom_score)
    policy = REGIME_POLICIES[code]
    confidence = int(np.clip(45 + confirmations * 9, 50, 90))
    as_of = pd.Timestamp(features.index[-1]).date().isoformat()
    indicators = {
        "close": _safe_float(latest.get("Close")),
        "daily_return": _safe_float(latest.get("RET1")),
        "return_20d": _safe_float(latest.get("RET20")),
        "return_60d": _safe_float(latest.get("RET60")),
        "rsi": _safe_float(latest.get("RSI14")),
        "realized_volatility": _safe_float(latest.get("HV20")),
        "volatility_rank": _safe_float(latest.get("HVRank")),
        "ma5": _safe_float(latest.get("MA5")),
        "ma20": _safe_float(latest.get("MA20")),
        "ma60": _safe_float(latest.get("MA60")),
        "ma120": _safe_float(latest.get("MA120")),
    }
    return {
        "status": "ok",
        "code": code,
        **policy,
        "panic_freeze": panic,
        "confidence": confidence,
        "as_of": as_of,
        "message": (
            "패닉 안전장치가 켜져 기술적 급매도를 멈춥니다."
            if panic
            else f"{policy['label']} 조건이 가장 많이 확인됐습니다."
        ),
        "indicators": indicators,
    }


def build_regime_action_plan(
    total_assets: float,
    current_equity_amount: float,
    regime: dict[str, Any],
    max_step: float = 0.05,
) -> dict[str, Any]:
    """Translate a regime into one explicit account-level action."""
    total = max(_safe_float(total_assets, 0.0), 0.0)
    equity = float(np.clip(_safe_float(current_equity_amount, 0.0), 0.0, total))
    cash = max(total - equity, 0.0)
    current_weight = equity / total if total else 0.0
    code = regime.get("code", "SIDEWAYS")
    policy = REGIME_POLICIES.get(code, REGIME_POLICIES["SIDEWAYS"])
    lower, upper = policy["equity_band"]
    step_cap = total * max_step

    action = "HOLD"
    amount = 0.0
    title = "오늘은 주식·현금 비중을 그대로 두세요"
    reason = f"현재 주식 {current_weight * 100:.0f}%가 권장 범위 {lower * 100:.0f}~{upper * 100:.0f}% 안입니다."
    next_check = "다음 종가"

    if regime.get("status") != "ok":
        title = "데이터가 보강될 때까지 새 주문을 보류하세요"
        reason = regime.get("message", "국면 데이터가 부족합니다.")
    elif regime.get("panic_freeze"):
        action = "PANIC_FREEZE"
        title = "패닉 중입니다 — 보유주식 급매도와 신규 인버스를 모두 멈추세요"
        reason = (
            f"현재 주식 {current_weight * 100:.0f}%는 그대로 둡니다. "
            "폭락 당일의 기술적 매도는 반등 손실 위험이 커서, 진정 신호 뒤에만 다시 판단합니다."
        )
        next_check = "다음 종가에서 패닉 해제 여부"
    elif code == "CRASH":
        if current_weight > upper:
            action = "REDUCE"
            amount = min(equity - total * upper, step_cap)
            title = f"약한 종목부터 {amount:,.0f}만원만 축소하세요"
            reason = (
                f"주식 {current_weight * 100:.0f}%가 하락장 허용범위 상단 {upper * 100:.0f}%를 넘었습니다. "
                "전량매도가 아니라 한 번에 총자산 5%p까지만 줄입니다."
            )
            next_check = "5거래일 뒤 또는 20일선 회복 종가"
        else:
            title = "새 매수 없이 현재 비중을 유지하세요"
            reason = (
                f"주식 {current_weight * 100:.0f}%는 하락장 허용범위 {lower * 100:.0f}~{upper * 100:.0f}% 안입니다. "
                "현금은 바닥 확인 뒤 쓸 대기자금으로 둡니다."
            )
    elif code in {"BOTTOM_RECOVERY", "UPTREND"} and current_weight < lower:
        action = "ADD"
        amount = min(total * lower - equity, step_cap, cash * 0.10)
        if amount > 0:
            title = f"우량주·시장지수를 {amount:,.0f}만원만 1차 매수하세요"
            reason = (
                f"주식 {current_weight * 100:.0f}%가 {policy['label']} 허용범위 하단 "
                f"{lower * 100:.0f}%보다 낮습니다. 남은 현금의 10%와 총자산 5%p 중 작은 금액만 씁니다."
            )
            next_check = "다음 단계 추세 확인 종가"
    elif current_weight > upper:
        action = "TRIM"
        amount = min(equity - total * upper, step_cap)
        title = f"비중이 큰 종목에서 {amount:,.0f}만원만 이익실현하세요"
        reason = (
            f"주식 {current_weight * 100:.0f}%가 {policy['label']} 허용범위 상단 "
            f"{upper * 100:.0f}%를 넘었습니다. 목표는 예측이 아니라 위험 범위 복귀입니다."
        )
        next_check = "5거래일 뒤"
    elif code == "SIDEWAYS" and current_weight < lower:
        action = "ADD"
        amount = min(total * lower - equity, step_cap, cash * 0.10)
        if amount > 0:
            title = f"급락 추격 없이 {amount:,.0f}만원만 분할 매수하세요"
            reason = (
                f"주식 {current_weight * 100:.0f}%가 횡보장 허용범위 하단 {lower * 100:.0f}%보다 낮습니다. "
                "시장지수·우량주 위주로 비중만 복원합니다."
            )

    if amount <= 0 and action in {"ADD", "REDUCE", "TRIM"}:
        action = "HOLD"
        title = "오늘은 주문하지 마세요"
        reason = "계산된 조정 금액이 0원이므로 현재 비중을 유지합니다."

    return {
        "action": action,
        "title": title,
        "reason": reason,
        "amount": round(amount, 1),
        "side": "매수" if action == "ADD" else "매도" if action in {"REDUCE", "TRIM"} else "없음",
        "current_equity_amount": equity,
        "current_cash_amount": cash,
        "current_equity_weight": current_weight,
        "equity_band": (lower, upper),
        "cash_band": (1 - upper, 1 - lower),
        "next_check": next_check,
        "steps": [
            f"오늘 주문: {('없음' if amount <= 0 else f'{amount:,.0f}만원 {('매수' if action == 'ADD' else '매도')}')}",
            f"주식 허용범위: 총자산의 {lower * 100:.0f}~{upper * 100:.0f}%",
            f"다시 확인: {next_check}",
        ],
    }


def build_holding_action(
    stock_data: dict[str, Any],
    regime: dict[str, Any],
    holding_value: float | None = None,
    fundamental_score: int | None = None,
    pnl_pct: float | None = None,
) -> dict[str, Any]:
    """Give a conservative, close-confirmed action for one existing holding."""
    price = _safe_float(stock_data.get("Price"))
    ma20 = _safe_float(stock_data.get("MA20"))
    ma60 = _safe_float(stock_data.get("MA60"))
    rsi = _safe_float(stock_data.get("RSI_14"), 50.0)
    bb_upper = _safe_float(stock_data.get("BB_upper"))
    fund = 3 if fundamental_score is None else int(fundamental_score)
    pnl = _safe_float(pnl_pct, 0.0)
    value = max(_safe_float(holding_value, 0.0), 0.0)
    code = regime.get("code", "SIDEWAYS")

    action = "HOLD"
    label = "보유"
    sell_fraction = 0.0
    trigger = "시장 국면과 종목 추세 모두 매도 조건이 아닙니다."

    if regime.get("panic_freeze"):
        label = "매도 동결"
        trigger = "폭락 중 기술적 손절을 하지 않습니다. 기업 훼손 공시가 있을 때만 별도 재검토합니다."
    elif fund <= 1 and np.isfinite(price) and np.isfinite(ma60) and price < ma60:
        action = "REVIEW_REDUCE"
        label = "25% 축소 검토"
        sell_fraction = 0.25
        trigger = "펀더멘탈 약화와 60일선 이탈이 함께 확인됐습니다. 다음 거래일에 25%만 먼저 줄입니다."
    elif (
        code == "CRASH"
        and fund <= 2
        and np.isfinite(price)
        and np.isfinite(ma20)
        and np.isfinite(ma60)
        and price < ma60
        and ma20 < ma60
        and rsi > 32
    ):
        action = "REDUCE"
        label = "10% 축소"
        sell_fraction = 0.10
        trigger = "패닉은 끝났지만 종목의 20·60일 추세가 모두 약합니다. 한 번에 10%만 줄입니다."
    elif (
        code == "SIDEWAYS"
        and pnl > 0
        and (rsi >= 70 or (np.isfinite(price) and np.isfinite(bb_upper) and price >= bb_upper))
    ):
        action = "TRIM"
        label = "10% 이익실현"
        sell_fraction = 0.10
        trigger = "횡보장 상단·과매수 구간입니다. 전량매도가 아니라 원래 비중으로만 되돌립니다."
    elif (
        code == "UPTREND"
        and pnl > 0
        and rsi >= 75
        and np.isfinite(price)
        and np.isfinite(ma20)
        and price >= ma20 * 1.15
    ):
        action = "TRIM"
        label = "10% 과열 축소"
        sell_fraction = 0.10
        trigger = "상승 추세는 유지되지만 20일선에서 15% 이상 벌어진 과열 구간입니다."
    elif code == "BOTTOM_RECOVERY" and fund >= 3:
        label = "보유·추가매도 금지"
        trigger = "바닥 확인 후 회복 구간의 우량 보유주입니다. 20일선 재이탈 전까지 보유합니다."

    sell_value = value * sell_fraction if value else None
    return {
        "action": action,
        "label": label,
        "sell_fraction": sell_fraction,
        "sell_value": round(sell_value, 1) if sell_value is not None else None,
        "trigger": trigger,
        "execution": "종가 확인 후 다음 거래일 분할 실행",
    }


def _performance_metrics(strategy_returns: pd.Series, benchmark_returns: pd.Series) -> dict[str, float]:
    aligned = pd.concat(
        [strategy_returns.rename("strategy"), benchmark_returns.rename("benchmark")],
        axis=1,
    ).dropna()
    if aligned.empty:
        return {}
    strategy_curve = (1 + aligned["strategy"]).cumprod()
    benchmark_curve = (1 + aligned["benchmark"]).cumprod()
    years = max(len(aligned) / 252, 1 / 252)

    def _mdd(curve: pd.Series) -> float:
        return float((curve / curve.cummax() - 1).min() * 100)

    strategy_vol = float(aligned["strategy"].std() * np.sqrt(252) * 100)
    benchmark_vol = float(aligned["benchmark"].std() * np.sqrt(252) * 100)
    downside = aligned.loc[aligned["benchmark"] < 0]
    downside_capture = (
        float(downside["strategy"].sum() / downside["benchmark"].sum() * 100)
        if not downside.empty and downside["benchmark"].sum() != 0
        else np.nan
    )
    return {
        "strategy_total_return": float((strategy_curve.iloc[-1] - 1) * 100),
        "benchmark_total_return": float((benchmark_curve.iloc[-1] - 1) * 100),
        "strategy_annual_return": float((strategy_curve.iloc[-1] ** (1 / years) - 1) * 100),
        "benchmark_annual_return": float((benchmark_curve.iloc[-1] ** (1 / years) - 1) * 100),
        "strategy_mdd": _mdd(strategy_curve),
        "benchmark_mdd": _mdd(benchmark_curve),
        "strategy_volatility": strategy_vol,
        "benchmark_volatility": benchmark_vol,
        "downside_capture": downside_capture,
    }


def run_regime_backtest(
    kospi_history: pd.DataFrame,
    transaction_cost_bps: float = 15.0,
    review_days: int = 5,
    max_step: float = 0.05,
) -> dict[str, Any]:
    """Backtest the fixed, long-only playbook using next-day close returns."""
    features = build_market_features(kospi_history)
    if len(features) < 504:
        return {
            "status": "unavailable",
            "message": "국면 전략 검증에는 최소 504거래일 데이터가 필요합니다.",
        }

    regimes: list[str] = []
    panics: list[bool] = []
    for _, row in features.iterrows():
        code, panic, _ = _row_regime(row, bottom_score=0.0)
        regimes.append(code)
        panics.append(panic)
    features["Regime"] = regimes
    features["PanicFreeze"] = panics

    desired = {
        "CRASH": 0.50,
        "BOTTOM_RECOVERY": 0.65,
        "UPTREND": 0.85,
        "SIDEWAYS": 0.60,
    }
    lower_band = {key: value["equity_band"][0] for key, value in REGIME_POLICIES.items()}
    upper_band = {key: value["equity_band"][1] for key, value in REGIME_POLICIES.items()}
    weights: list[float] = []
    current_weight = 0.60
    last_trade = -review_days
    for i, row in enumerate(features.itertuples()):
        code = row.Regime
        if not row.PanicFreeze and i - last_trade >= review_days:
            if current_weight < lower_band[code]:
                current_weight = min(current_weight + max_step, desired[code])
                last_trade = i
            elif current_weight > upper_band[code]:
                current_weight = max(current_weight - max_step, desired[code])
                last_trade = i
        weights.append(current_weight)
    features["EquityWeight"] = weights

    benchmark_returns = features["Close"].pct_change().fillna(0.0)
    effective_weight = features["EquityWeight"].shift(1).fillna(0.60)
    turnover = features["EquityWeight"].diff().abs().shift(1).fillna(0.0)
    strategy_returns = (
        effective_weight * benchmark_returns
        - turnover * (transaction_cost_bps / 10_000)
    )
    valid = features["MA120"].notna()
    strategy_returns = strategy_returns.loc[valid]
    benchmark_returns = benchmark_returns.loc[valid]
    curve = pd.DataFrame(
        {
            "국면 전략": (1 + strategy_returns).cumprod(),
            "KOSPI 보유": (1 + benchmark_returns).cumprod(),
        }
    )
    split = max(int(len(curve) * 0.70), 1)
    holdout_index = curve.index[split:]
    holdout_strategy = strategy_returns.loc[holdout_index]
    holdout_benchmark = benchmark_returns.loc[holdout_index]
    return {
        "status": "ok",
        "metrics": _performance_metrics(strategy_returns, benchmark_returns),
        "holdout_metrics": _performance_metrics(holdout_strategy, holdout_benchmark),
        "holdout_start": (
            pd.Timestamp(holdout_index[0]).date().isoformat()
            if len(holdout_index)
            else None
        ),
        "equity_curve": curve,
        "latest_weight": float(features["EquityWeight"].iloc[-1]),
    }
