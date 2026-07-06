import re

with open("signals.py", "r", encoding="utf-8") as f:
    content = f.read()

# 1. Replace risk radars
old_risk_radar = re.search(r"def calculate_us_risk_radar.*?return grade, color, alerts", content, flags=re.DOTALL).group(0)

new_risk_radar = """def calculate_us_risk_radar(vix_hist, vix3m_hist, hyg_hist, ief_hist, spy_hist):
    alerts = []
    danger_count = 0

    curr_vix   = float(vix_hist['Close'].iloc[-1])  if not vix_hist.empty  else None
    curr_vix3m = float(vix3m_hist['Close'].iloc[-1]) if not vix3m_hist.empty else None
    
    if curr_vix and curr_vix3m:
        if curr_vix > curr_vix3m * 1.05:
            alerts.append(("🔴", f"VIX 백워데이션 발생 ({curr_vix:.1f} > {curr_vix3m:.1f}). 단기 패닉 초입."))
            danger_count += 2
        elif curr_vix > curr_vix3m:
            alerts.append(("🟠", f"VIX 백워데이션 진입 중. 예비 주시."))
            danger_count += 1
        else:
            alerts.append(("🟢", f"VIX 콘탱고 정상. 시장 구조 안정."))

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

    credit_danger = False
    if not hyg_hist.empty and not ief_hist.empty:
        try:
            df_c = pd.concat([hyg_hist['Close'], ief_hist['Close']], axis=1).ffill().dropna()
            if len(df_c) >= 50:
                df_c.columns = ['HYG', 'IEF']
                df_c['R'] = df_c['HYG'] / df_c['IEF']
                ma20 = float(df_c['R'].rolling(20).mean().iloc[-1])
                ma50 = float(df_c['R'].rolling(50).mean().iloc[-1])
                curr = float(df_c['R'].iloc[-1])
                if curr < ma50 * 0.97:
                    alerts.append(("🔴", f"신용 스프레드 위험 이탈. 기관 투매 감지."))
                    danger_count += 2
                    credit_danger = True
                elif curr < ma20:
                    alerts.append(("🟠", f"신용 스프레드 단기 이탈. 주시 필요."))
                    danger_count += 1
                    credit_danger = True
                else:
                    alerts.append(("🟢", "신용 스프레드 안정 (정배열)."))
        except:
            alerts.append(("⚪", "신용 스프레드 산출 불가."))

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

    if danger_count >= 6:
        grade = "🚨 글로벌 마스터 킬 스위치 작동 — 시스템적 유동성 위기."
        color = "#ff0000"
    elif danger_count >= 4:
        grade = "🔴 글로벌 위기 경보 — 폭락 초입 가능성."
        color = "#ff4b4b"
    elif danger_count >= 2:
        grade = "🟠 글로벌 주의 단계 — 신규 진입 자제."
        color = "#ff9900"
    elif danger_count >= 1:
        grade = "🟡 글로벌 관찰 단계 — 경미한 이상 신호."
        color = "#fcca46"
    else:
        grade = "🟢 글로벌 마스터 이상 없음 — 매크로 환경 정상."
        color = "#21c354"

    return grade, color, alerts

def calculate_kr_risk_radar(vkospi_hist, usdkrw_hist, kospi_hist):
    alerts = []
    danger_count = 0

    if not usdkrw_hist.empty and len(usdkrw_hist) >= 20:
        curr_krw = float(usdkrw_hist['Close'].iloc[-1])
        krw_5d_ago = float(usdkrw_hist['Close'].iloc[-6])
        krw_surge = (curr_krw - krw_5d_ago) / krw_5d_ago * 100
        krw_rsi = calc_rsi(usdkrw_hist['Close'], 14)
        krw_ma20 = float(usdkrw_hist['Close'].rolling(20).mean().iloc[-1])
        krw_macd_val, krw_macd_dir = calc_macd(usdkrw_hist['Close'])
        
        if krw_surge >= 1.5 or (curr_krw > krw_ma20 and krw_rsi and krw_rsi >= 65):
            alerts.append(("🔴", f"환율 단기 폭등/추세이탈 (+{krw_surge:.1f}%, RSI {krw_rsi:.1f}) — 외국인 엑소더스 징후."))
            danger_count += 2
        elif krw_surge >= 0.8 or (krw_rsi and krw_rsi >= 55) or (krw_macd_dir == "🟢상승" and curr_krw > krw_ma20):
            alerts.append(("🟠", f"환율 상승세 (+{krw_surge:.1f}%) 및 MACD 상승 — 외국인 수급 악화 조기 경보."))
            danger_count += 1
        else:
            alerts.append(("🟢", f"환율 안정적 ({curr_krw:,.1f}원) — 외인 수급 이탈 우려 낮음."))

    if not vkospi_hist.empty and len(vkospi_hist) >= 20:
        curr_vk = float(vkospi_hist['Close'].iloc[-1])
        vk_ma20 = float(vkospi_hist['Close'].rolling(20).mean().iloc[-1])
        vk_spike = (curr_vk - vk_ma20) / vk_ma20 * 100 if vk_ma20 > 0 else 0
        vk_5d_ago = float(vkospi_hist['Close'].iloc[-6])
        vk_surge = (curr_vk - vk_5d_ago) / vk_5d_ago * 100 if vk_5d_ago > 0 else 0
        
        if vk_spike >= 30 or curr_vk >= 25 or vk_surge >= 25:
            alerts.append(("🔴", f"VKOSPI 급등 ({curr_vk:.1f}, +{vk_spike:.1f}% vs 20일평균) — 기관/외인 하락 헷지 팽창."))
            danger_count += 2
        elif vk_spike >= 15 or curr_vk >= 18 or vk_surge >= 15:
            alerts.append(("🟠", f"VKOSPI 불안 ({curr_vk:.1f}) — 파생 변동성 확대 조짐."))
            danger_count += 1
        else:
            alerts.append(("🟢", f"VKOSPI 평온 ({curr_vk:.1f}) — 하방 압력 낮음."))

    if not kospi_hist.empty and len(kospi_hist) >= 6:
        k_5d_ret = (float(kospi_hist['Close'].iloc[-1]) / float(kospi_hist['Close'].iloc[-6]) - 1) * 100
        if k_5d_ret <= -4:
            alerts.append(("🔴", f"KOSPI 5일 급락 ({k_5d_ret:.1f}%) — 프로그램 및 동반 투매 감지."))
            danger_count += 1
        elif k_5d_ret <= -2:
            alerts.append(("🟠", f"KOSPI 5일 하락 ({k_5d_ret:.1f}%) — 단기 매도 우위."))
        else:
            alerts.append(("🟢", f"KOSPI 단기 추세 ({k_5d_ret:+.1f}%) — 안정적."))

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

    return grade, color, alerts"""

