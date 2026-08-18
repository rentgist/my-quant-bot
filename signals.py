import pandas as pd
import numpy as np
from indicators import calc_rsi, calc_macd, get_rolling_rsi
import streamlit as st

# ═════════════════════════════════════════
# 공용 상수 (실시간 & 백테스트가 반드시 같은 값 사용)
# ═════════════════════════════════════════
GRIND_DOWN_RATIO   = 0.55   # 최근 20일 중 하락 마감일 비율 임계값
DIV_RSI_MARGIN     = 2.0    # RSI 다이버전스 인정 마진
KNIFE_1D_RET       = -2.5   # 떨어지는 칼날: 당일 급락 임계값 (%)
KNIFE_MA5_GAP      = -4.0   # 떨어지는 칼날: 5일선 이탈 임계값 (%)
KNIFE_PENALTY      = 20     # 칼날 감지 시 차감 점수
US_ENTRY_FLOOR     = 60.0   # 미국 선발대 검토 최소 환경점수
US_FULL_ENTRY      = 65.0   # 10% 선발대에 필요한 환경점수
US_CREDIT_RATIO_VETO = -0.02  # HYG/IEF 5일 -2% 이하는 명확한 신용 스트레스

# ═════════════════════════════════════════
# 공용 헬퍼
# ═════════════════════════════════════════
def credit_spread_ratio(hyg_hist, ief_hist, min_len=50):
    """HYG/IEF 비율 시계열 (신용 스프레드 프록시). 단일 진실 원천."""
    if hyg_hist is None or ief_hist is None or hyg_hist.empty or ief_hist.empty:
        return None
    try:
        df = pd.concat([hyg_hist['Close'], ief_hist['Close']], axis=1).ffill().dropna()
        if len(df) < min_len:
            return None
        df.columns = ['HYG', 'IEF']
        return df['HYG'] / df['IEF']
    except Exception:
        return None