content = content.replace(old_risk_radar, new_risk_radar)

# 2. Replace us bottom finder return block
old_us_return = """    score = min(int(score), 100)

    if drawdown > -5: verdict = "📈 고점권 — 바닥 탐지 불가"
    elif score >= 70: verdict = "🔥 강력 매수 신호 (역사적 바닥 근접)"
    elif score >= 50: verdict = "🟢 분할 매수 구간 (역발상 타점)"
    elif score >= 35: verdict = "🟡 조정 진행 중 (추가 하락 여지)"
    else: verdict = "⚪ 바닥 조건 미충족"

    return score, verdict, details, market_phase"""

new_us_return = """    score = min(int(score), 100)

    is_falling_knife = False
    if len(spy_close) >= 5:
        spy_1d_ret = (float(spy_close.iloc[-1]) / float(spy_close.iloc[-2]) - 1) * 100
        ma5 = float(spy_close.rolling(5).mean().iloc[-1])
        gap_ma5 = (curr_spy - ma5) / ma5 * 100
        
        if spy_1d_ret <= -2.5 or gap_ma5 <= -4.0:
            is_falling_knife = True
            if score >= 35:
                details.append(f"🚨 [Safety Catch] 당일 급락({spy_1d_ret:.1f}%) 또는 5일선 심각한 이탈({gap_ma5:.1f}%). 브레이크(양봉) 확인 후 진입 권장. (-20점 차감)")
                score = max(score - 20, 0)

    if drawdown > -5: verdict = "📈 고점권 — 바닥 탐지 불가"
    elif score >= 70: verdict = "🔥 강력 매수 신호 (역사적 바닥 근접)"
    elif score >= 50: verdict = "🟢 분할 매수 구간 (역발상 타점)"
    elif score >= 35: verdict = "🟡 조정 진행 중 (추가 하락 여지)"
    else: verdict = "⚪ 바닥 조건 미충족"

    if is_falling_knife and score >= 35:
        verdict = "⚠️ 떨어지는 칼날 (관망 권장)"

    return score, verdict, details, market_phase"""

content = content.replace(old_us_return, new_us_return)

# 3. Replace kr bottom finder return block
old_kr_return = """    score = min(int(score), 100)

    if drawdown > -5: verdict = "📈 고점권 — 바닥 탐지 불가"
    elif score >= 70: verdict = "🔥 강력 매수 신호 (역사적 바닥 근접)"
    elif score >= 50: verdict = "🟢 분할 매수 구간 (역발상 타점)"
    elif score >= 35: verdict = "🟡 조정 진행 중 (추가 하락 여지)"
    else: verdict = "⚪ 바닥 조건 미충족"

    return score, verdict, details, market_phase"""

new_kr_return = """    score = min(int(score), 100)

    is_falling_knife = False
    if len(kospi_close) >= 5:
        k_1d_ret = (float(kospi_close.iloc[-1]) / float(kospi_close.iloc[-2]) - 1) * 100
        ma5 = float(kospi_close.rolling(5).mean().iloc[-1])
        gap_ma5 = (curr_kospi - ma5) / ma5 * 100
        
        if k_1d_ret <= -2.5 or gap_ma5 <= -4.0:
            is_falling_knife = True
            if score >= 35:
                details.append(f"🚨 [Safety Catch] 당일 급락({k_1d_ret:.1f}%) 또는 5일선 심각한 이탈({gap_ma5:.1f}%). 브레이크(양봉) 확인 후 진입 권장. (-20점 차감)")
                score = max(score - 20, 0)

    if drawdown > -5: verdict = "📈 고점권 — 바닥 탐지 불가"
    elif score >= 70: verdict = "🔥 강력 매수 신호 (역사적 바닥 근접)"
    elif score >= 50: verdict = "🟢 분할 매수 구간 (역발상 타점)"
    elif score >= 35: verdict = "🟡 조정 진행 중 (추가 하락 여지)"
    else: verdict = "⚪ 바닥 조건 미충족"

    if is_falling_knife and score >= 35:
        verdict = "⚠️ 떨어지는 칼날 (관망 권장)"

    return score, verdict, details, market_phase"""

# Replace only the second occurrence (kr return)
content = content.replace(old_kr_return, new_kr_return, 1)

with open("signals.py", "w", encoding="utf-8") as f:
    f.write(content)