def analyze_market_structure(close):
    """
    🧠 시장 구조/국면(Regime) 분석기 — v23.0 신규 핵심 모듈.

    기존 탐지기의 맹점 보완:
    - 🐻 Grinding Bear: VIX가 안 뛰는 '미지근한 지속 하락' (하락일 비율 + 50일선 기울기로 감지)
    - 🌊 Whipsaw: 변동성은 큰데 방향이 없는 '오르면서 빠지는' 횡보 (실현변동성 vs 순변화 괴리)
    - 🏗️ Basing: 바닥 다지기 (저점 높이기 + 20일선 탈환)
    - RSI 상승 다이버전스: 가격은 신저점인데 RSI 저점은 높아짐 → 매도 에너지 소진
    """
    out = {
        "regime": "⚪ 판별 불가", "drawdown": 0.0,
        "is_panic": False, "is_grind": False, "is_whipsaw": False, "is_basing": False,
        "bullish_div": False, "higher_low": False, "ma20_reclaim": False,
        "down_ratio": None, "days_since_high": None, "ma50_slope": 0.0,
        "dead_cross": False, "realized_vol": None,
    }
    if close is None or len(close) < 60:
        return out

    price     = float(close.iloc[-1])
    high_252  = float(close.rolling(252, min_periods=1).max().iloc[-1])
    drawdown  = (price / high_252 - 1) * 100
    out["drawdown"] = drawdown

    rets   = close.pct_change()
    ret_1d = float(rets.iloc[-1]) * 100

    # 최근 20일 중 하락 마감일 비율 — '조용한 자금 이탈' 감지의 핵심
    down_ratio = float((rets.iloc[-20:] < 0).mean())
    out["down_ratio"] = round(down_ratio * 100, 0)

    # 52주 고점 이후 경과 거래일
    window = close.iloc[-252:]
    out["days_since_high"] = int(len(window) - 1 - int(np.argmax(window.values)))

    ma20 = float(close.rolling(20).mean().iloc[-1])
    ma50 = float(close.rolling(50).mean().iloc[-1]) if len(close) >= 50 else price
    ma200 = float(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else None

    if len(close) >= 71:
        ma50_series = close.rolling(50).mean()
        out["ma50_slope"] = round((float(ma50_series.iloc[-1]) / float(ma50_series.iloc[-21]) - 1) * 100, 2)

    if ma200 is not None:
        out["dead_cross"] = (ma50 < ma200) and (price < ma200)

    # 실현 변동성 (20일, 연율화 %) — VIX가 못 잡는 실제 가격 요동 측정
    realized_vol = float(rets.iloc[-20:].std() * np.sqrt(252) * 100)
    out["realized_vol"] = round(realized_vol, 1)

    net_20d = (price / float(close.iloc[-21]) - 1) * 100 if len(close) >= 21 else 0.0

    # ── RSI 다이버전스 & 저점 구조 (최근 60일을 전반/후반 30일로 나눠 비교) ──
    rsi_series = get_rolling_rsi(close, 14)
    recent_p = close.iloc[-60:]
    recent_r = rsi_series.iloc[-60:]
    p1, p2 = float(recent_p.iloc[:30].min()), float(recent_p.iloc[30:].min())
    r1, r2 = float(recent_r.iloc[:30].min()), float(recent_r.iloc[30:].min())

    if p2 < p1 and r2 > r1 + DIV_RSI_MARGIN:
        out["bullish_div"] = True     # 가격 신저점 + RSI 저점 상승 = 매도세 소진 신호
    if p2 > p1 * 1.005:
        out["higher_low"] = True      # 저점 높이기 (바닥 구조의 필요조건)
    out["ma20_reclaim"] = price > ma20

    # ── 국면(Regime) 판별 ──
    is_panic   = (ret_1d <= KNIFE_1D_RET) or (drawdown <= -15 and realized_vol >= 25)
    is_grind   = (drawdown <= -7) and (down_ratio >= GRIND_DOWN_RATIO) and (out["ma50_slope"] < 0) and not is_panic
    is_whipsaw = (realized_vol >= 18) and (abs(net_20d) < 2.5) and not is_panic and not is_grind
    is_basing  = (drawdown <= -10) and out["higher_low"] and out["ma20_reclaim"] and not is_panic

    out.update({"is_panic": is_panic, "is_grind": is_grind,
                "is_whipsaw": is_whipsaw, "is_basing": is_basing})

    if drawdown > -5 and not is_whipsaw:
        out["regime"] = f"📈 고점권/상승 추세 (DD {drawdown:.1f}%)"
    elif is_panic:
        out["regime"] = f"🚨 급락 패닉 (DD {drawdown:.1f}%, 실현변동성 {realized_vol:.0f}%)"
    elif is_basing:
        out["regime"] = f"🏗️ 바닥 다지기 진행 (DD {drawdown:.1f}%, 저점 높이는 중)"
    elif is_grind:
        out["regime"] = f"🐻 완만한 하락 — Grinding Bear (DD {drawdown:.1f}%, 하락일 {down_ratio*100:.0f}%)"
    elif is_whipsaw:
        out["regime"] = f"🌊 고변동 횡보 — Whipsaw (DD {drawdown:.1f}%, 변동성 {realized_vol:.0f}%)"
    elif drawdown > -12:
        out["regime"] = f"📉 단기 조정 (DD {drawdown:.1f}%)"
    elif drawdown > -20:
        out["regime"] = f"🟠 깊은 조정 (DD {drawdown:.1f}%)"
    else:
        out["regime"] = f"🔴 약세장 진행 (DD {drawdown:.1f}%)"

    return out


# ═════════════════════════════════════════
# 🇺🇸 레이어 1: 미국 전용 위험 탐지기 (v23.0: 스텔스 약세장 레이어 추가)
# ═════════════════════════════════════════
def calculate_us_risk_radar(vix_hist, vix3m_hist, hyg_hist, ief_hist, spy_hist, tnx_hist=None, irx_hist=None, mu_hist=None, soxx_hist=None):
    alerts = []
    danger_count = 0

    curr_vix   = float(vix_hist['Close'].iloc[-1])   if not vix_hist.empty  else None
    curr_vix3m = float(vix3m_hist['Close'].iloc[-1]) if not vix3m_hist.empty else None

    # ── ① VIX 기간구조 (백워데이션 = 단기 패닉) ──
    if curr_vix and curr_vix3m:
        if curr_vix > curr_vix3m * 1.05:
            alerts.append(("🔴", f"VIX 백워데이션 발생 ({curr_vix:.1f} > {curr_vix3m:.1f}). 단기 패닉 초입."))
            danger_count += 2
        elif curr_vix > curr_vix3m:
            alerts.append(("🟠", "VIX 백워데이션 진입 중. 예비 주시."))
            danger_count += 1
        else:
            alerts.append(("🟢", "VIX 콘탱고 정상. 시장 구조 안정."))

    # ── ② VIX 상대 급등 + 절대 레벨 ──
    vix_spike = 0
    if curr_vix:
        vix_ma20 = float(vix_hist['Close'].rolling(20).mean().iloc[-1]) if len(vix_hist) >= 20 else curr_vix
        vix_spike = (curr_vix - vix_ma20) / vix_ma20 * 100 if vix_ma20 > 0 else 0

        if vix_spike >= 40:
            alerts.append(("🚨", f"VIX 폭등 경보 (+{vix_spike:.1f}% vs 20일평균) — 기습적인 공포장 진입."))
            danger_count += 2
        elif vix_spike >= 20:
            alerts.append(("🔴", f"VIX 단기 급등 (+{vix_spike:.1f}% vs 20일평균) — 변동성 팽창 중."))
            danger_count += 1

        if curr_vix >= 30:
            alerts.append(("🔴", f"VIX {curr_vix:.1f} — 절대적 공포 확산 구간."))
            danger_count += 2
        elif curr_vix >= 22:
            alerts.append(("🟠", f"VIX {curr_vix:.1f} — 절대적 불안 상승 구간."))
            danger_count += 1
        else:
            if vix_spike < 20:
                alerts.append(("🟢", f"VIX {curr_vix:.1f} — 평온 구간."))

    # ── ③ 신용 스프레드 (공용 헬퍼 — 중복 로직 제거) ──
    credit_danger = False
    ratio = credit_spread_ratio(hyg_hist, ief_hist)
    if ratio is not None:
        ma20 = float(ratio.rolling(20).mean().iloc[-1])
        ma50 = float(ratio.rolling(50).mean().iloc[-1])
        curr = float(ratio.iloc[-1])
        if curr < ma50 * 0.97:
            alerts.append(("🔴", "신용 스프레드 위험 이탈. 기관 투매 감지."))
            danger_count += 2
            credit_danger = True
        elif curr < ma20:
            alerts.append(("🟠", "신용 스프레드 단기 이탈. 주시 필요."))
            danger_count += 1
            credit_danger = True
        else:
            alerts.append(("🟢", "신용 스프레드 안정 (정배열)."))
    else:
        alerts.append(("⚪", "신용 스프레드 산출 불가."))

    # ── ④ SPY 급락 & 킬 스위치 교차 검증 ──
    if not spy_hist.empty and len(spy_hist) >= 6:
        spy_1d_ret = (float(spy_hist['Close'].iloc[-1]) / float(spy_hist['Close'].iloc[-2]) - 1) * 100
        spy_5d_ret = (float(spy_hist['Close'].iloc[-1]) / float(spy_hist['Close'].iloc[-6]) - 1) * 100

        if spy_1d_ret <= -1.5 or spy_5d_ret <= -3.0:
            if credit_danger:
                alerts.append(("🚨", f"글로벌 킬 스위치 발동: SPY 급락({spy_1d_ret:.1f}%) & 신용 경색. 진짜 위기."))
                danger_count += 3
            else:
                alerts.append(("⚪", f"SPY 급락({spy_1d_ret:.1f}%) 발생, 단 신용 시장 평온. (단순 차익실현 추정)"))
        else:
            alerts.append(("🟢", f"SPY 단기 매크로 추세 안정적 ({spy_1d_ret:+.1f}%)."))

    # ── ⑤ 🆕 스텔스 약세장 레이어 (급등이 아닌 '구조'로 위험 감지) ──
    if not spy_hist.empty:
        struct = analyze_market_structure(spy_hist['Close'])
        dd = struct["drawdown"]

        if struct["is_grind"]:
            alerts.append(("🔴", f"스텔스 약세장(Grinding Bear) 감지 — VIX 급등 없이 최근 20일 중 "
                                 f"{struct['down_ratio']:.0f}%가 하락 마감, 50일선 기울기 {struct['ma50_slope']:+.1f}%. "
                                 f"조용한 자금 이탈이 진행 중."))
            danger_count += 2

        if dd <= -8 and curr_vix is not None and curr_vix < 20:
            alerts.append(("🟠", f"VIX 안일(Complacency) 다이버전스 — 지수는 고점 대비 {dd:.1f}% 빠졌는데 "
                                 f"VIX {curr_vix:.1f}로 공포 미반영. 헷지 수요 부재 = 추가 하락 시 무방비."))
            danger_count += 1

        if struct["dead_cross"]:
            alerts.append(("🔴", "장기 추세 훼손 — 50일선 < 200일선 (데드크로스) & 주가 200일선 이탈."))
            danger_count += 1

        if struct["is_whipsaw"]:
            alerts.append(("🟡", f"고변동 횡보(Whipsaw) 국면 — 실현변동성 {struct['realized_vol']:.0f}%인데 "
                                 f"20일 순변화는 미미. 추세 매매 실패 확률 높음 → 현금 비중 유지 유리."))
            danger_count += 1

    # ── ⑥ 장단기 금리 역전 (수익률 곡선 역전 = 경기침체 선행 신호) ──
    # ^IRX: 3개월 T-Bill, yfinance는 이미 % 단위로 반환 (예: 5.20)
    if tnx_hist is not None and irx_hist is not None and not tnx_hist.empty and not irx_hist.empty:
        try:
            tnx_val = float(tnx_hist['Close'].dropna().iloc[-1])  # 10년물 (%)
            irx_val = float(irx_hist['Close'].dropna().iloc[-1])   # 3개월물 (% 그대로 사용, /10 제거)
            spread = tnx_val - irx_val  # 장단기 스프레드 (양수=정상, 음수=역전)

            if spread <= -0.5:
                alerts.append(("🚨", f"장단기 금리 완전 역전 (10Y-3M: {spread:+.2f}%p) — 경기침체 강력 선행 신호. 성장주 밸류에이션 직격."))
                danger_count += 2
            elif spread <= 0:
                alerts.append(("🔴", f"장단기 금리 역전 발생 (10Y-3M: {spread:+.2f}%p) — 경기침체 경보 발령. 성장주 할인율 상승 위험."))
                danger_count += 1
            elif spread <= 0.5:
                alerts.append(("🟡", f"장단기 금리차 축소 (10Y-3M: {spread:+.2f}%p) — 역전 경계선 접근 중. 주시 필요."))
            else:
                alerts.append(("🟢", f"장단기 금리차 정상 (10Y-3M: {spread:+.2f}%p) — 수익률 곡선 건강."))
        except Exception:
            alerts.append(("⚪", "장단기 금리차 산출 불가."))
    
    # ── ⑦ 🆕 반도체 업황 건강도 (MU vs SOXX 상대 강도 = DRAM 업황 프록시) ──
    if mu_hist is not None and soxx_hist is not None and not mu_hist.empty and not soxx_hist.empty:
        try:
            # 최근 20거래일 수익률 비교
            mu_20d   = (float(mu_hist['Close'].dropna().iloc[-1]) / float(mu_hist['Close'].dropna().iloc[-21]) - 1) * 100
            soxx_20d = (float(soxx_hist['Close'].dropna().iloc[-1]) / float(soxx_hist['Close'].dropna().iloc[-21]) - 1) * 100
            rel_strength = mu_20d - soxx_20d  # 양수 = MU 강세 = DRAM 업황 호조

            # 반도체 업황은 정보 제공 전용 — 노이즈가 심해 danger_count에 미반영
            if rel_strength >= 5:
                alerts.append(("🟢", f"반도체 업황 강세 — MU(마이크론) 20일 수익률이 SOX 대비 {rel_strength:+.1f}%p 초과 (DRAM 수요 회복 시그널). [참고용]"))
            elif rel_strength <= -5:
                alerts.append(("🟠", f"반도체 업황 약세 — MU 20일 수익률이 SOX 대비 {rel_strength:+.1f}%p 부진 (DRAM 공급 과잉 경고). [참고용, 점수 미반영]"))
            else:
                alerts.append(("🟡", f"반도체 업황 중립 — MU vs SOX 상대 강도 {rel_strength:+.1f}%p (방향성 탐색 중). [참고용]"))
        except Exception:
            alerts.append(("⚪", "반도체 업황 지표 산출 불가."))

    # 감지 항목이 늘어난 만큼 등급 컷도 상향 (과잉 경보 방지)
    if danger_count >= 7:
        grade = "🚨 글로벌 마스터 킬 스위치 작동 — 시스템적 유동성 위기."
        color = "#ff0000"
    elif danger_count >= 5:
        grade = "🔴 글로벌 위기 경보 — 폭락 초입 가능성."
        color = "#ff4b4b"
    elif danger_count >= 3:
        grade = "🟠 글로벌 주의 단계 — 신규 진입 자제."
        color = "#ff9900"
    elif danger_count >= 1:
        grade = "🟡 글로벌 관찰 단계 — 경미한 이상 신호."
        color = "#fcca46"
    else:
        grade = "🟢 글로벌 마스터 이상 없음 — 매크로 환경 정상."
        color = "#21c354"

    return grade, color, alerts, danger_count


# ═════════════════════════════════════════
# 🇰🇷 레이어 1: 한국 전용 위험 탐지기
# (v23.0: 중복 정의 제거 — 정교 버전(MACD+VKOSPI 이격) 단일화 + 스텔스 감지 추가)
# ═════════════════════════════════════════
def calculate_kr_risk_radar(vkospi_hist, usdkrw_hist, kospi_hist):
    alerts = []
    danger_count = 0

    # ── ① 환율: 급등 + RSI + MACD 추세 교차 검증 (조기경보) ──
    if not usdkrw_hist.empty and len(usdkrw_hist) >= 20:
        curr_krw   = float(usdkrw_hist['Close'].iloc[-1])
        krw_5d_ago = float(usdkrw_hist['Close'].iloc[-6])
        krw_surge  = (curr_krw - krw_5d_ago) / krw_5d_ago * 100
        krw_rsi    = calc_rsi(usdkrw_hist['Close'], 14)
        krw_ma20   = float(usdkrw_hist['Close'].rolling(20).mean().iloc[-1])
        _, krw_macd_dir = calc_macd(usdkrw_hist['Close'])

        if krw_surge >= 1.5 or (curr_krw > krw_ma20 and krw_rsi and krw_rsi >= 65):
            alerts.append(("🔴", f"환율 단기 폭등/추세이탈 (+{krw_surge:.1f}%, RSI {krw_rsi:.1f}) — 외국인 엑소더스 징후."))
            danger_count += 2
        elif krw_surge >= 0.8 or (krw_rsi and krw_rsi >= 55) or (krw_macd_dir == "🟢상승" and curr_krw > krw_ma20):
            alerts.append(("🟠", f"환율 상승세 (+{krw_surge:.1f}%) 및 MACD 상승 — 외국인 수급 악화 조기 경보."))
            danger_count += 1
        else:
            alerts.append(("🟢", f"환율 안정적 ({curr_krw:,.1f}원) — 외인 수급 이탈 우려 낮음."))

    # ── ② VKOSPI: 20일 이격(spike) + 절대 레벨 + 5일 급등 ──
    if not vkospi_hist.empty and len(vkospi_hist) >= 20:
        curr_vk  = float(vkospi_hist['Close'].iloc[-1])
        vk_ma20  = float(vkospi_hist['Close'].rolling(20).mean().iloc[-1])
        vk_spike = (curr_vk - vk_ma20) / vk_ma20 * 100 if vk_ma20 > 0 else 0
        vk_5d_ago = float(vkospi_hist['Close'].iloc[-6])
        vk_surge  = (curr_vk - vk_5d_ago) / vk_5d_ago * 100 if vk_5d_ago > 0 else 0

        if vk_spike >= 30 or curr_vk >= 25 or vk_surge >= 25:
            alerts.append(("🔴", f"VKOSPI 급등 ({curr_vk:.1f}, +{vk_spike:.1f}% vs 20일평균) — 기관/외인 하락 헷지 팽창."))
            danger_count += 2
        elif vk_spike >= 15 or curr_vk >= 18 or vk_surge >= 15:
            alerts.append(("🟠", f"VKOSPI 불안 ({curr_vk:.1f}) — 파생 변동성 확대 조짐."))
            danger_count += 1
        else:
            alerts.append(("🟢", f"VKOSPI 평온 ({curr_vk:.1f}) — 하방 압력 낮음."))

    # ── ③ KOSPI 5일 낙폭 ──
    if not kospi_hist.empty and len(kospi_hist) >= 6:
        k_5d_ret = (float(kospi_hist['Close'].iloc[-1]) / float(kospi_hist['Close'].iloc[-6]) - 1) * 100
        if k_5d_ret <= -4:
            alerts.append(("🔴", f"KOSPI 5일 급락 ({k_5d_ret:.1f}%) — 프로그램 및 동반 투매 감지."))
            danger_count += 1
        elif k_5d_ret <= -2:
            alerts.append(("🟠", f"KOSPI 5일 하락 ({k_5d_ret:.1f}%) — 단기 매도 우위."))
        else:
            alerts.append(("🟢", f"KOSPI 단기 추세 ({k_5d_ret:+.1f}%) — 안정적."))

    # ── ④ 🆕 KOSPI 스텔스 약세 (미지근한 지속 하락 감지) ──
    if not kospi_hist.empty:
        struct = analyze_market_structure(kospi_hist['Close'])
        if struct["is_grind"]:
            alerts.append(("🔴", f"KOSPI 스텔스 약세 감지 — 최근 20일 중 {struct['down_ratio']:.0f}%가 하락 마감, "
                                 f"50일선 우하향 ({struct['ma50_slope']:+.1f}%). 완만한 외인 이탈형 하락."))
            danger_count += 2
        elif struct["is_whipsaw"]:
            alerts.append(("🟡", f"KOSPI 고변동 횡보 — 변동성 {struct['realized_vol']:.0f}% 대비 방향성 부재. 관망 유리."))
            danger_count += 1
        else:
            alerts.append(("🟢", f"KOSPI 시장 구조 건전 — 스텔스 약세 및 고변동 징후 없음."))

    if danger_count >= 5:
        grade = "🔴 한국 위기 경보 — 외인 이탈 및 폭락 초입 우려."
        color = "#ff4b4b"
    elif danger_count >= 3:
        grade = "🟠 한국 주의 단계 — 수급/환율 불안정."
        color = "#ff9900"
    elif danger_count >= 1:
        grade = "🟡 한국 관찰 단계 — 경미한 수급 꼬임 감지."
        color = "#fcca46"
    else:
        grade = "🟢 한국 이상 없음 — 국내 수급 환경 안정적."
        color = "#21c354"

    return grade, color, alerts, danger_count


# ═════════════════════════════════════════
# 진바닥 탐지기 — 공용 스코어러
# (실시간 & 백테스트가 '동일 함수'를 사용 → 점수 스케일 완전 통일)
# ═════════════════════════════════════════
def _score_bottom(drawdown, rsi, vix, cnn=None, details=None):
    """
    미국 바닥 코어 점수. CNN 유무와 무관하게 항상 '만점 대비 %'로 정규화.
    → 실시간(CNN 포함, 100점 만점)과 백테스트(CNN 제외, 80점 만점)가 같은 자로 비교 가능.
    """
    def _log(msg):
        if details is not None:
            details.append(msg)

    s, maxs = 0, 80  # Drawdown 35 + RSI 20 + VIX 25

    # Drawdown 점수: -5%부터 점수 시작 (기존 -8% 기준에서 완화)
    if drawdown <= -25:   s += 35; _log(f"🟢 대세 하락장 낙폭 ({drawdown:.1f}%) [+35/35]")
    elif drawdown <= -15: s += 22; _log(f"🟢 깊은 조정 ({drawdown:.1f}%) [+22/35]")
    elif drawdown <= -10: s += 14; _log(f"🟡 중간 조정 ({drawdown:.1f}%) [+14/35]")
    elif drawdown <= -5:  s += 7;  _log(f"🟡 얕은 조정 ({drawdown:.1f}%) [+7/35]")
    else: _log(f"⚪ 고점 근처 ({drawdown:.1f}%) [+0/35]")

    if rsi is not None:
        if rsi <= 30:   s += 20; _log(f"🟢 RSI 극단 과매도 ({rsi:.1f}) [+20/20]")
        elif rsi <= 38: s += 12; _log(f"🟢 RSI 과매도 ({rsi:.1f}) [+12/20]")
        elif rsi <= 45: s += 5;  _log(f"🟡 RSI 과매도 진입 ({rsi:.1f}) [+5/20]")
        else: _log(f"⚪ RSI 정상 ({rsi:.1f}) [+0/20]")

    if vix is not None:
        if vix >= 40:   s += 25; _log(f"🟢 VIX 극단 패닉 ({vix:.1f}) [+25/25]")
        elif vix >= 32: s += 20; _log(f"🟢 VIX 패닉 투매 ({vix:.1f}) [+20/25]")
        elif vix >= 26: s += 12; _log(f"🟡 VIX 공포 확산 ({vix:.1f}) [+12/25]")
        elif vix >= 22: s += 6;  _log(f"🟡 VIX 상승 주의 ({vix:.1f}) [+6/25]")
        elif vix >= 18: s += 2;  _log(f"⚪ VIX 경계 구간 ({vix:.1f}) [+2/25]")
        else: _log(f"⚪ VIX 평온 ({vix:.1f}) [+0/25]")

    if cnn is not None:
        maxs += 20
        if cnn <= 15: s += 20; _log(f"🟢 F&G 역사적 패닉 ({cnn}) [+20/20]")
        elif cnn <= 25: s += 15; _log(f"🟢 F&G 극단 공포 ({cnn}) [+15/20]")
        elif cnn <= 35: s += 8;  _log(f"🟡 F&G 공포 구간 ({cnn}) [+8/20]")
        elif cnn <= 45: s += 3;  _log(f"⚪ F&G 약한 공포 ({cnn}) [+3/20]")
        else: _log(f"⚪ F&G 중립~탐욕 ({cnn}) [+0/20]")

    return min(int(round(s / maxs * 100)), 100)


def _apply_structure_bonus(score, struct, details):
    """🆕 구조 보너스 — '충분히 빠졌다'를 넘어 '빠짐이 끝나간다'를 점수화."""
    dd = struct["drawdown"]
    if struct["is_grind"] and dd <= -10:
        score += 8
        details.append("🟢 [구조] Grinding Bear 성숙 보정 — VIX가 못 잡는 완만한 하락의 누적 낙폭 반영 [+8점]")
    if struct["bullish_div"]:
        score += 10
        details.append("🟢 [구조] RSI 상승 다이버전스 — 가격 신저점에도 매도 에너지 소진 중 [+10점]")
    if struct["higher_low"] and dd <= -8:
        score += 5
        details.append("🟢 [구조] 저점 높이기(Higher Low) 확인 — 바닥 다지기 진행 [+5점]")
    if struct["ma20_reclaim"] and dd <= -10:
        score += 5
        details.append("🟢 [구조] 20일선 탈환 — 단기 수급 회복 [+5점]")
    return min(int(score), 100)


def _apply_falling_knife(score, close, details):
    """떨어지는 칼날 안전장치 (실시간·백테스트 공용 임계값)."""
    is_knife = False
    if len(close) >= 5:
        ret_1d  = (float(close.iloc[-1]) / float(close.iloc[-2]) - 1) * 100
        ma5     = float(close.rolling(5).mean().iloc[-1])
        gap_ma5 = (float(close.iloc[-1]) - ma5) / ma5 * 100
        if ret_1d <= KNIFE_1D_RET or gap_ma5 <= KNIFE_MA5_GAP:
            is_knife = True
            if score >= 35:
                details.append(f"🚨 [Safety Catch] 당일 급락({ret_1d:.1f}%) 또는 5일선 심각한 이탈({gap_ma5:.1f}%). "
                               f"브레이크(양봉) 확인 후 진입 권장. (-{KNIFE_PENALTY}점 차감)")
                score = max(score - KNIFE_PENALTY, 0)
    return score, is_knife


def _verdict_from_score(score, drawdown, is_knife):
    if drawdown > -5: verdict = "📈 고점권 — 바닥 탐지 불가"
    elif score >= 70: verdict = "🔥 강한 바닥 후보 (가치 관찰 구간)"
    elif score >= 50: verdict = "🟢 바닥 후보 관찰 구간"
    elif score >= 35: verdict = "🟡 조정 진행 중 (추가 하락 여지)"
    else: verdict = "⚪ 바닥 조건 미충족"
    if is_knife and score >= 35:
        verdict = "⚠️ 떨어지는 칼날 (관망 권장)"
    return verdict


def calculate_us_bottom_finder(spy_hist, vix_hist, cnn_score):
    if spy_hist is None or spy_hist.empty:
        return 0, "데이터 부족", [], "알 수 없음"

    spy_close = spy_hist['Close']
    struct = analyze_market_structure(spy_close)
    drawdown = struct["drawdown"]
    market_phase = struct["regime"]

    spy_rsi  = calc_rsi(spy_close, 14)
    curr_vix = float(vix_hist['Close'].iloc[-1]) if not vix_hist.empty else None

    details = []
    score = _score_bottom(drawdown, spy_rsi, curr_vix, cnn_score, details=details)
    score = _apply_structure_bonus(score, struct, details)
    score, is_knife = _apply_falling_knife(score, spy_close, details)
    verdict = _verdict_from_score(score, drawdown, is_knife)

    return score, verdict, details, market_phase


def calculate_kr_bottom_finder(kospi_hist, vkospi_hist, usdkrw_hist):
    if kospi_hist is None or kospi_hist.empty:
        return 0, "데이터 부족", [], "알 수 없음"

    kospi_close = kospi_hist['Close']
    struct = analyze_market_structure(kospi_close)
    drawdown = struct["drawdown"]
    market_phase = struct["regime"]

    score, max_score, details = 0, 0, []
    kill_switch = False

    # ① Drawdown (만점 35)
    max_score += 35
    dd = -drawdown
    if dd >= 20: 
        score += 35; details.append(f"🟢 KOSPI 대세 하락장 ({drawdown:.1f}%) [+35/35]")
    elif dd >= 12: 
        pts = 22 + (dd - 12) * (35 - 22) / (20 - 12)
        score += pts; details.append(f"🟢 KOSPI 깊은 조정 ({drawdown:.1f}%) [+{pts:.1f}/35]")
    elif dd >= 7: 
        pts = 10 + (dd - 7) * (22 - 10) / (12 - 7)
        score += pts; details.append(f"🟡 KOSPI 단기 조정 ({drawdown:.1f}%) [+{pts:.1f}/35]")
    elif dd > 0:
        pts = dd * 10 / 7
        score += pts; details.append(f"⚪ 얕은 조정 ({drawdown:.1f}%) [+{pts:.1f}/35]")
    else: 
        details.append(f"⚪ 고점 근처 ({drawdown:.1f}%) [+0/35]")

    # ② RSI (만점 20)
    kr_rsi = calc_rsi(kospi_close, 14)
    if kr_rsi is not None:
        max_score += 20
        if kr_rsi <= 30: 
            score += 20; details.append(f"🟢 KOSPI 극단 과매도 ({kr_rsi:.1f}) [+20/20]")
        elif kr_rsi <= 40: 
            pts = 12 + (40 - kr_rsi) * (20 - 12) / (40 - 30)
            score += pts; details.append(f"🟢 KOSPI 과매도 ({kr_rsi:.1f}) [+{pts:.1f}/20]")
        elif kr_rsi <= 45: 
            pts = 5 + (45 - kr_rsi) * (12 - 5) / (45 - 40)
            score += pts; details.append(f"🟡 KOSPI 과매도 진입 ({kr_rsi:.1f}) [+{pts:.1f}/20]")
        elif kr_rsi <= 60:
            pts = (60 - kr_rsi) * 5 / (60 - 45)
            score += pts; details.append(f"⚪ KOSPI RSI 정상 ({kr_rsi:.1f}) [+{pts:.1f}/20]")
        else: 
            details.append(f"⚪ KOSPI RSI 높음 ({kr_rsi:.1f}) [+0/20]")

    # ③ VKOSPI (만점 25) — 누락 시 만점에서 자동 제외 (하드코딩 환산 제거)
    curr_vkospi = float(vkospi_hist['Close'].iloc[-1]) if not vkospi_hist.empty else None
    if curr_vkospi and not np.isnan(curr_vkospi):
        max_score += 25
        if curr_vkospi >= 25: 
            score += 25; details.append(f"🟢 VKOSPI 패닉 투매 ({curr_vkospi:.1f}) [+25/25]")
        elif curr_vkospi >= 20: 
            pts = 15 + (curr_vkospi - 20) * (25 - 15) / (25 - 20)
            score += pts; details.append(f"🟢 VKOSPI 공포 확산 ({curr_vkospi:.1f}) [+{pts:.1f}/25]")
        elif curr_vkospi >= 16: 
            pts = 5 + (curr_vkospi - 16) * (15 - 5) / (20 - 16)
            score += pts; details.append(f"🟡 VKOSPI 상승 주의 ({curr_vkospi:.1f}) [+{pts:.1f}/25]")
        elif curr_vkospi >= 12:
            pts = (curr_vkospi - 12) * 5 / (16 - 12)
            score += pts; details.append(f"⚪ VKOSPI 평온 ({curr_vkospi:.1f}) [+{pts:.1f}/25]")
        else: 
            details.append(f"⚪ VKOSPI 매우 평온 ({curr_vkospi:.1f}) [+0/25]")
    else:
        details.append("⚪ VKOSPI 데이터 누락 — 만점에서 제외해 자동 보정 [+0점]")

    # ④ 환율 (만점 20) + 킬 스위치
    if not usdkrw_hist.empty:
        krw_rsi = calc_rsi(usdkrw_hist['Close'], 14)
        if krw_rsi is not None:
            max_score += 20
            if krw_rsi <= 55: 
                score += 20; details.append(f"🟢 환율 안정 및 원화 강세 (RSI {krw_rsi:.1f}) [+20/20]")
            elif krw_rsi <= 65: 
                pts = 10 + (65 - krw_rsi) * (20 - 10) / (65 - 55)
                score += pts; details.append(f"🟡 환율 약세 구간 (RSI {krw_rsi:.1f}) [+{pts:.1f}/20]")
            elif krw_rsi <= 75:
                pts = (75 - krw_rsi) * 10 / (75 - 65)
                score += pts; details.append(f"🚨 환율 단기 폭등 위험 (RSI {krw_rsi:.1f}) [+{pts:.1f}/20]")
            else:
                details.append(f"🚨 환율 극단적 폭등 (RSI {krw_rsi:.1f}) [+0/20]")
                if krw_rsi > 70 and drawdown > -10:
                    kill_switch = True
                    details.append("💣 [Kill Switch] 코스피 낙폭 적은데 환율 초급등. 폭락 초입 가능성으로 최종 점수 30점 제한.")

    # 만점 정규화 → 구조 보너스 → 킬 스위치 → 떨어지는 칼날
    score = min(int(round(score / max_score * 100)), 100) if max_score > 0 else 0
    score = _apply_structure_bonus(score, struct, details)
    if kill_switch:
        score = min(score, 30)
    score, is_knife = _apply_falling_knife(score, kospi_close, details)
    verdict = _verdict_from_score(score, drawdown, is_knife)

    return score, verdict, details, market_phase


# ═════════════════════════════════════════
# 레이어 3: 회복 확인
# ═════════════════════════════════════════
def calculate_recovery_confirmation(rsp_hist, spy_hist, hyg_hist, ief_hist):
    signals = []
    recovery_score = 0

    if not rsp_hist.empty and not spy_hist.empty:
        try:
            df_b = pd.concat([rsp_hist['Close'], spy_hist['Close']], axis=1).ffill().dropna()
            df_b.columns = ['RSP', 'SPY']
            df_b['R'] = df_b['RSP'] / df_b['SPY']
            curr_r = float(df_b['R'].iloc[-1])
            ma50_r = float(df_b['R'].rolling(50, min_periods=1).mean().iloc[-1])
            if curr_r > ma50_r:
                pct_above = (curr_r - ma50_r) / ma50_r * 100
                signals.append(("🟢", f"시장 Breadth 회복 — 동일가중(RSP)이 MA50 +{pct_above:.1f}% 상회. 중소형주도 반등 동참."))
                recovery_score += 50
            else:
                pct_below = (ma50_r - curr_r) / ma50_r * 100
                signals.append(("🔴", f"Breadth 미회복 — 동일가중(RSP)이 MA50 -{pct_below:.1f}% 하회. 대형주만 오르는 편중 장세."))
        except Exception:
            signals.append(("⚪", "Breadth 데이터 산출 불가."))

    ratio = credit_spread_ratio(hyg_hist, ief_hist)
    if ratio is not None:
        curr = float(ratio.iloc[-1])
        ma20 = float(ratio.rolling(20).mean().iloc[-1])
        ma50 = float(ratio.rolling(50).mean().iloc[-1])
        if curr > ma20 > ma50:
            signals.append(("🟢", "신용시장 회복 확인 — HYG/IEF 정배열. 기관이 위험자산으로 복귀 중."))
            recovery_score += 50
        elif curr > ma50:
            signals.append(("🟡", "신용시장 부분 회복 — MA50 위. 아직 완전 정배열은 아님."))
            recovery_score += 25
        else:
            signals.append(("🔴", "신용시장 미회복 — 아직 기관 자금 복귀 확인 안 됨."))
    else:
        signals.append(("⚪", "Credit 데이터 산출 불가."))

    if recovery_score >= 100: verdict = "🟢 반등 신뢰도 높음 — Breadth + Credit 동시 회복"
    elif recovery_score >= 50: verdict = "🟡 반등 신뢰도 보통 — 일부만 회복"
    else: verdict = "🔴 반등 신뢰도 낮음 — 아직 회복 확인 안 됨"

    return verdict, signals, recovery_score


def calculate_macro_risk_gauge(kospi_hist, usdkrw_hist):
    details = []
    macro_score = 0

    if not kospi_hist.empty and len(kospi_hist) >= 50:
        try:
            close = kospi_hist['Close']
            curr_k = float(close.iloc[-1])
            ma20 = float(close.rolling(20).mean().iloc[-1])
            ma50 = float(close.rolling(50).mean().iloc[-1])
            
            if curr_k > ma20 and curr_k > ma50:
                details.append(("🟢", "KOSPI 추세 강함 — 20일선 및 50일선 상회 (+50점)"))
                macro_score += 50
            elif curr_k > ma20:
                details.append(("🟡", "KOSPI 단기 회복 — 20일선 상회, 50일선 하회 (+25점)"))
                macro_score += 25
            else:
                details.append(("🔴", "KOSPI 추세 약함 — 20일선 하회 (+0점)"))
        except Exception:
            details.append(("⚪", "KOSPI 데이터 산출 불가"))

    if not usdkrw_hist.empty and len(usdkrw_hist) >= 50:
        try:
            curr_fx = float(usdkrw_hist['Close'].iloc[-1])
            ma20_fx = float(usdkrw_hist['Close'].rolling(20).mean().iloc[-1])
            ma50_fx = float(usdkrw_hist['Close'].rolling(50).mean().iloc[-1])
            
            if curr_fx < ma20_fx and curr_fx < ma50_fx:
                details.append(("🟢", "환율 안정 — 20일선 및 50일선 하회 (+50점)"))
                macro_score += 50
            elif curr_fx < ma20_fx:
                details.append(("🟡", "환율 진정 중 — 20일선 하회, 50일선 상회 (+25점)"))
                macro_score += 25
            else:
                details.append(("🔴", "환율 불안정 — 20일선 상회 (+0점)"))
        except Exception:
            details.append(("⚪", "환율 데이터 산출 불가"))

    if macro_score >= 80:
        status = "🟢 매크로 안전 (안심 진입 구간)"
    elif macro_score >= 50:
        status = "🟡 매크로 조심 (확인 필요)"
    else:
        status = "🔴 매크로 위험 (보조 신호 필수)"

    return macro_score, status, details


def calculate_cashflow_signal(
    foreign_futures,
    oi_signal,
    kospi_hist,
    foreign_cashflow=None,
    market_breadth=None,
    rsp_change_pct=None,
):
    """한국 자금흐름을 현물·시장폭 중심으로 평가한다.

    외국인 선물은 현물 헤지·차익거래가 섞일 수 있으므로 확인 변수로만
    사용한다. 미결제약정도 가격 방향과 결합하지 않으면 롱·숏을 구분할 수
    없으므로, 단순 증가 자체에는 점수를 부여하지 않는다.
    """
    details = []
    flow_score = 0

    # 1. KOSPI 가격 추세 (30점 만점)
    if kospi_hist is not None and not kospi_hist.empty and len(kospi_hist) >= 20:
        try:
            close = kospi_hist["Close"]
            current = float(close.iloc[-1])
            ma5 = float(close.rolling(5).mean().iloc[-1])
            ma20 = float(close.rolling(20).mean().iloc[-1])
            if current >= ma5:
                flow_score += 15
                details.append(("🟢", "KOSPI 5일선 유지 [+15점]"))
            else:
                details.append(("🔴", "KOSPI 5일선 하회 [+0점]"))
            if current >= ma20:
                flow_score += 15
                details.append(("🟢", "KOSPI 20일선 유지 [+15점]"))
            else:
                details.append(("🔴", "KOSPI 20일선 하회 [+0점]"))
        except Exception:
            details.append(("⚪", "KOSPI 이동평균 산출 불가"))
    else:
        details.append(("⚪", "KOSPI 20일 데이터 부족"))

    # 2. 외국인 KOSPI 현물 (20점 만점)
    if foreign_cashflow is None:
        details.append(("⚪", "외국인 현물 수급 미확인 — 점수 제외"))
    else:
        try:
            cashflow = float(foreign_cashflow)
            if cashflow >= 3000:
                flow_score += 20
                details.append(("🟢", f"외국인 현물 강한 순매수 ({cashflow:+,.0f}억원) [+20점]"))
            elif cashflow >= 500:
                flow_score += 15
                details.append(("🟢", f"외국인 현물 순매수 ({cashflow:+,.0f}억원) [+15점]"))
            elif cashflow > 0:
                flow_score += 8
                details.append(("🟡", f"외국인 현물 소폭 순매수 ({cashflow:+,.0f}억원) [+8점]"))
            elif cashflow <= -3000:
                details.append(("🔴", f"외국인 현물 대규모 순매도 ({cashflow:+,.0f}억원) [+0점]"))
            else:
                details.append(("🟡", f"외국인 현물 매도/중립 ({cashflow:+,.0f}억원) [+0점]"))
        except (TypeError, ValueError):
            details.append(("⚪", "외국인 현물 수급 형식 오류 — 점수 제외"))

    # 3. 한국 시장 폭 (20점 만점)
    advancing = market_breadth.get("advancing") if isinstance(market_breadth, dict) else None
    declining = market_breadth.get("declining") if isinstance(market_breadth, dict) else None
    try:
        if advancing is not None and declining is not None and float(declining) > 0:
            adr = float(advancing) / float(declining)
            if adr >= 1.20:
                flow_score += 20
                details.append(("🟢", f"한국 시장 폭 확산 (ADR {adr:.2f}) [+20점]"))
            elif adr >= 0.80:
                flow_score += 10
                details.append(("🟡", f"한국 시장 폭 중립 (ADR {adr:.2f}) [+10점]"))
            else:
                details.append(("🔴", f"한국 시장 폭 취약 (ADR {adr:.2f}) [+0점]"))
        else:
            details.append(("⚪", "한국 시장 폭 미확인 — 점수 제외"))
    except (TypeError, ValueError, ZeroDivisionError):
        details.append(("⚪", "한국 시장 폭 산출 불가 — 점수 제외"))

    # 4. 외국인 선물 (15점 만점, 필수 게이트 아님)
    if foreign_futures is None:
        details.append(("⚪", "외국인 선물 미확인 — 점수 제외, 매수 차단 아님"))
    else:
        try:
            futures = float(foreign_futures)
            if futures >= 5000:
                flow_score += 15
                details.append(("🟢", f"외국인 선물 강한 순매수 ({futures:+,.0f}계약) [+15점]"))
            elif futures >= 2500:
                flow_score += 10
                details.append(("🟢", f"외국인 선물 순매수 ({futures:+,.0f}계약) [+10점]"))
            elif futures >= 1000:
                flow_score += 5
                details.append(("🟡", f"외국인 선물 소폭 순매수 ({futures:+,.0f}계약) [+5점]"))
            elif futures < 0:
                details.append(("🟡", f"외국인 선물 순매도 ({futures:+,.0f}계약) — 현물 헤지 가능성, 단독 차단 아님 [+0점]"))
            else:
                details.append(("⚪", "외국인 선물 중립 [+0점]"))
        except (TypeError, ValueError):
            details.append(("⚪", "외국인 선물 형식 오류 — 점수 제외"))

    # 5. 선물 가격과 미결제약정의 결합 해석 (10점 만점)
    oi_scores = {
        "가격 상승 + 미결제약정 증가 (신규 롱 가능성)": (10, "🟢", "가격 상승·미결제약정 증가 — 신규 롱 가능성 [+10점]"),
        "가격 상승 + 미결제약정 감소 (숏커버 가능성)": (5, "🟡", "가격 상승·미결제약정 감소 — 숏커버 가능성 [+5점]"),
        "가격 하락 + 미결제약정 증가 (신규 숏 가능성)": (0, "🔴", "가격 하락·미결제약정 증가 — 신규 숏 가능성 [+0점]"),
        "가격 하락 + 미결제약정 감소 (롱청산 가능성)": (0, "🔴", "가격 하락·미결제약정 감소 — 롱청산 가능성 [+0점]"),
    }
    oi_score, oi_icon, oi_message = oi_scores.get(
        oi_signal,
        (0, "⚪", "선물 가격·미결제약정 조합 미확인 — 점수 제외"),
    )
    flow_score += oi_score
    details.append((oi_icon, oi_message))

    # 6. RSP는 글로벌 온기 확인용 보조지표로만 사용한다. (5점 만점)
    if rsp_change_pct is None:
        details.append(("⚪", "RSP 데이터 미확인 — 점수 제외"))
    else:
        try:
            rsp_change = float(rsp_change_pct)
            if rsp_change >= 0:
                flow_score += 5
                details.append(("🟢", f"글로벌 위험선호 보조 확인 (RSP {rsp_change:+.2f}%) [+5점]"))
            elif rsp_change >= -0.5:
                flow_score += 3
                details.append(("🟡", f"글로벌 위험선호 약보합 (RSP {rsp_change:+.2f}%) [+3점]"))
            else:
                details.append(("🔴", f"글로벌 위험선호 약화 (RSP {rsp_change:+.2f}%) [+0점]"))
        except (TypeError, ValueError):
            details.append(("⚪", "RSP 데이터 형식 오류 — 점수 제외"))

    if flow_score >= 70:
        status = "🟢 자금흐름 강함 (추세 확대 확인)"
    elif flow_score >= 50:
        status = "🟡 자금흐름 확인 (조건부 GO 검토)"
    else:
        status = "🔴 자금흐름 미확인/약함 (추가 확인)"

    return flow_score, status, details


def evaluate_market_execution_quality(kospi_hist):
    """당일 봉의 체결 품질을 평가해 추세 신호와 주문 타이밍을 분리한다."""
    result = {
        "code": "DATA_UNAVAILABLE",
        "label": "⚪ 체결 품질 미확인",
        "reason": "당일 고가·저가·종가 데이터가 부족합니다. 신규 주문은 종가 확인 후 검토합니다.",
        "defer_new_order": True,
        "close_location": None,
        "high_to_close_pct": None,
    }
    if kospi_hist is None or kospi_hist.empty or len(kospi_hist) < 20:
        return result
    if not {"Close", "High", "Low"}.issubset(kospi_hist.columns):
        return result

    try:
        close = float(kospi_hist["Close"].iloc[-1])
        high = float(kospi_hist["High"].iloc[-1])
        low = float(kospi_hist["Low"].iloc[-1])
        ma5 = float(kospi_hist["Close"].rolling(5).mean().iloc[-1])
        ma20 = float(kospi_hist["Close"].rolling(20).mean().iloc[-1])
    except (TypeError, ValueError, KeyError, IndexError):
        return result

    day_range = high - low
    close_location = 0.5 if day_range <= 0 else (close - low) / day_range
    high_to_close_pct = 0.0 if high <= 0 else (high - close) / high * 100.0
    result["close_location"] = close_location
    result["high_to_close_pct"] = high_to_close_pct

    if high_to_close_pct >= 3.0 and close_location <= 0.25:
        result.update(
            {
                "code": "FAILED_BREAKOUT",
                "label": "🔴 돌파 실패 — 체결 유예",
                "reason": (
                    f"장중 고점 대비 종가가 {high_to_close_pct:.1f}% 밀렸고 종가는 당일 범위 하단 "
                    f"{close_location * 100:.0f}%에 위치했습니다. 추세 신호와 별개로 오늘 신규 주문은 유예합니다."
                ),
                "defer_new_order": True,
            }
        )
    elif close >= ma5 and close >= ma20 and close_location >= 0.50:
        result.update(
            {
                "code": "EXECUTABLE",
                "label": "🟢 종가 체결 가능",
                "reason": "종가가 5일선·20일선 위에서 당일 범위 중단 이상에 위치했습니다. 다음 거래일 분할 실행만 검토합니다.",
                "defer_new_order": False,
            }
        )
    else:
        result.update(
            {
                "code": "WAIT_CONFIRMATION",
                "label": "🟡 종가 추가 확인",
                "reason": "추세는 훼손되지 않았더라도 종가 체결 품질이 충분하지 않습니다. 다음 거래일 지지·안착을 확인합니다.",
                "defer_new_order": True,
            }
        )
    return result


def load_state_from_github(tracker_file):
    import os, json, base64
    import streamlit as st
    
    state = {"last_date": "", "warning_days": 0}
    token = None
    try:
        token = st.secrets.get("GITHUB_TOKEN")
    except Exception:
        pass
        
    if not token:
        if os.path.exists(tracker_file):
            try:
                with open(tracker_file, "r") as f:
                    return json.load(f)
            except:
                pass
        return state
        
    repo = "rentgist/my-quant-bot"
    url = f"https://api.github.com/repos/{repo}/contents/{tracker_file}"
    headers = {"Authorization": f"token {token}"}
    
    try:
        import requests
        r = requests.get(url, headers=headers, timeout=5)
        if r.status_code == 200:
            content = base64.b64decode(r.json()["content"]).decode("utf-8")
            state = json.loads(content)
            with open(tracker_file, "w") as f:
                json.dump(state, f)
            return state
    except Exception:
        pass
        
    if os.path.exists(tracker_file):
        try:
            with open(tracker_file, "r") as f:
                return json.load(f)
        except:
            pass
    return state

def save_state_to_github(tracker_file, state):
    import os, json, base64
    import streamlit as st
    
    with open(tracker_file, "w") as f:
        json.dump(state, f)
        
    token = None
    try:
        token = st.secrets.get("GITHUB_TOKEN")
    except Exception:
        pass
        
    if not token:
        return
        
    repo = "rentgist/my-quant-bot"
    url = f"https://api.github.com/repos/{repo}/contents/{tracker_file}"
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"}
    
    sha = None
    try:
        import requests
        r = requests.get(url, headers=headers, timeout=5)
        if r.status_code == 200:
            sha = r.json().get("sha")
    except:
        pass
        
    content_b64 = base64.b64encode(json.dumps(state, indent=4).encode("utf-8")).decode("utf-8")
    data = {
        "message": f"Update {tracker_file} by Bot",
        "content": content_b64,
        "branch": "main"
    }
    if sha:
        data["sha"] = sha
        
    try:
        import requests
        requests.put(url, headers=headers, json=data, timeout=5)
    except:
        pass


def calculate_regime_classification(
    macro_score,
    flow_score,
    kospi_above_ma20,
    warning_days_override=None,
    save_state=False,
    execution_quality=None,
):
    import datetime
    tracker_file = "regime_state.json"
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    
    state = load_state_from_github(tracker_file)
            
    # GO는 합산 점수만으로 확정하지 않는다.
    # 환율 안정만으로 macro_score 50점이 만들어질 수 있으므로,
    # KOSPI의 실제 20일선 탈환을 별도 필수 게이트로 확인한다.
    go_ready = macro_score >= 50 and flow_score >= 50 and kospi_above_ma20
    is_warning = flow_score >= 50 and not go_ready
    execution_deferred = bool(
        isinstance(execution_quality, dict)
        and execution_quality.get("defer_new_order", False)
    )
    execution_reason = (
        execution_quality.get("reason", "당일 체결 품질을 추가 확인합니다.")
        if isinstance(execution_quality, dict)
        else ""
    )
    warning_days = state.get("warning_days", 0)
    last_date = state.get("last_date")
    
    if is_warning:
        if last_date != today_str:
            warning_days += 1
            state["warning_days"] = warning_days
            state["last_date"] = today_str
            if save_state:
                save_state_to_github(tracker_file, state)
    else:
        if warning_days != 0 or last_date != today_str:
            state["warning_days"] = 0
            state["last_date"] = today_str
            if save_state:
                save_state_to_github(tracker_file, state)
        warning_days = 0
        
    warning_days = warning_days_override if warning_days_override is not None else max(1, min(5, warning_days)) if is_warning else 0
    
    if macro_score >= 80 and flow_score >= 70 and kospi_above_ma20:
        if execution_deferred:
            regime = "🟠 강력 GO — 체결 유예"
            action = f"추세 확대 조건은 충족했지만 {execution_reason} 다음 거래일 종가 확인 후에만 총자산 5%p 이내로 분할 실행합니다."
            color = "#ff9900"
        else:
            regime = "🟢 강력 GO (정배열)"
            action = "추세 확인 완료. 목표비중까지 분할 확대하되 한 번에 총자산 5%p를 넘기지 않습니다."
            color = "#21c354"
    elif go_ready:
        if execution_deferred:
            regime = "🟠 조건부 GO — 체결 유예"
            action = f"20일선 탈환과 수급 조건은 유지됩니다. 다만 {execution_reason} 오늘 신규 주문은 동결하고 다음 거래일에 총자산 5%p 이내로만 재검토합니다."
            color = "#ff9900"
        else:
            regime = "🟡 조건부 GO (추세 전환)"
            action = "20일선 탈환 완료. 본대 자금 분할 진입을 시작하되 한 번에 총자산 5%p를 넘기지 않습니다."
            color = "#fcca46"
    elif is_warning:
        if warning_days >= 3:
            regime = "✅ 경고 국면 확정 (3거래일 지지 성공)"
            if kospi_above_ma20:
                action = "20일선은 회복했지만 매크로 점수가 부족합니다. '선발대(10~20%)'만 진입 검토."
            else:
                action = "수급 지지는 확인됐지만 20일선 미탈환 상태입니다. 본대 투입 없이 선발대 진입만 검토."
            color = "#ff9900"
        else:
            regime = f"⚠️ 경고 국면 (바닥 탈출 시도 - {warning_days}/3일 관찰 중)"
            if kospi_above_ma20:
                action = f"20일선은 회복했지만 매크로 확인이 부족합니다. 관찰 지속 (남은 기간: {3-warning_days}거래일)."
            else:
                action = f"수급은 포착됐지만 20일선 미탈환 상태입니다. 관찰 지속 (남은 기간: {3-warning_days}거래일)."
            color = "#ff9900"
    else:
        regime = "🔴 PASS (매수 보류)"
        action = "매크로 위험 및 자금흐름 약세 지속. 칼날 잡기 금지. 현금 사수."
        color = "#ff4b4b"
        
    return regime, action, color


# ═════════════════════════════════════════
# 🎯 레이어 4: 종합 전략 제언 엔진
# 위험 탐지기(danger) × 바닥 탐지기(score) × 반등 신뢰도(recovery)를
# 교차 결합해 '지금 매수해도 되는가'를 실전 액션으로 번역한다.
# 포지션 비율은 11원칙(위기 줍줍·분할 매수) 철학 기준.
# ═════════════════════════════════════════
def get_strategic_advice(danger_count, bottom_score, bottom_verdict, regime="", recovery_score=None):
    """
    반환: (headline, color, actions[])
    ORION v28.1 — 상황 → 체크리스트 → 타점 안내를 한 흐름으로 전달
    """
    actions = []
    is_knife = "칼날" in bottom_verdict
    is_top   = "고점" in bottom_verdict

    # 1순위: 떨어지는 칼날 (매수 보류)
    if is_knife:
        headline = "🔴 ORION Signal : STOP — 지금은 기다릴 때입니다."
        color = "#ff9900"
        actions = [
            "급락 진행 중입니다. 속도가 문제인 구간에서는 진입하지 않습니다.",
            "5일선 회복이 확인되면 아래 체크리스트를 다시 점검하세요.",
            "기존 포지션은 홀딩합니다. 추가 자금 투입은 보류합니다.",
        ]

    # 2순위: 고점권 (바닥 점수 무의미)
    elif is_top:
        if danger_count >= 5:
            headline = "🔴 ORION Signal : STOP — 지금은 매수보다 현금을 지킬 때입니다."
            color = "#ff4b4b"
            actions = [
                "위험 경보가 다수 감지되었으나 낙폭은 아직 적습니다. 빠질 공간이 남아 있습니다.",
                "신규 매수를 중단하고, 반등이 나오면 비중 축소 기회로 활용하세요.",
            ]
        elif danger_count >= 3:
            headline = "🟡 ORION Signal : WAIT — 이상 징후가 감지되었습니다."
            color = "#ff9900"
            actions = [
                "고점권에서 위험 신호가 포착되었습니다. 추격 매수의 기댓값이 가장 낮은 구간입니다.",
                "수익 중인 종목 일부 익절로 현금을 확보하세요.",
            ]
        else:
            headline = "🟢 ORION Signal : CLEAR — 안정적인 흐름입니다."
            color = "#21c354"
            actions = [
                "시장에 이상 신호 없는 안정 구간입니다.",
                "정해진 원칙에 따라 기계적 분할 매수를 유지하세요.",
                "종목 레이더에서 눌림목 타점을 확인하고, 조건이 맞으면 진입하세요.",
            ]

    # 3순위: 극단 패닉 (바닥 점수 80+) -> 기회 탐지
    elif bottom_score >= 80:
        headline = "🟠 ORION Signal : ALERT — 역사적 바닥권이 감지되었습니다."
        color = "#e94560"
        actions = [
            "바닥 탐지 점수가 80점을 넘었습니다. 역사적으로 드문 기회 영역입니다.",
            "아직 추세 반전이 확인되지 않았습니다. 아래 체크리스트에서 조건을 점검한 뒤, GO 사인이 뜨면 진입하세요.",
            "종목 레이더의 매수 타점을 확인하고, 검증된 우량주만 대상으로 하세요.",
            "ORION은 바닥을 감지합니다. 진입 여부는 체크리스트가, 타점은 레이더가 결정합니다.",
        ]
        
    # 4순위: 추세 전환 및 분할 매수 (바닥 점수 50~79) -> Tier 2
    # recovery_score: 100=Breadth+Credit 둘 다 회복, 50=하나만 회복, 25=부분, 0=미회복
    elif bottom_score >= 50:
        gates_ok = (recovery_score is not None and recovery_score >= 30)  # 기준 완화: 50→30
        if gates_ok:
            headline = "🟡 ORION Signal : GO — 추세 전환이 확인되었습니다."
            color = "#fcca46"
            actions = [
                "바닥 점수와 반등 신뢰도가 충족되었습니다.",
                "아래 체크리스트에서 최종 GO 사인을 확인한 뒤, 종목 레이더에서 타점을 잡고 분할 진입하세요.",
                "오후 종가 부근에 집행하여 리스크를 최소화하세요.",
            ]
        else:
            headline = "🟡 ORION Signal : WAIT — 바닥 확인 중이나, 아직 때가 아닙니다."
            color = "#fcca46"
            actions = [
                "바닥 점수는 충분하지만, Breadth(RSP) 또는 Credit(HYG) 회복 신호가 아직 미흡합니다.",
                "수급 전환, 5일선 돌파, 환율 안정 중 하나 이상이 확인될 때 진입 검토하세요.",
                "기회는 많습니다. 확률이 높을 때만 움직입니다.",
            ]

    # 5순위: 애매한 하락 (35~49)
    elif bottom_score >= 35:
        headline = "⚪ ORION Signal : HOLD — 관망이 최선입니다."
        color = "#aaaaaa"
        actions = [
            "단기 조정이 나왔지만, 바닥이라 부르기엔 아직 이릅니다.",
            "어설픈 물타기 구간입니다. 기존 포지션만 유지하세요.",
        ]

    # 6순위: 평범 (그 외) -> Tier 1
    else:
        headline = "🟢 ORION Signal : CLEAR — 평이한 시장입니다."
        color = "#21c354"
        actions = [
            "큰 패닉이나 과열이 없는 일상적인 시장입니다.",
            "종목 레이더에서 눌림목 타점을 확인하고, 원칙에 따라 기계적으로 매수하세요.",
        ]

    return headline, color, actions



def run_historical_backtest(spy_hist, vix_hist, vix3m_hist):
    if any(df.empty for df in [spy_hist, vix_hist, vix3m_hist]):
        return None

    df = pd.concat([
        spy_hist['Close'], vix_hist['Close'], vix3m_hist['Close'],
    ], axis=1).ffill().dropna()

    if df.empty or len(df) < 400:
        return None

    df.columns = ['SPY', 'VIX', 'VIX3M']

    # 고점 기준선: min_periods=252 → 데이터 초기 1년은 '가짜 저낙폭' 왜곡이 생기므로 제외
    df['SPY_High_252'] = df['SPY'].rolling(252, min_periods=252).max()
    df['Drawdown']     = (df['SPY'] / df['SPY_High_252'] - 1) * 100
    df['RSI']          = get_rolling_rsi(df['SPY'], 14)
    df = df.dropna(subset=['Drawdown', 'RSI'])
    if df.empty:
        return None

    df['Fwd_3M_Ret'] = (df['SPY'].shift(-63)  / df['SPY'] - 1) * 100
    df['Fwd_6M_Ret'] = (df['SPY'].shift(-126) / df['SPY'] - 1) * 100

    # ① 코어 점수 — 실시간과 같은 _score_bottom (CNN은 과거 데이터 없어 제외, 만점 정규화로 스케일 동일)
    df['Score'] = [
        _score_bottom(dd, rsi, vix)
        for dd, rsi, vix in zip(df['Drawdown'], df['RSI'], df['VIX'])
    ]

    # ② 구조 보너스 — 실시간의 _apply_structure_bonus를 벡터화한 동일 조건
    close = df['SPY']
    rets  = close.pct_change()
    ma20  = close.rolling(20).mean()
    ma50  = close.rolling(50).mean()
    ma50_slope = (ma50 / ma50.shift(21) - 1) * 100
    down_ratio = (rets < 0).rolling(20).mean()
    p1 = close.shift(30).rolling(30).min()
    p2 = close.rolling(30).min()
    r1 = df['RSI'].shift(30).rolling(30).min()
    r2 = df['RSI'].rolling(30).min()

    bonus = np.zeros(len(df))
    bonus += np.where((df['Drawdown'] <= -10) & (down_ratio >= GRIND_DOWN_RATIO) & (ma50_slope < 0), 8, 0)
    bonus += np.where((p2 < p1) & (r2 > r1 + DIV_RSI_MARGIN), 10, 0)
    bonus += np.where((p2 > p1 * 1.005) & (df['Drawdown'] <= -8), 5, 0)
    bonus += np.where((close > ma20) & (df['Drawdown'] <= -10), 5, 0)
    df['Score'] = np.minimum(df['Score'] + bonus, 100).astype(int)

    # ③ 떨어지는 칼날 패널티 — 실시간과 동일 임계값
    ret_1d  = rets * 100
    ma5     = close.rolling(5).mean()
    gap_ma5 = (close / ma5 - 1) * 100
    knife   = (ret_1d <= KNIFE_1D_RET) | (gap_ma5 <= KNIFE_MA5_GAP)
    df['Score'] = np.where(knife & (df['Score'] >= 35), df['Score'] - KNIFE_PENALTY, df['Score'])
    df['Score'] = df['Score'].clip(0, 100).astype(int)

    res_70 = df[df['Score'] >= 70].dropna(subset=['Fwd_3M_Ret'])
    res_50 = df[(df['Score'] >= 50) & (df['Score'] < 70)].dropna(subset=['Fwd_3M_Ret'])

    def _stat(sub):
        if len(sub) == 0:
            return {"발생 횟수": 0, "평균 3M 수익률": 0, "평균 6M 수익률": 0, "승률 3M": 0}
        return {
            "발생 횟수":    len(sub),
            "평균 3M 수익률": round(sub['Fwd_3M_Ret'].mean(), 2),
            "평균 6M 수익률": round(sub['Fwd_6M_Ret'].dropna().mean(), 2) if len(sub['Fwd_6M_Ret'].dropna()) > 0 else 0,
            "승률 3M":       round((sub['Fwd_3M_Ret'] > 0).mean() * 100, 1),
        }

    event_dates = {
        "코로나 바닥": "2020-03-23",
        "2022 약세장 바닥": "2022-10-13",
        "2018 12월 조정": "2018-12-24",
    }
    event_scores = {}
    for name, d in event_dates.items():
        try:
            dt = pd.Timestamp(d)
            closest = df.index[df.index.get_indexer([dt], method='nearest')[0]]
            if abs((closest - dt).days) <= 5:
                event_scores[name] = int(df.loc[closest, 'Score'])
            else:
                event_scores[name] = "데이터 외 구간"
        except Exception:
            event_scores[name] = None

    return {
        "70점 이상 (강력 매수)":    _stat(res_70),
        "50~69점 (분할 매수)":      _stat(res_50),
        "주요 이벤트 점수":          event_scores,
        "score_series":             df[['Score', 'Drawdown']],
    }


def run_kr_historical_backtest(kospi_hist, vkospi_hist, usdkrw_hist):
    if any(df is None for df in [kospi_hist, vkospi_hist, usdkrw_hist]) or any(df.empty for df in [kospi_hist, vkospi_hist, usdkrw_hist]):
        return None

    df = pd.concat([
        kospi_hist['Close'], vkospi_hist['Close'], usdkrw_hist['Close'],
    ], axis=1).ffill().dropna()

    if df.empty or len(df) < 400:
        return None

    df.columns = ['KOSPI', 'VKOSPI', 'USDKRW']

    # Drawdown (max 35)
    df['KOSPI_High_252'] = df['KOSPI'].rolling(252, min_periods=252).max()
    df['Drawdown']     = (df['KOSPI'] / df['KOSPI_High_252'] - 1) * 100
    df['RSI']          = get_rolling_rsi(df['KOSPI'], 14)
    df['USDKRW_RSI']   = get_rolling_rsi(df['USDKRW'], 14)
    
    df = df.dropna(subset=['Drawdown', 'RSI', 'USDKRW_RSI'])
    if df.empty:
        return None

    df['Fwd_3M_Ret'] = (df['KOSPI'].shift(-63)  / df['KOSPI'] - 1) * 100
    df['Fwd_6M_Ret'] = (df['KOSPI'].shift(-126) / df['KOSPI'] - 1) * 100

    dd = -df['Drawdown']
    kr_rsi = df['RSI']
    vkospi = df['VKOSPI']
    krw_rsi = df['USDKRW_RSI']

    # Vectorized score calculation (equivalent to calculate_kr_bottom_finder)
    s_dd = np.where(dd >= 20, 35,
             np.where(dd >= 12, 22 + (dd - 12) * (35 - 22) / (20 - 12),
               np.where(dd >= 7, 10 + (dd - 7) * (22 - 10) / (12 - 7),
                 np.where(dd > 0, dd * 10 / 7, 0))))
                 
    s_rsi = np.where(kr_rsi <= 30, 20,
              np.where(kr_rsi <= 40, 12 + (40 - kr_rsi) * (20 - 12) / (40 - 30),
                np.where(kr_rsi <= 45, 5 + (45 - kr_rsi) * (12 - 5) / (45 - 40),
                  np.where(kr_rsi <= 60, (60 - kr_rsi) * 5 / (60 - 45), 0))))
                  
    s_vkospi = np.where(vkospi >= 25, 25,
                 np.where(vkospi >= 20, 15 + (vkospi - 20) * (25 - 15) / (25 - 20),
                   np.where(vkospi >= 16, 5 + (vkospi - 16) * (15 - 5) / (20 - 16),
                     np.where(vkospi >= 12, (vkospi - 12) * 5 / (16 - 12), 0))))
                     
    s_krw = np.where(krw_rsi <= 55, 20,
              np.where(krw_rsi <= 65, 10 + (65 - krw_rsi) * (20 - 10) / (65 - 55),
                np.where(krw_rsi <= 75, (75 - krw_rsi) * 10 / (75 - 65), 0)))
                
    kill_switch = (krw_rsi > 70) & (df['Drawdown'] > -10)
    
    max_score = 100 # Assuming all data available
    score = (s_dd + s_rsi + s_vkospi + s_krw)
    score = np.round(score / max_score * 100).clip(0, 100)
    
    # Structure Bonus
    close = df['KOSPI']
    rets  = close.pct_change()
    ma20  = close.rolling(20).mean()
    ma50  = close.rolling(50).mean()
    ma50_slope = (ma50 / ma50.shift(21) - 1) * 100
    down_ratio = (rets < 0).rolling(20).mean()
    p1 = close.shift(30).rolling(30).min()
    p2 = close.rolling(30).min()
    r1 = df['RSI'].shift(30).rolling(30).min()
    r2 = df['RSI'].rolling(30).min()

    bonus = np.zeros(len(df))
    bonus += np.where((df['Drawdown'] <= -10) & (down_ratio >= GRIND_DOWN_RATIO) & (ma50_slope < 0), 8, 0)
    bonus += np.where((p2 < p1) & (r2 > r1 + DIV_RSI_MARGIN), 10, 0)
    bonus += np.where((p2 > p1 * 1.005) & (df['Drawdown'] <= -8), 5, 0)
    bonus += np.where((close > ma20) & (df['Drawdown'] <= -10), 5, 0)
    
    score = np.minimum(score + bonus, 100)
    score = np.where(kill_switch, np.minimum(score, 30), score)
    
    # Knife penalty
    ret_1d  = rets * 100
    ma5     = close.rolling(5).mean()
    gap_ma5 = (close / ma5 - 1) * 100
    knife   = (ret_1d <= KNIFE_1D_RET) | (gap_ma5 <= KNIFE_MA5_GAP)
    score = np.where(knife & (score >= 35), score - KNIFE_PENALTY, score)
    df['Score'] = score.clip(0, 100).astype(int)

    res_70 = df[df['Score'] >= 70].dropna(subset=['Fwd_3M_Ret'])
    res_50 = df[(df['Score'] >= 50) & (df['Score'] < 70)].dropna(subset=['Fwd_3M_Ret'])

    def _stat(sub):
        if len(sub) == 0:
            return {"발생 횟수": 0, "평균 3M 수익률": 0, "평균 6M 수익률": 0, "승률 3M": 0}
        return {
            "발생 횟수":    len(sub),
            "평균 3M 수익률": round(sub['Fwd_3M_Ret'].mean(), 2),
            "평균 6M 수익률": round(sub['Fwd_6M_Ret'].dropna().mean(), 2) if len(sub['Fwd_6M_Ret'].dropna()) > 0 else 0,
            "승률 3M":       round((sub['Fwd_3M_Ret'] > 0).mean() * 100, 1),
        }

    event_dates = {
        "코로나 바닥": "2020-03-19",
        "2022 약세장 바닥": "2022-09-30",
        "2018 10월 폭락": "2018-10-29",
    }
    event_scores = {}
    for name, d in event_dates.items():
        try:
            dt = pd.Timestamp(d)
            closest = df.index[df.index.get_indexer([dt], method='nearest')[0]]
            if abs((closest - dt).days) <= 5:
                event_scores[name] = int(df.loc[closest, 'Score'])
            else:
                event_scores[name] = "데이터 외 구간"
        except Exception:
            event_scores[name] = None

    return {
        "70점 이상 (강력 매수)":    _stat(res_70),
        "50~69점 (분할 매수)":      _stat(res_50),
        "주요 이벤트 점수":          event_scores,
        "score_series":             df[['Score', 'Drawdown']],
    }


# ═════════════════════════════════════════
# 종목 해석 / 라벨링 유틸
# ═════════════════════════════════════════
def get_cashflow_interpretation(d):
    gm = d.get('Gross_Margin')
    roic = d.get('ROIC')
    fcf_y = d.get('FCF_Yield')
    buybacks = d.get('Buybacks')

    texts = []
    if gm is not None:
        if gm >= 0.50: texts.append(f"✅ 압도적 마진율로 독점적 지위 증명 (매출총이익률 {gm*100:.1f}%)")
        elif gm <= 0.20: texts.append(f"⚠️ 원가 부담이 큰 박리다매 구조 (매출총이익률 {gm*100:.1f}%)")

    if roic is not None:
        if roic >= 0.10: texts.append(f"✅ 훌륭한 자본 배치로 돈이 돈을 버는 구조 (ROIC {roic*100:.1f}%)")
        elif roic < 0.05 and roic > 0: texts.append(f"⚠️ 투하자본 대비 실제 수익성은 다소 낮음 (ROIC {roic*100:.1f}%)")
        elif roic < 0: texts.append("🚨 투하자본 대비 적자 발생")

    if fcf_y is not None:
        if fcf_y >= 0.05: texts.append(f"✅ 현금 창출력 대비 주가가 싼 매력적인 구간 (FCF Yield {fcf_y*100:.1f}%)")
        elif fcf_y <= 0.02 and fcf_y > 0: texts.append("💡 현금 대비 주가에 프리미엄(기대감)이 반영된 성장주")
        elif fcf_y < 0: texts.append("🚨 잉여현금흐름 마이너스 (보유 현금 소진 중)")

    if buybacks is not None and buybacks != 0:
        texts.append("✅ 자사주 매입을 통한 주가 방어 및 주주환원 적극 진행 중")

    if not texts: return "해당 지표의 데이터가 충분하지 않아 해석이 보류되었습니다."
    return " / ".join(texts)


def relative_strength_label(my_rsi, spy_rsi):
    if my_rsi is None or spy_rsi is None:
        return "N/A"
    gap = my_rsi - spy_rsi
    if my_rsi > 65 and spy_rsi > 65:
        return f"🔵 동반 과매수 (시장 전체 과열, 차이 {gap:+.0f})"
    if my_rsi < 35 and spy_rsi < 35:
        return f"🟠 동반 과매도 (시장 전체 하락, 차이 {gap:+.0f})"
    if gap >= 10:  return f"💪 강한 주도주 (SPY 대비 +{gap:.0f})"
    if gap >= 5:   return f"📈 주도주 (SPY 대비 +{gap:.0f})"
    if gap <= -10: return f"📉 강한 소외주 (SPY 대비 {gap:.0f})"
    if gap <= -5:  return f"⚠️ 소외주 (SPY 대비 {gap:.0f})"
    return f"⚖️ 시장 동기화 (차이 {gap:+.0f})"


def short_interest_label(short_val):
    if short_val is None: return "N/A"
    s_pct = short_val * 100
    if s_pct >= 20:   tag = "🔴 매우 높음"
    elif s_pct >= 10: tag = "🟠 높음"
    elif s_pct >= 5:  tag = "🟡 보통"
    else:             tag = "✅ 낮음"
    return f"{s_pct:.1f}% ({tag})"


def get_comprehensive_risk_grade(short_val, beta_val):
    if short_val is None or beta_val is None: return "N/A"
    s_pct = short_val * 100
    is_high_short = s_pct >= 5.0
    is_high_beta = beta_val >= 1.2

    if not is_high_short and not is_high_beta: return "🟢 안정형 — 방어적 투자에 적합"
    elif not is_high_short and is_high_beta: return "🟡 모멘텀형 — 상승장에 강하지만 하락 시 크게 빠짐"
    elif is_high_short and not is_high_beta: return "🟠 논란형 — 시장은 의심하지만 변동성은 낮음, 이유 확인 필요"
    else: return "🔴 고위험 — 하락 베팅 + 큰 변동성, 진입 신중"


TITLE_MAP = {
    "ceo": "CEO (최고경영자)", "chief executive": "CEO (최고경영자)",
    "president": "President (대표)", "cfo": "CFO (최고재무책임자)",
    "chief financial": "CFO (최고재무책임자)", "coo": "COO (최고운영책임자)",
    "chief operating": "COO (최고운영책임자)", "cto": "CTO (최고기술책임자)",
    "chief technology": "CTO (최고기술책임자)", "cso": "CSO (최고전략책임자)",
    "chief strategy": "CSO (최고전략책임자)", "cmo": "CMO (최고마케팅책임자)",
    "chief marketing": "CMO (최고마케팅책임자)", "cpo": "CPO (최고상품책임자)",
    "chief product": "CPO (최고상품책임자)", "executive vice president": "EVP (수석부사장)",
    "evp": "EVP (수석부사장)", "senior vice president": "SVP (선임부사장)",
    "svp": "SVP (선임부사장)", "vice president": "VP (부사장)",
    "general counsel": "GC (법무총괄)", "director": "이사 (Director)",
    "chairman": "이사회 의장 (Chairman)", "board": "이사회 멤버",
    "10%": "10% 이상 주요주주", "beneficial": "수익적 소유자",
}


def normalize_title(raw_title: str) -> str:
    if not raw_title: return "직함 미상"
    lower = raw_title.lower().strip()
    for key, label in TITLE_MAP.items():
        if key in lower: return label
    return raw_title.strip()


def analyze_macro_flow(macro_data, flow_data, extra_data=None):
    """
    수집된 매크로 지표(금리, 유가, 환율)와 수급(외국인 등)을 교차 분석하여 국면(Phase) 확정.
    extra_data: {cnn_score, cnn_rating, us_score, us_phase, kr_score, kr_phase} (optional)
    """
    tnx_df = macro_data.get('tnx_10y', None)
    wti_df = macro_data.get('wti_10y', None)
    usdkrw_df = macro_data.get('usdkrw_10y', None)
    vix_df = macro_data.get('vix_10y', None)
    spy_df = macro_data.get('spy_10y', None)
    kospi_df = macro_data.get('kospi_10y', None)
    
    # 최근 2거래일 데이터 추출 헬퍼
    def _extract(df):
        if df is not None and not df.empty:
            clean = df['Close'].dropna()
            if len(clean) >= 2:
                return float(clean.iloc[-1]), float(clean.iloc[-1] - clean.iloc[-2])
        return 0.0, 0.0
    
    tnx_current, tnx_change = _extract(tnx_df)
    wti_current, wti_change = _extract(wti_df)
    usdkrw_current, usdkrw_change = _extract(usdkrw_df)
    vix_current, vix_change = _extract(vix_df)
    spy_current, spy_change = _extract(spy_df)
    kospi_current, kospi_change = _extract(kospi_df)
    
    # S&P 500 / KOSPI 등락률
    spy_pct = (spy_change / (spy_current - spy_change) * 100) if (spy_current - spy_change) != 0 else 0
    kospi_pct = (kospi_change / (kospi_current - kospi_change) * 100) if (kospi_current - kospi_change) != 0 else 0
        
    foreigner, institutional, retail = flow_data
    
    # 수급 데이터 유효성 체크 (KRX 서버 점검 시 모두 0)
    flow_valid = not (foreigner == 0 and institutional == 0 and retail == 0)
    
    # 시나리오 기계적 판별
    if flow_valid:
        if usdkrw_change < 0 and tnx_change < 0 and foreigner > 0:
            phase = "🟢 리스크 온 (강한 외국인 자금 유입)"
        elif usdkrw_change > 0 and tnx_change > 0 and foreigner < 0:
            phase = "🔴 리스크 오프 (안전자산 선호 및 외국인 이탈)"
        elif foreigner > 0:
            phase = "🟡 개별 종목 장세 (매크로 혼조 속 외국인 매수)"
        elif foreigner < 0:
            phase = "🟡 조정 장세 (외국인 차익 실현 및 매도 우위)"
        else:
            phase = "⚪ 방향성 탐색 (눈치 보기 장세)"
    else:
        phase = "⚪ 방향성 탐색 (눈치 보기 장세)"
    
    # 수급 라벨: 양수→순매수, 음수→순매도
    def _flow_label(val):
        if not flow_valid:
            return "⚠️ 점검 중"
        if val >= 0:
            return f"+{val:,}억원"
        else:
            return f"{val:,}억원"
    
    # extra_data에서 추가 지표 추출
    ed = extra_data or {}
    cnn_score = ed.get('cnn_score')
    cnn_rating = ed.get('cnn_rating', 'N/A')
    flow_1m = ed.get('flow_1m', (0, 0, 0))
    f_1m, i_1m, r_1m = flow_1m
    
    # 1개월 수급 유효성 체크
    flow_1m_valid = not (f_1m == 0 and i_1m == 0 and r_1m == 0)
    
    def _flow_label_1m(val):
        if not flow_1m_valid:
            return "⚠️ 점검 중"
        if val >= 0:
            return f"+{val:,}억원"
        else:
            return f"{val:,}억원"
        
    summary_dict = {
        "TNX_10Y": f"{tnx_current:.3f}% (전일대비 {tnx_change:+.3f}%p)",
        "WTI_Crude": f"${wti_current:.2f} (전일대비 {wti_change:+.2f}$)",
        "USD_KRW": f"{usdkrw_current:.1f}원 (전일대비 {usdkrw_change:+.1f}원)",
        "Foreigner": _flow_label(foreigner),
        "Institutional": _flow_label(institutional),
        "Retail": _flow_label(retail),
        "Foreigner_raw": foreigner,
        "Institutional_raw": institutional,
        "Retail_raw": retail,
        "flow_valid": flow_valid,
        
        "Foreigner_1m": _flow_label_1m(f_1m),
        "Institutional_1m": _flow_label_1m(i_1m),
        "Retail_1m": _flow_label_1m(r_1m),
        "flow_1m_valid": flow_1m_valid,
        
        # 추가 지표
        "VIX": f"{vix_current:.2f} (전일대비 {vix_change:+.2f})",
        "SPY": f"${spy_current:,.2f} ({spy_pct:+.2f}%)",
        "KOSPI": f"{kospi_current:,.2f} ({kospi_pct:+.2f}%)",
        "CNN_FG": f"{cnn_score}/100 ({cnn_rating})" if cnn_score is not None else "N/A",
    }
    
    return phase, summary_dict

@st.cache_data(ttl=3600)
def generate_economic_commentary(summary_dict, phase):
    """
    코드가 판정한 데이터와 국면을 Gemini API에 던져 자연어 해설 생성.
    """
    import os
    
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return "⚠️ 환경 변수에 GEMINI_API_KEY가 설정되지 않아 AI 브리핑을 제공할 수 없습니다."
    
    # 수급 데이터 유효성에 따라 프롬프트 분기
    flow_valid = summary_dict.get('flow_valid', True)
    flow_1m_valid = summary_dict.get('flow_1m_valid', True)
    
    if flow_valid or flow_1m_valid:
        flow_section = f"""[코스피 투자자별 수급 (양수=순매수, 음수=순매도)]
    (1) 오늘(당일) 수급
    - 외국인: {summary_dict['Foreigner']}
    - 기관합계: {summary_dict['Institutional']}
    - 개인: {summary_dict['Retail']}
    
    (2) 최근 1개월(30일) 누적 수급
    - 외국인: {summary_dict.get('Foreigner_1m', 'N/A')}
    - 기관합계: {summary_dict.get('Institutional_1m', 'N/A')}
    - 개인: {summary_dict.get('Retail_1m', 'N/A')}"""
        flow_instruction = "당일의 단기적 수급과 1개월의 중기적 누적 수급 트렌드를 비교하여 굵직한 돈의 흐름을 분석해라."
    else:
        flow_section = "[코스피 투자자별 수급]\n    - ⚠️ KRX 서버 점검 중으로 당일 및 1개월 수급 데이터 미수신 (0원 표시는 실제 거래량이 아님)"
        flow_instruction = "수급 데이터가 점검 중이므로 투자자 매매 관련 해설은 생략하고, 매크로 지표 해설에 집중해라."
    
    prompt = f"""너는 최고재무책임자(CFO)이자 전술적 자산배분 전문가다.
아래 전달받은 데이터(수치)와 시스템이 판정한 시장 국면을 바탕으로 가장 날카롭고 입체적인 브리핑을 작성하라.
단순히 숫자를 나열하지 말고, [거시 지표(금리/유가/환율)의 구조적 변화 ➔ 증시 반영 여부 ➔ 수급 다이버전스(괴리) 포착 ➔ 유리한 섹터/테마 암시 ➔ 최종 행동 강령] 순으로 인과관계에 맞게 해설해라.

[글로벌 매크로 지표]
    - 미국 10년물 국채 금리: {summary_dict['TNX_10Y']}
    - WTI 원유: {summary_dict['WTI_Crude']}
    - 원/달러 환율: {summary_dict['USD_KRW']}
    - VIX 공포지수: {summary_dict.get('VIX', 'N/A')}
    - CNN Fear & Greed 지수: {summary_dict.get('CNN_FG', 'N/A')}

[주요 지수]
    - S&P 500: {summary_dict.get('SPY', 'N/A')}
    - KOSPI: {summary_dict.get('KOSPI', 'N/A')}

{flow_section}

[시스템이 판정한 현재 시장 국면]
    - {phase}

[입체적 분석 및 작성 규칙]
1. {flow_instruction}
2. 다이버전스 포착: 만약 지수는 하락/조정 중인데 외국인/기관 수급이 대량 유입된다면 '은밀한 매집'으로, 반대의 경우 '차익 실현(탈출)'으로 해석하는 입체적 분석을 포함해라.
3. 섹터 전략 암시: 현재 매크로 및 수급 국면에서 롱(비중 확대) 포지션이 유리한 테마(예: 방어주, 가치주, 수출주 등)와 숏(관망/비중 축소) 포지션이 필요한 리스크를 대비시켜라.
4. 5~6문장으로 짜임새 있게 작성해라.
5. 마지막 문장은 반드시 "따라서 현재 구간에서는 ~전략이 유리합니다." 형태로 행동 강령을 제시해라.
6. 불필요한 인사말은 제외하고 전문적인 톤을 유지해라.
"""
    
    # 방법 1: 새 SDK (google-genai)
    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        
        models_to_try = [
            "gemini-2.5-pro",          # 1순위: 2.5 Pro (최상급 브레인)
            "gemini-3.5-flash",        # 2순위: 3.5 Flash (강력한 신형 Flash)
            "gemini-3.1-flash-lite",   # 3순위: 3.1 Flash Lite (확인된 안정 모델)
            "gemini-1.5-flash-lite",   # 4순위: 2.5 Flash Lite
            "gemini-pro-latest",
            "gemini-flash-latest"
        ]
        
        response = None
        successful_model = None
        for model_name in models_to_try:
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                )
                successful_model = model_name
                break
            except:
                continue
                
        if response:
            return f"*(사용된 CFO AI 모델: {successful_model})*\n\n" + response.text.strip()
        else:
            raise Exception("모든 신규 SDK 모델 호출 실패")
    except Exception as e1:
        print(f"[google-genai 시도 실패]: {e1}")
    
    # 방법 2: 구 SDK (google-generativeai) 폴백
    try:
        import google.generativeai as genai_old
        genai_old.configure(api_key=api_key)
        
        response = None
        successful_model = None
        for old_model in ["gemini-2.5-pro", "gemini-3.5-flash", "gemini-3.1-flash-lite", "gemini-1.5-flash-lite", "gemini-flash-latest", "gemini-pro-latest"]:
            try:
                model = genai_old.GenerativeModel(old_model)
                safety_settings = [
                    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
                ]
                response = model.generate_content(prompt, safety_settings=safety_settings)
                if response and response.text:
                    successful_model = old_model
                    break
            except:
                continue
        if response and response.text:
            return f"*(사용된 CFO AI 모델: {successful_model} - 구형)*\n\n" + response.text.strip()
        else:
            raise Exception("모든 구형 SDK 모델 호출 실패")
        return response.text.strip()
    except Exception as e2:
        import traceback
        err_msg = traceback.format_exc()
        print(f"[google-generativeai 시도 실패]:\n{err_msg}")
        
        error_text = str(e2)
        if "429" in error_text or "Quota exceeded" in error_text:
            return (
                "⚠️ **Gemini API 일일/분당 무료 제공량(Quota)을 초과했습니다.**\n\n"
                "Google AI Studio의 무료 버전(Free Tier) API 키는 호출 횟수(RPM) 제한이 매우 낮습니다. "
                "스트림릿 화면을 새로고침하거나 UI를 조작할 때마다 API가 호출되어 한도에 금방 도달할 수 있습니다.\n\n"
                "💡 **해결 방법:**\n"
                "Google Cloud Console에서 프로젝트에 **결제 수단(신용카드)을 등록(Billing Enable)**하시면 넉넉한 한도(Pay-as-you-go)로 이용 가능합니다. "
                "(개인 용도로 과도하게 사용하지 않는 이상 기본 제공량 내에서 처리되어 요금이 청구되지 않으니 안심하세요!)"
            )
        return f"⚠️ AI 해설 생성 중 오류 발생: {e2}"


def get_edgar_link(ticker: str) -> str:
    return (f"https://www.sec.gov/cgi-bin/browse-edgar"
            f"?action=getcompany&company={ticker}&type=4"
            f"&dateb=&owner=include&count=10&search_text=")


def parse_insider(tk, ticker_str: str):
    edgar_url = get_edgar_link(ticker_str)
    status    = "내역 없음"
    detail    = ""
    try:
        insider_trans = tk.insider_transactions
        if insider_trans is None or insider_trans.empty:
            return "내역 없음", "", edgar_url

        for idx, row in insider_trans.head(30).iterrows():
            row_dict = {k.lower(): v for k, v in row.to_dict().items()}
            row_str  = str(row_dict)

            is_buy = ("buy" in row_str.lower() or "purchase" in row_str.lower())
            is_sell_or_exercise = ("sale" in row_str.lower() or "sell" in row_str.lower() or
                                   "exercise" in row_str.lower() or "tax" in row_str.lower())

            if is_buy and not is_sell_or_exercise:
                name = (row_dict.get('insider') or row_dict.get('name') or
                        row_dict.get('filer') or "이름 미상")
                raw_title = (row_dict.get('title') or row_dict.get('relationship') or
                             row_dict.get('position') or row_dict.get('role') or "")
                title = normalize_title(str(raw_title))
                shares = (row_dict.get('shares') or row_dict.get('qty') or
                          row_dict.get('quantity') or "미상")
                value = (row_dict.get('value') or row_dict.get('transaction value') or None)

                date_str = (idx.strftime('%Y-%m-%d') if hasattr(idx, 'strftime') else str(idx)[:10])
                status = "🟢 매수 기록 있음"
                value_str = f" / 거래금액 ${value:,.0f}" if value and isinstance(value, (int, float)) else ""
                detail = (f"[{date_str}] {name} — {title}\n        순수 매수 {shares}주{value_str}")
                break

        if status == "내역 없음":
            try:
                first = insider_trans.iloc[0]
                row_dict = {k.lower(): v for k, v in first.to_dict().items()}
                trans_type = (row_dict.get('transaction') or row_dict.get('text') or "거래 기록 있음 (매수 아님)")
                status = f"⚪ {str(trans_type)[:30]}"
            except Exception:
                status = "내역 없음"

    except Exception as e:
        status = f"조회 불가 ({str(e)[:30]})"

    return status, detail, edgar_url


def get_ai_signal(d):
    rsi  = d.get('RSI_14')
    cp   = d.get('Price')
    ma20 = d.get('MA20')
    vol  = d.get('Vol_ratio')
    macd = d.get('MACD_dir') or ""
    roe  = d.get('ROE')
    op_m = d.get('Op_Margin')
    change = d.get('Change', 0)
    ma5 = d.get('MA5', cp)

    if rsi is None or cp is None or ma20 is None: return "⚪ 데이터 부족 (판단 보류)"

    rsi_f    = float(rsi)
    cp_f     = float(cp)
    ma20_f   = float(ma20)
    vol_f    = float(vol) if vol is not None else 100.0
    change_f = float(change)
    ma5_f    = float(ma5)
    
    ma20_gap = (cp_f - ma20_f) / ma20_f * 100
    ma5_gap  = (cp_f - ma5_f) / ma5_f * 100 if ma5_f > 0 else 0

    roe_f  = float(roe)  if roe  is not None else None
    op_m_f = float(op_m) if op_m is not None else None
    if roe_f is not None and op_m_f is not None:
        if roe_f < 0 and op_m_f < 0: return "⚫ 경고 (적자 기업)"

    if rsi_f >= 75 and ma20_gap > 15: return "🔵 과매수 (익절/관망)"
    if 60 <= rsi_f < 75 and cp_f > ma20_f and "상승" in macd and vol_f > 120: return "🚀 추세 탑승 (불타기)"
    if 40 <= rsi_f < 60 and cp_f >= ma20_f * 0.95: return "🟢 상승장 눌림목 (GTC 대기)"
    if rsi_f < 40:
        # 떨어지는 칼날 방어
        if change_f <= -3.0 or ma5_gap <= -4.0:
            return "⚠️ 떨어지는 칼날 (매수 대기)"
        return "🟠 Value 후보 (Scout 별도 검토)"
    return "🟡 방향성 탐색 (관망)"


def calculate_smart_target(d, ai_sig):
    cp       = d.get('Price')
    ma5      = d.get('MA5', cp)
    ma20     = d.get('MA20', cp)
    bb_upper = d.get('BB_upper', cp)
    bb_lower = d.get('BB_lower', cp)
    
    if cp is None or ma20 is None or bb_lower is None: return "-", "데이터 부족"
    
    if "추세 탑승"  in ai_sig: 
        return max(ma5, cp * 0.98), "5일선 지지"
    elif "눌림목"   in ai_sig: 
        if cp > ma20:
            return ma20, "20일선 부근 GTC"
        else:
            return bb_lower, "20선 하회 (볼린저하단 GTC)"
    elif "Value 후보" in ai_sig:
        return bb_lower, "볼린저 하단 GTC"
    elif "과매수"   in ai_sig: 
        return bb_upper,  "볼린저 상단"
    else: 
        return "-", "홀딩(Wait)"


def get_tenbagger_signal(d):
    mcap     = float(d.get('MarketCap') or 0)
    region   = d.get('Region')
    rev_g    = float(d.get('Rev_Growth') or 0)
    earn_g   = float(d.get('Earnings_Growth') or 0)
    peg      = float(d.get('PEG')        or 99)
    gap_high = float(d.get('Gap_High')   or 0)
    op_m     = d.get('Op_Margin')
    is_turnaround = d.get("Is_Turnaround", False)
    rule_40  = d.get("Rule_of_40")

    if region == "미국" and mcap >= 100_000_000_000:   return "-"
    if region == "한국" and mcap >= 10_000_000_000_000: return "-"

    is_rule_40_passed = rule_40 is not None and rule_40 >= 40

    if rev_g < 0.20:
        is_exception = False
        if is_turnaround:
            is_exception = True
        elif op_m is not None and float(op_m) >= 0.20:
            is_exception = True
        elif is_rule_40_passed:
            is_exception = True

        if not is_exception:
            return "-"

    if gap_high < -35.0: return "-"

    points = 0
    if rev_g >= 0.30: points += 1
    if earn_g >= 0.30 or is_turnaround: points += 1
    if 0 < peg <= 1.5: points += 1
    if op_m is not None and float(op_m) >= 0.20: points += 1
    if is_rule_40_passed: points += 2

    if points >= 3: return "🔥 기관 최선호 대장주 (Rule of 40)" if is_rule_40_passed else "🔥 기관 최선호 대장주"
    if points >= 1: return "🌱 우량 고성장주 (Rule of 40)" if is_rule_40_passed else "🌱 우량 고성장주"
    return "-"

# Force Streamlit to reload this module

# ─────────────────────────────────────────
# US Market ORION Signal Scoring
# ─────────────────────────────────────────
def calculate_us_orion_score(macro_data, as_of=None):
    """
    Calculate the US ORION Signal score (0-100) based on macroeconomic and market data.
    macro_data: dict of dataframes from data_loader
    Returns: total_score, phase, score_components, triggers, metrics
    """
    score_components = {'macro': 0.0, 'credit': 0.0, 'strength': 0.0, 'aux': 0.0}
    triggers, metrics = [], {}

    def get_series(key, col='Close'):
        df = macro_data.get(key)
        if df is None or df.empty or col not in df:
            return None
        series = pd.to_numeric(df[col], errors='coerce').dropna()
        return series if not series.empty else None

    def get_last(key, col='Close'):
        series = get_series(key, col)
        return float(series.iloc[-1]) if series is not None else None

    def period_return(key, periods):
        series = get_series(key)
        if series is None or len(series) <= periods:
            return None
        return float(series.iloc[-1] / series.iloc[-periods - 1] - 1.0)

    def clamp(value):
        return max(0.0, min(100.0, float(value)))

    # ── 데이터 품질 게이트: 결측·노후 데이터는 중립점수로 숨기지 않는다. ──
    missing, stale = [], []
    now = pd.Timestamp(as_of if as_of is not None else pd.Timestamp.now()).tz_localize(None).normalize()
    for key in (
        'spy_10y', 'vix_10y', 'rsp_10y', 'soxx_10y',
        'tnx_10y', 'tyx_10y', 'irx_10y', 'dxy_10y', 'usdjpy_10y',
        'hyg_10y', 'ief_10y',
    ):
        series = get_series(key)
        if series is None:
            missing.append(key)
            continue
        last_date = pd.Timestamp(series.index[-1]).tz_localize(None).normalize()
        if (now - last_date).days > 4:
            stale.append(key)
    fred = macro_data.get('fred_macro', pd.DataFrame())
    for col in ('WALCL', 'WTREGEN', 'RRPONTSYD', 'BAMLH0A0HYM2'):
        if fred.empty or col not in fred or pd.to_numeric(fred[col], errors='coerce').dropna().empty:
            missing.append(f'fred:{col}')
    fred_as_of = macro_data.get('fred_as_of', {})
    for col, max_age in (('WALCL', 10), ('WTREGEN', 10), ('RRPONTSYD', 4), ('BAMLH0A0HYM2', 4)):
        date = pd.to_datetime(fred_as_of.get(col), errors='coerce')
        if pd.isna(date):
            missing.append(f'fred_as_of:{col}')
        elif (now - date.normalize()).days > max_age:
            stale.append(f'fred:{col}')
    data_quality = {'valid': not missing and not stale, 'missing': missing, 'stale': stale}
    metrics['data_quality'] = data_quality

    # 1. Macro & Liquidity (35%)
    fed_liquidity_score = 50.0
    if not fred.empty and all(col in fred for col in ('WALCL', 'WTREGEN', 'RRPONTSYD')):
        # WALCL·WTREGEN = USD millions, RRPONTSYD = USD billions.
        liquidity = (
            pd.to_numeric(fred['WALCL'], errors='coerce')
            - pd.to_numeric(fred['WTREGEN'], errors='coerce')
            - pd.to_numeric(fred['RRPONTSYD'], errors='coerce') * 1000.0
        ).dropna()
        if len(liquidity) >= 29:
            curr_liq = float(liquidity.iloc[-1])
            change_4w_b = (curr_liq - float(liquidity.iloc[-29])) / 1000.0
            metrics.update(net_liquidity=curr_liq / 1000.0, net_liquidity_4w_change=change_4w_b)
            if change_4w_b > 50:
                fed_liquidity_score = 80.0
            elif change_4w_b > 0:
                fed_liquidity_score = 65.0
            elif change_4w_b > -50:
                fed_liquidity_score = 45.0
            else:
                fed_liquidity_score = 20.0
            triggers.append(f"연준 유동성 프록시 4주 변화 {change_4w_b:+.1f}B")

    dxy = get_last('dxy_10y')
    dxy_20d = period_return('dxy_10y', 20)
    dxy_score = 50.0
    if dxy is not None:
        metrics['dxy'] = dxy
    if dxy_20d is not None:
        metrics['dxy_20d_return'] = dxy_20d
        dxy_score = clamp(50.0 - dxy_20d * 1000.0)
        if abs(dxy_20d) >= 0.02:
            triggers.append(f"DXY 20일 변화 {dxy_20d*100:+.1f}%")

    jpy = get_last('usdjpy_10y')
    jpy_5d = period_return('usdjpy_10y', 5)
    jpy_20d = period_return('usdjpy_10y', 20)
    jpy_score = 55.0
    if jpy is not None:
        metrics['usdjpy'] = jpy
    if (jpy_5d is not None and jpy_5d <= -0.03) or (jpy_20d is not None and jpy_20d <= -0.05):
        jpy_score = 20.0
        triggers.append("USD/JPY 급락으로 엔캐리 청산 위험")

    tnx, tyx, irx = get_last('tnx_10y'), get_last('tyx_10y'), get_last('irx_10y')
    tnx_5d = period_return('tnx_10y', 5)
    yield_score = 60.0
    if tnx is not None:
        metrics['tnx'] = tnx
        if tnx > 4.65:
            yield_score -= 20.0
            triggers.append(f"10년물 {tnx:.2f}%로 기술주 적정가치 부담")
    if tnx_5d is not None and tnx_5d > 0.025:
        yield_score -= 15.0
        triggers.append("10년물 금리 5일 급등")
    if tyx is not None:
        metrics['tyx'] = tyx
        if tyx >= 5.20:
            yield_score -= 20.0
            triggers.append(f"30년물 {tyx:.2f}%로 장기 적정가치 부담")
    if tnx is not None and irx is not None:
        spread = tnx - irx
        metrics['yield_spread'] = spread
        yield_score += 5.0 if spread > 0 else -10.0
    yield_score = clamp(yield_score)

    macro_score = (fed_liquidity_score + dxy_score + jpy_score + yield_score) / 4.0
    score_components['macro'] = macro_score * 0.35

    # 2. Credit & Volatility (35%)
    hy_score = 50.0
    if not fred.empty and 'BAMLH0A0HYM2' in fred:
        hy = pd.to_numeric(fred['BAMLH0A0HYM2'], errors='coerce').dropna()
        if not hy.empty:
            hy_spread = float(hy.iloc[-1])
            hy_5d_change = float(hy.iloc[-1] - hy.iloc[-6]) if len(hy) > 5 else 0.0
            metrics.update(hy_spread=hy_spread, hy_spread_5d_change=hy_5d_change)
            if hy_spread < 4.0 and hy_5d_change <= 0.15:
                hy_score = 80.0
            elif hy_spread > 5.5 or hy_5d_change >= 0.50:
                hy_score = 15.0
                triggers.append(f"하이일드 스프레드 경색 ({hy_spread:.2f}%, 5일 {hy_5d_change:+.2f}%p)")
            else:
                hy_score = 50.0

    vix, vix3m = get_last('vix_10y'), None
    vix3m_series = get_series('vix3m_10y')
    if vix3m_series is not None:
        vix3m_date = pd.Timestamp(vix3m_series.index[-1]).tz_localize(None).normalize()
        if (now - vix3m_date).days <= 4:
            vix3m = float(vix3m_series.iloc[-1])
        else:
            metrics['vix3m_optional_stale'] = True
    vix_score = 55.0
    if vix is not None:
        metrics['vix'] = vix
        if vix >= 30:
            vix_score = 10.0
        elif vix >= 20:
            vix_score = 35.0
        elif vix < 12:
            vix_score = 45.0  # 극단적 안도는 추격매수 보너스로 사용하지 않는다.
        else:
            vix_score = 70.0
    if vix is not None and vix3m is not None:
        metrics['vix_term_ratio'] = vix / vix3m
        if vix >= vix3m:
            vix_score -= 20.0
            triggers.append("VIX 기간구조 백워데이션으로 단기 스트레스 확인")
    vix_score = clamp(vix_score)

    spy_series = get_series('spy_10y')
    spy_rsi = 50.0
    if spy_series is not None and len(spy_series) > 14:
        spy_rsi = float(get_rolling_rsi(spy_series, 14).iloc[-1])
    metrics['spy_rsi'] = spy_rsi
    if spy_rsi < 30:
        rsi_score = 30.0
    elif spy_rsi < 45:
        rsi_score = 50.0
    elif spy_rsi <= 65:
        rsi_score = 75.0
    elif spy_rsi <= 75:
        rsi_score = 55.0
    else:
        rsi_score = 30.0
        triggers.append(f"SPY RSI {spy_rsi:.1f} 과열로 추격매수 경계")

    credit_score = (hy_score + vix_score + rsi_score) / 3.0
    score_components['credit'] = credit_score * 0.35

    # 3. Market Breadth & Trend (25%)
    strength_score = 50.0
    rsp_20d, spy_20d, soxx_20d = period_return('rsp_10y', 20), period_return('spy_10y', 20), period_return('soxx_10y', 20)
    if rsp_20d is not None and spy_20d is not None:
        metrics['rsp_spy_20d_gap'] = rsp_20d - spy_20d
        strength_score += 15.0 if rsp_20d >= spy_20d else -10.0
        triggers.append(f"RSP-SPY 20일 상대수익률 {(rsp_20d-spy_20d)*100:+.1f}%p")
    if soxx_20d is not None and spy_20d is not None:
        metrics['soxx_spy_20d_gap'] = soxx_20d - spy_20d
        strength_score += 15.0 if soxx_20d >= spy_20d else -10.0
        triggers.append(f"SOXX-SPY 20일 상대수익률 {(soxx_20d-spy_20d)*100:+.1f}%p")
    if spy_series is not None and len(spy_series) >= 21:
        spy_ma20 = float(spy_series.rolling(20).mean().iloc[-1])
        metrics['spy_above_ma20'] = bool(spy_series.iloc[-1] >= spy_ma20)
        strength_score += 15.0 if metrics['spy_above_ma20'] else -20.0
    strength_score = clamp(strength_score)
    score_components['strength'] = strength_score * 0.25

    # 4. Auxiliary risk appetite (5%): BTC는 보조 확인에만 제한한다.
    btc = get_last('btc_10y')
    btc_series = get_series('btc_10y')
    aux_score = 50.0
    if btc is not None and btc_series is not None and len(btc_series) >= 50:
        metrics['btc'] = btc
        aux_score = 70.0 if btc >= float(btc_series.rolling(50).mean().iloc[-1]) else 35.0
    score_components['aux'] = aux_score * 0.05

    total_score = sum(score_components.values())
    if not data_quality['valid']:
        us_phase = "DATA_ERROR"
        triggers.append(f"데이터 품질 차단: 결측 {missing or '없음'}, 노후 {stale or '없음'}")
    elif total_score >= 65:
        us_phase = "CLEAR"
    elif total_score >= 40:
        us_phase = "CAUTION"
    else:
        us_phase = "ALERT"
    return total_score, us_phase, score_components, triggers, metrics


def evaluate_us_entry_permission(
    macro_data,
    us_phase,
    metrics,
    flow_score=0,
    flow_is_stale=True,
    environment_score=None,
):
    """중복 하드게이트를 제거한 미국 주식 단계형 선발대 허가."""
    checks = {}
    quality = metrics.get('data_quality', {})
    checks['data_quality'] = bool(quality.get('valid', False))

    if environment_score is None:
        environment_score = US_FULL_ENTRY if us_phase == 'CLEAR' else 0.0
    environment_score = float(environment_score)
    checks['environment_floor_60'] = environment_score >= US_ENTRY_FLOOR
    checks['environment_full_65'] = environment_score >= US_FULL_ENTRY

    spy = macro_data.get('spy_10y', pd.DataFrame())
    rsp = macro_data.get('rsp_10y', pd.DataFrame())
    hyg = macro_data.get('hyg_10y', pd.DataFrame())
    ief = macro_data.get('ief_10y', pd.DataFrame())

    falling_knife = True
    checks['trend_confirmed'] = False
    if spy is not None and not spy.empty and 'Close' in spy and len(spy) >= 22:
        close = pd.to_numeric(spy['Close'], errors='coerce').dropna()
        ma5 = close.rolling(5).mean()
        ma20 = close.rolling(20).mean()
        ret_1d = float(close.pct_change().iloc[-1] * 100)
        ma5_gap = float((close.iloc[-1] / ma5.iloc[-1] - 1) * 100)
        falling_knife = ret_1d <= KNIFE_1D_RET or ma5_gap <= KNIFE_MA5_GAP
        checks['trend_confirmed'] = bool(close.iloc[-1] >= ma20.iloc[-1])
        metrics['spy_1d_return'] = ret_1d
        metrics['spy_ma5_gap'] = ma5_gap
    checks['falling_knife_released'] = not falling_knife

    checks['breadth_confirmed'] = False
    if all(df is not None and not df.empty and 'Close' in df and len(df) > 5 for df in (rsp, spy)):
        pair = pd.concat([rsp['Close'], spy['Close']], axis=1).dropna()
        if len(pair) > 5:
            ratio = pair.iloc[:, 0] / pair.iloc[:, 1]
            breadth_5d_change = float(ratio.iloc[-1] / ratio.iloc[-6] - 1.0)
            metrics['rsp_spy_5d_change'] = breadth_5d_change
            checks['breadth_confirmed'] = bool(breadth_5d_change >= 0)

    # 실제 펀드플로우가 아닌 가격·거래량 확인은 소프트 조건으로만 사용한다.
    checks['price_volume_confirmed'] = bool(not flow_is_stale and flow_score > 0)

    credit_ratio_change = None
    if all(df is not None and not df.empty and 'Close' in df and len(df) > 5 for df in (hyg, ief)):
        pair = pd.concat([hyg['Close'], ief['Close']], axis=1).dropna()
        if len(pair) > 5:
            ratio = pair.iloc[:, 0] / pair.iloc[:, 1]
            credit_ratio_change = float(ratio.iloc[-1] / ratio.iloc[-6] - 1.0)
            metrics['hyg_ief_5d_change'] = credit_ratio_change
    hy_spread = metrics.get('hy_spread')
    hy_change = metrics.get('hy_spread_5d_change')
    credit_stress = (
        credit_ratio_change is None
        or credit_ratio_change <= US_CREDIT_RATIO_VETO
        or (hy_spread is not None and hy_spread > 5.5)
        or (hy_change is not None and hy_change >= 0.50)
    )
    checks['credit_stress_absent'] = not credit_stress

    soft_keys = ('trend_confirmed', 'breadth_confirmed', 'price_volume_confirmed')
    soft_count = sum(bool(checks[key]) for key in soft_keys)
    metrics['entry_confirmation_count'] = soft_count

    labels = {
        'data_quality': '필수 데이터가 정상 확인되지 않음',
        'environment_floor_60': f'환경점수 {US_ENTRY_FLOOR:.0f}점 미만',
        'environment_full_65': f'10% 선발대 기준 {US_FULL_ENTRY:.0f}점 미만',
        'trend_confirmed': 'SPY가 20일선 위에 있지 않음',
        'breadth_confirmed': 'RSP/SPY 최근 5일 시장 폭이 개선되지 않음',
        'price_volume_confirmed': '가격·거래량 상승 확인이 부족함',
        'falling_knife_released': '낙하 칼날 안전장치가 해제되지 않음',
        'credit_stress_absent': '명확한 신용 스트레스가 감지됨',
    }
    reasons = [labels[key] for key, passed in checks.items() if not passed]

    if not checks['data_quality']:
        state, allocation = 'DATA_VETO', 0
    elif not checks['falling_knife_released']:
        state, allocation = 'FALLING_KNIFE_VETO', 0
    elif not checks['credit_stress_absent']:
        state, allocation = 'CREDIT_STRESS_VETO', 0
    elif not checks['environment_floor_60'] or soft_count < 2:
        state, allocation = 'ENTRY_WAIT', 0
    elif checks['environment_full_65'] and soft_count == 3:
        state, allocation = 'STARTER_GO_10', 10
    else:
        state, allocation = 'STARTER_GO_5', 5

    metrics['entry_allocation_pct'] = allocation
    metrics['entry_state'] = state
    return state, checks, reasons


def run_us_orion_walkforward_validation(
    macro_data,
    transaction_cost_bps=5.0,
    min_history=60,
    horizons=(5, 20, 60),
    cooldown_days=20,
):
    """WAIT에 기존 보유분을 청산하지 않는 진입 이벤트 기반 워크포워드 검증."""
    spy = macro_data.get('spy_10y', pd.DataFrame())
    if spy is None or spy.empty or 'Close' not in spy or len(spy) < min_history + 2:
        return {'usable': False, 'reason': 'insufficient_spy_history'}

    spy_close = pd.to_numeric(spy['Close'], errors='coerce').dropna()
    dates = spy_close.index
    signal_rows = []

    def historical_flow_proxy(frame):
        if frame is None or frame.empty or not {'Close', 'Volume'}.issubset(frame.columns) or len(frame) < 20:
            return None
        close = pd.to_numeric(frame['Close'], errors='coerce').dropna()
        volume = pd.to_numeric(frame['Volume'], errors='coerce').reindex(close.index)
        if len(close) < 20 or volume.dropna().empty:
            return None
        avg_volume = volume.rolling(20).mean().iloc[-1]
        if pd.isna(avg_volume) or avg_volume <= 0:
            return None
        return float(close.pct_change().iloc[-1] * 100.0 * volume.iloc[-1] / avg_volume)

    for idx in range(min_history, len(dates) - 1):
        as_of = pd.Timestamp(dates[idx]).tz_localize(None)
        sliced = {}
        for key, value in macro_data.items():
            if isinstance(value, pd.DataFrame) and isinstance(value.index, pd.DatetimeIndex):
                sliced[key] = value.loc[value.index <= as_of].copy()
            else:
                sliced[key] = value
        fred_slice = sliced.get('fred_macro', pd.DataFrame())
        if not fred_slice.empty:
            sliced['fred_as_of'] = {
                col: pd.Timestamp(fred_slice[col].dropna().index[-1]).strftime('%Y-%m-%d')
                for col in fred_slice.columns if not fred_slice[col].dropna().empty
            }

        base_score, base_phase, _, _, metrics = calculate_us_orion_score(sliced, as_of=as_of)
        flow_values = [
            historical_flow_proxy(sliced.get(key, pd.DataFrame()))
            for key in ('spy_10y', 'qqq_10y', 'soxx_10y')
        ]
        flow_stale = any(value is None for value in flow_values)
        flow_score = 0
        if not flow_stale:
            flow_score, _, _ = calculate_us_flow_signal(*flow_values)
        final_score = max(0.0, min(100.0, base_score + flow_score * 0.2))
        final_phase = (
            'DATA_ERROR' if base_phase == 'DATA_ERROR'
            else 'CLEAR' if final_score >= 65
            else 'CAUTION' if final_score >= 40
            else 'ALERT'
        )
        state, _, _ = evaluate_us_entry_permission(
            sliced,
            final_phase,
            metrics,
            flow_score=flow_score,
            flow_is_stale=flow_stale,
            environment_score=final_score,
        )
        signal_rows.append({
            'date': as_of,
            'state': state,
            'score': final_score,
            'eligible': bool(metrics.get('data_quality', {}).get('valid', False)),
        })

    if not signal_rows:
        return {'usable': False, 'reason': 'no_validation_observations'}

    signal_df = pd.DataFrame(signal_rows).set_index('date')
    # 모든 비교군은 필수 데이터가 동시에 존재하는 공통 구간만 사용한다.
    signal_df = signal_df[signal_df['eligible']].copy()
    if signal_df.empty:
        return {'usable': False, 'reason': 'no_common_valid_data_window'}
    spy_open = pd.to_numeric(spy.get('Open', spy['Close']), errors='coerce').reindex(dates)
    spy_low = pd.to_numeric(spy.get('Low', spy['Close']), errors='coerce').reindex(dates)
    round_trip_cost = transaction_cost_bps * 2.0 / 10000.0

    def spaced_indices(mask):
        selected, last_idx = [], -10**9
        for date in signal_df.index[mask]:
            absolute_idx = dates.get_loc(date)
            if absolute_idx - last_idx > cooldown_days:
                selected.append(absolute_idx)
                last_idx = absolute_idx
        return selected

    def event_summary(mask):
        selected = spaced_indices(mask)
        result = {'signal_days': int(mask.sum()), 'independent_events': int(len(selected))}
        for horizon in horizons:
            returns, adverse = [], []
            for idx in selected:
                if idx + horizon >= len(dates):
                    continue
                entry = float(spy_open.iloc[idx + 1])
                exit_value = float(spy_close.iloc[idx + horizon])
                path_low = spy_low.iloc[idx + 1:idx + horizon + 1]
                if entry <= 0 or pd.isna(exit_value) or path_low.dropna().empty:
                    continue
                returns.append(exit_value / entry - 1.0 - round_trip_cost)
                adverse.append(float(path_low.min() / entry - 1.0))
            values = np.asarray(returns, dtype=float)
            mae = np.asarray(adverse, dtype=float)
            result[str(horizon)] = {
                'events': int(len(values)),
                'mean_return': float(values.mean()) if len(values) else None,
                'median_return': float(np.median(values)) if len(values) else None,
                'hit_rate': float((values > 0).mean()) if len(values) else None,
                'p10_return': float(np.quantile(values, 0.10)) if len(values) else None,
                'median_max_adverse': float(np.median(mae)) if len(mae) else None,
            }
        return result

    five_mask = signal_df['state'] == 'STARTER_GO_5'
    ten_mask = signal_df['state'] == 'STARTER_GO_10'
    any_mask = five_mask | ten_mask
    all_mask = pd.Series(True, index=signal_df.index)

    return {
        'usable': True,
        'method': 'entry_event_next_open_no_forced_exit_on_wait',
        'observations': int(len(signal_df)),
        'signal_rate': float(any_mask.mean()),
        'signals': {
            'all_days_baseline': event_summary(all_mask),
            'starter_any': event_summary(any_mask),
            'starter_5': event_summary(five_mask),
            'starter_10': event_summary(ten_mask),
        },
        'last_score': float(signal_df['score'].iloc[-1]),
        'last_state': str(signal_df['state'].iloc[-1]),
        'transaction_cost_bps_each_way': float(transaction_cost_bps),
        'cooldown_days': int(cooldown_days),
    }

def get_us_strategic_advice(us_phase, total_score, triggers):
    """
    Generate dynamic advice string based on US ORION triggers.
    """
    if us_phase == "CLEAR":
        head = "🟢 위험선호 검토 가능 (CLEAR) - 진입 게이트 별도 확인"
        color = "#2e7d32"
    elif us_phase == "CAUTION":
        head = "🟡 환경 주의 (CAUTION) - 단계형 진입 게이트 확인"
        color = "#fbc02d"
    elif us_phase == "ALERT":
        head = "🔴 위험 회피 (ALERT) - 방어적 자산 배분 우선"
        color = "#c62828"
    else:
        head = "⚫ 데이터 검증 실패 (DATA ERROR) - 신규 주문 금지"
        color = "#424242"
        
    actions = []
        
    # Add top news action point if we can fetch it
    try:
        from data_loader import get_market_news
        us_news = get_market_news("US", limit=5)
        top_news = [n for n in us_news if n.get("importance", 0) >= 4]
        if top_news:
            latest_important = top_news[0]
            action = latest_important.get("action_point")
            if action:
                # Resolve contradiction
                sentiment = latest_important.get("sentiment", "")
                prefix = "📰 **최고 중요도 뉴스 기반 대응**"
                if sentiment == "악재" and us_phase == "CLEAR":
                    prefix = "📰 **단기 노이즈 주의(단기 악재 뉴스 포착)**"
                elif sentiment == "호재" and us_phase == "ALERT":
                    prefix = "📰 **단기 반등 재료(호재 뉴스 포착)**"
                actions.append(f"{prefix}: {action}")
    except Exception as e:
        pass
        
    if us_phase == "CLEAR":
        actions.append("🔎 **투자 전략**: 시장환경과 안전장치를 분리합니다. 단계형 진입 게이트가 허용한 예정금의 5% 또는 10%만 집행합니다.")
    elif us_phase == "CAUTION":
        actions.append("⚖️ **투자 전략**: 신규 투자는 단계형 게이트가 허용한 범위만 집행하고, 기존 보유분은 시장 신호만으로 매도하지 않습니다.")
    elif us_phase == "ALERT":
        actions.append("🛡️ **투자 전략**: 하방 리스크가 큽니다. 단기채(SGOV 등) 및 현금 비중을 대폭 늘리십시오.")
    else:
        actions.append("⛔ **투자 전략**: 결측·노후 데이터를 갱신하기 전에는 신규 주문을 실행하지 마십시오.")
        
    return head, color, actions


def get_us_trigger_display(trigger):
    """미국 진단 근거의 의미와 아이콘을 일치시킨다."""
    import re

    text = str(trigger)
    if "데이터 품질 차단" in text:
        return "⚫", text
    if "4주 변화" in text or "상대수익률" in text:
        match = re.search(r"([+-]\d+(?:\.\d+)?)", text)
        if match:
            value = float(match.group(1))
            return ("🟢" if value >= 0 else "🔴"), text
    red_words = (
        "부담", "급등", "경색", "악화", "위험", "과열", "백워데이션",
        "청산", "축소", "하회", "스트레스",
    )
    green_words = ("확대", "완화", "회복", "안정", "상회", "양호")
    if any(word in text for word in red_words):
        return "🔴", text
    if any(word in text for word in green_words):
        return "🟢", text
    return "🟡", text




def generate_us_economic_commentary(summary_dict, phase):
    import os
    
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return "⚠️ 환경 변수에 GEMINI_API_KEY가 설정되지 않아 AI 브리핑을 제공할 수 없습니다."
    
    prompt = f"""너는 월스트리트 출신의 매크로 전략가이자 퀀트 펀드 매니저다.
아래 전달받은 미국 증시 핵심 데이터와 시스템이 판정한 시장 국면을 바탕으로 가장 날카롭고 입체적인 브리핑을 작성하라.
단순히 숫자를 나열하지 말고, [매크로/유동성의 구조적 변화 ➔ 미국 증시 반영 여부 ➔ 섹터 수급(SPY, QQQ, SOXX) 괴리 포착 ➔ 유리한 섹터/테마 암시 ➔ 최종 행동 강령] 순으로 인과관계에 맞게 해설해라.

[미국 매크로 및 유동성 핵심 지표]
    - 미국 10년물 국채 금리: {summary_dict.get('TNX_10Y', 'N/A')}
    - 달러 인덱스 (DXY): {summary_dict.get('DXY', 'N/A')}
    - 하이일드 스프레드: {summary_dict.get('HY_Spread', 'N/A')}
    - 연준 순유동성: {summary_dict.get('Net_Liquidity', 'N/A')}
    - VIX 공포지수: {summary_dict.get('VIX', 'N/A')}

[미국 주요 ETF 당일 가격·거래량 프록시 (양수=상승 확인, 음수=하락 확인)]
    - SPY (S&P 500): {summary_dict.get('SPY_Flow', 'N/A')}
    - QQQ (나스닥): {summary_dict.get('QQQ_Flow', 'N/A')}
    - SOXX (반도체): {summary_dict.get('SOXX_Flow', 'N/A')}

[시스템 판정 국면]
    - 현재 국면: {phase}

출력 형식은 마크다운을 사용하며, 너무 길지 않게 핵심만 3~4개의 글머리 기호(Bullet point)로 나누어 전달하라. 마지막엔 한 줄 요약(Action Point)을 덧붙여라.
"""
    
    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        
        models_to_try = [
            "gemini-2.5-pro",
            "gemini-3.5-flash",
            "gemini-3.1-flash-lite",
            "gemini-1.5-flash-lite",
            "gemini-pro-latest",
            "gemini-flash-latest"
        ]
        
        response = None
        successful_model = None
        errors = []
        
        for model_name in models_to_try:
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt
                )
                successful_model = model_name
                break
            except Exception as e:
                errors.append(f"- 신규 SDK {model_name} 실패: {str(e)}")
                continue
                
        if response:
            return f"*(적용된 AI 모델: {successful_model})*\n\n" + response.text.strip()
        else:
            try:
                import google.generativeai as genai_old
                genai_old.configure(api_key=api_key)
                for old_model in models_to_try:
                    try:
                        model = genai_old.GenerativeModel(old_model)
                        safety_settings = [
                            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
                        ]
                        old_response = model.generate_content(prompt, safety_settings=safety_settings)
                        if old_response and old_response.text:
                            return f"*(구형 SDK 모델: {old_model} 우회 성공)*\n\n" + old_response.text.strip()
                    except Exception as e_old:
                        errors.append(f"- 구형 SDK {old_model} 실패: {str(e_old)}")
            except Exception as e_import:
                errors.append(f"- 구형 SDK 로드 실패: {str(e_import)}")
                
            error_details = "\n".join(errors)
            return (
                f"⚠️ **AI 모델 호출에 모두 실패했습니다.**\n\n"
                f"**[상세 에러 로그]**\n{error_details}"
            )
            
    except Exception as e:
        return f"⚠️ 브리핑 생성 중 예외 발생: {e}"




def calculate_us_flow_signal(spy_flow, qqq_flow, soxx_flow):
    """
    US ETF 종가와 거래량 기반 프록시로 단기 가격 압력을 판정합니다.
    """
    score = 0
    details = []
    
    avg_flow = (spy_flow + qqq_flow) / 2
    
    if avg_flow > 0.5:
        score += 40
        status = "🟢 강한 가격·거래량 상승 확인"
    elif avg_flow > 0:
        score += 20
        status = "🟡 약한 가격·거래량 상승 확인"
    elif avg_flow > -0.5:
        score -= 20
        status = "🟠 약한 가격·거래량 하락 확인"
    else:
        score -= 40
        status = "🔴 강한 가격·거래량 하락 확인"

    # 반도체는 경고 문구만 띄우지 않고 제한된 범위에서 실제 점수에도 반영한다.
    if soxx_flow > 1.0:
        score += 10
    elif soxx_flow < -1.0:
        score -= 10
    score = max(-40, min(40, score))
        
    details.append(("🏢", f"SPY 가격·거래량 프록시: {spy_flow:+.2f}"))
    details.append(("🚀", f"QQQ 가격·거래량 프록시: {qqq_flow:+.2f}"))
    details.append(("💻", f"SOXX 가격·거래량 프록시: {soxx_flow:+.2f}"))
    
    if soxx_flow < -1.0:
        details.append(("⚠️", "반도체(SOXX) 가격·거래량이 강한 하락을 확인"))
    elif soxx_flow > 1.0:
        details.append(("🔥", "반도체(SOXX) 가격·거래량이 강한 상승을 확인"))
        
    return score, status, details

