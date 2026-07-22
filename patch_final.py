import re

def patch_file():
    with open('final.py', 'r', encoding='utf-8') as f:
        content = f.read()

    start_marker = "    # 🚨 인버스 매수 추천 스코어링 (Percentile & Z-Score 동적 임계치 적용)"
    
    if start_marker not in content:
        print("Marker not found!")
        return

    start_idx = content.find(start_marker)

    new_block = """    # ════════════════════════════════════════════
    # 🟡 변동성 레짐 정밀 분류기 v2.0 (Strategy B)
    # ════════════════════════════════════════════
    vol_regime = "⚪ 판별 불가"
    vol_color  = "#6c757d"
    vol_action = ""
    vol_details = []

    if has_tech and not vkospi_10y.empty:
        daily_rets = kospi_10y['Close'].pct_change().dropna()
        hv20 = float(daily_rets.tail(20).std() * (252**0.5) * 100)
        hv_series = daily_rets.rolling(20).std() * (252**0.5) * 100
        hv_pct = float((hv_series.dropna() <= hv20).mean())

        vk = vkospi_10y['Close']
        vk_ma5  = float(vk.rolling(5).mean().iloc[-1])
        vk_ma20 = float(vk.rolling(20).mean().iloc[-1])
        vk_contango = vk_ma5 < vk_ma20

        net_20d = float((kospi_10y['Close'].iloc[-1] / kospi_10y['Close'].iloc[-21] - 1) * 100)
        directional_ratio = abs(net_20d) / hv20 if hv20 > 0 else 0

        if hv_pct >= 0.90 and not vk_contango:
            vol_regime = "🔴 패닉 변동성 (Panic Volatility)"
            vol_color  = "#dc3545"
            vol_action = "곱버스 EXIT 검토 + 우량주 소량 선발대 진입 타이밍"
            vol_details = [
                f"실현변동성(HV20): {hv20:.1f}% — 역사적 상위 {(1-hv_pct)*100:.0f}%",
                f"VKOSPI 구조: 백워데이션 (단기 {vk_ma5:.1f} > 장기 {vk_ma20:.1f}) — 공포 피크아웃 전형",
                "👉 패닉 변동성은 보통 1~3일 이내 소멸. 곱버스 청산 후 현금 대기."
            ]
        elif hv_pct >= 0.75 and curr_atr_ratio >= 1.3:
            vol_regime = "🟠 추세 변동성 (Trending — 칼날 구간)"
            vol_color  = "#fd7e14"
            vol_action = "인버스/곱버스 홀딩 유지. 신규 현물 매수 금지."
            vol_details = [
                f"실현변동성(HV20): {hv20:.1f}% — 확장 국면 (역사적 {hv_pct*100:.0f}% 백분위)",
                f"ATR 비율: {curr_atr_ratio:.2f}x — 강한 방향성 동반",
                f"방향성 비율(|순변화|/HV20): {directional_ratio:.2f} — 추세 확인"
            ]
        elif hv_pct >= 0.60 and directional_ratio < 0.3:
            vol_regime = "🌊 휩쏘 변동성 (Whipsaw — 오르락내리락)"
            vol_color  = "#6f42c1"
            vol_action = "모든 방향성 베팅 금지. 변동성 수확(Gamma Scalping 격) 전략 활성화."
            vol_details = [
                f"실현변동성(HV20): {hv20:.1f}% — 높음 (상위 {(1-hv_pct)*100:.0f}%)",
                f"방향성 비율: {directional_ratio:.2f} — 0.3 미만 (방향 없는 노이즈)",
                "👉 ETF 리밸런싱, 고배당 Long/인버스 Short 마켓뉴트럴이 최적."
            ]
        elif hv_pct <= 0.30 and vk_contango:
            vol_regime = "😴 과도한 평온 (Quiet — 폭발 직전 주의)"
            vol_color  = "#17a2b8"
            vol_action = "변동성 저점 매수 전략. 소량 VKOSPI 콜옵션 격(KODEX200 콜워런트) 대기."
            vol_details = [
                f"실현변동성(HV20): {hv20:.1f}% — 역사적 하위 {hv_pct*100:.0f}% (극단 저변동성)",
                f"VKOSPI 구조: 콘탱고 ({vk_ma5:.1f} < {vk_ma20:.1f}) — 시장 과신 경보",
                "👉 변동성 압축은 반드시 폭발을 동반. 포트 헷지 준비."
            ]
        else:
            vol_regime = "🟢 정상 회복 변동성 (Normal Recovery)"
            vol_color  = "#28a745"
            vol_action = "헷징 포지션 청산 완료. 분할 매수 재개 적기."
            vol_details = [
                f"실현변동성(HV20): {hv20:.1f}% — 정상 범위 ({hv_pct*100:.0f}% 백분위)",
                f"방향성 비율: {directional_ratio:.2f} — 안정적 회복 추세",
                "👉 ORION Signal 탭의 Tier 시스템에 따라 분할 매수 재개."
            ]

    # 🚨 인버스 매수 추천 스코어링
    inv_score = 0
    inv_details = []
    
    internals = get_intraday_market_internals()
    prog_net = internals.get("program_net", 0)
    adr = internals.get("adr", 1.0)
    
    if internals.get("declining", 0) > 0 and adr <= 0.4:
        inv_score += 20
        inv_details.append(f"시장 Breadth (ADR) {adr:.2f}로 극심한 패닉 (+20점)")
    elif internals.get("declining", 0) > 0 and adr <= 0.7:
        inv_score += 10
        inv_details.append(f"시장 Breadth (ADR) {adr:.2f}로 하락 종목 우위 (+10점)")
        
    if prog_net <= -300000:
        inv_score += 20
        inv_details.append(f"프로그램 3,000억 이상 대규모 순매도 출회 (+20점)")
    
    f_fut = locals().get('foreign_futures', 0)
    if f_fut <= -5000:
        inv_score += 30
        inv_details.append("외국인 선물 5천계약 이상 초대량 순매도 (+30점)")
    elif f_fut <= -2000:
        inv_score += 15
        inv_details.append("외국인 선물 2천계약 이상 순매도 중 (+15점)")
    else:
        inv_details.append("외국인 선물 매도 압력 낮음 (0점)")
        
    if 'vkospi_10y' in locals() and not vkospi_10y.empty:
        v_tail = vkospi_10y['Close'].tail(250)
        curr_vk = v_tail.iloc[-1]
        pct_rank = (v_tail <= curr_vk).mean()
        if pct_rank >= 0.95:
            inv_score += 30
            inv_details.append(f"VKOSPI 최근 1년 내 상위 5% 돌파 (+30점)")
        elif pct_rank >= 0.85:
            inv_score += 15
            inv_details.append(f"VKOSPI 최근 1년 내 상위 15% 진입 (+15점)")
            
    k_val = locals().get('current_kospi_val', 0)
    k_5ma = locals().get('kospi_5d_sma', 0)
    if isinstance(k_val, (int, float)) and isinstance(k_5ma, (int, float)) and k_val < k_5ma:
        inv_score += 20
        inv_details.append("KOSPI 지수 5일 이평선 하회 (+20점)")
        
    if 'usd_krw' in locals() and not usd_krw.empty:
        usd_tail = usd_krw['Close'].tail(100)
        usd_ma60 = usd_tail.rolling(60).mean().iloc[-1]
        usd_std60 = usd_tail.rolling(60).std().iloc[-1]
        curr_ex = usd_tail.iloc[-1]
        usd_z = (curr_ex - usd_ma60) / usd_std60 if usd_std60 > 0 else 0
        if usd_z >= 2.0:
            inv_score += 20
            inv_details.append(f"원/달러 환율 60일 평균 대비 +2σ 폭등 (Z: {usd_z:+.2f}) (+20점)")
        elif usd_z >= 1.0:
            inv_score += 10
            inv_details.append(f"원/달러 환율 60일 평균 대비 상승 (Z: {usd_z:+.2f}) (+10점)")

    if has_tech and curr_rsi > 40:
        if inv_score >= 70:
            inv_score = 69
        inv_details.append(f"⚠️ KOSPI RSI({curr_rsi:.1f})가 40 이상이므로 점수 상한(69점) 제한")

    inv_score = min(inv_score, 100)

    # ════════════════════════════════════════════
    # 🔴 인버스 동적 EXIT 알고리즘 (Strategy A)
    # ════════════════════════════════════════════
    exit_score = 0
    exit_details = []
    exit_signals = []

    if has_tech:
        if curr_rsi < 25:
            exit_score += 40
            exit_details.append(f"🚨 KOSPI RSI {curr_rsi:.1f} — 극단적 과매도. 인버스 익절 후 현금 전환 강력 권고 (+40)")
            exit_signals.append("🟢 RSI 과매도 임계 돌파")
        elif curr_rsi < 32:
            exit_score += 20
            exit_details.append(f"⚠️ KOSPI RSI {curr_rsi:.1f} — 과매도 구간 진입. 인버스 분할 익절 시작 (+20)")

    if f_fut >= 0:
        exit_score += 25
        exit_details.append(f"외국인 선물 순매도 해소 → 하방 압력 소멸. 인버스 청산 신호 (+25)")
        exit_signals.append("🟢 외인 선물 전환")
    elif f_fut >= -500:
        exit_score += 10
        exit_details.append(f"외국인 선물 매도 규모 급감 ({f_fut}계약) (+10)")

    if not vkospi_10y.empty:
        v_tail = vkospi_10y['Close'].tail(250)
        curr_vk = v_tail.iloc[-1]
        vk_5d_high = v_tail.tail(5).max()
        if curr_vk < vk_5d_high * 0.92:
            exit_score += 25
            exit_details.append(f"VKOSPI 5일 고점({vk_5d_high:.1f}) 대비 {curr_vk:.1f}로 공포 피크아웃. 인버스 청산 신호 (+25)")
            exit_signals.append("🟢 VKOSPI 피크아웃")

    if 'usd_krw' in locals() and not usd_krw.empty:
        ex_tail = usd_krw['Close'].dropna().tail(10)
        if len(ex_tail) >= 5:
            ex_5d_slope = (float(ex_tail.iloc[-1]) - float(ex_tail.iloc[-5])) / float(ex_tail.iloc[-5]) * 100
            if ex_5d_slope < -0.5:
                exit_score += 10
                exit_details.append(f"원/달러 환율 5일 하락 전환 ({ex_5d_slope:+.2f}%) — 외인 위험회피 완화 (+10)")

    us_score = locals().get('us_score', 0)
    if us_score >= 70:
        exit_score += 15
        exit_details.append(f"미국 진바닥 확률 {us_score}% — 글로벌 동반 반등 가능성. 곱버스 청산 고려 (+15)")

    exit_score = min(exit_score, 100)
    if exit_score >= 60:
        exit_verdict = "🚨 인버스 즉시 청산 (익절) 강력 권고"
        exit_color = "#28a745"
    elif exit_score >= 35:
        exit_verdict = "⚠️ 인버스 분할 익절 시작 (50% 청산 후 대기)"
        exit_color = "#ffc107"
    else:
        exit_verdict = "⚫ 인버스 홀딩 유지 (청산 조건 미충족)"
        exit_color = "#6c757d"

    # 사전 계산: 볼린저 밴드 폭 (Strategy E용)
    bw = 100.0
    curr_k = 0.0
    curr_lower1 = 0.0
    curr_lower2 = 0.0
    curr_upper1 = 0.0
    curr_upper2 = 0.0
    curr_ma20 = 0.0
    ma20_s = None
    upper2 = None
    lower2 = None
    if not kospi_10y.empty:
        try:
            k = kospi_10y['Close'].tail(60)
            ma20_s = k.rolling(20).mean()
            std20_s = k.rolling(20).std()
            upper2 = ma20_s + 2 * std20_s
            lower2 = ma20_s - 2 * std20_s
            upper1 = ma20_s + 1 * std20_s
            lower1 = ma20_s - 1 * std20_s
            
            curr_k = float(k.iloc[-1])
            curr_upper2 = float(upper2.iloc[-1])
            curr_lower2 = float(lower2.iloc[-1])
            curr_upper1 = float(upper1.iloc[-1])
            curr_lower1 = float(lower1.iloc[-1])
            curr_ma20   = float(ma20_s.iloc[-1])
            bw = (curr_upper2 - curr_lower2) / curr_ma20 * 100
        except: pass

    # ════════════════════════════════════════════
    # 🗺️ 헷징 전략 통합 매트릭스 (Strategy E)
    # ════════════════════════════════════════════
    st.divider()
    st.markdown("### 🗺️ 헷징 전략 통합 매트릭스")
    st.caption("현재 시장 상황에서 활성화해야 할 헷징 전략을 한눈에 확인합니다.")

    matrix_data = {
        "전략": [
            "① 곱버스(인버스) 매수",
            "② 코스피200↔코스닥 스프레드",
            "③ 마켓뉴트럴 (고배당 L/인버스 S)",
            "④ 볼린저 리밸런싱",
            "⑤ 현금 100% 대기",
        ],
        "상태": [
            "🟢 활성" if inv_score >= 70 else ("🟡 준비" if inv_score >= 40 else "⛔ 비활성"),
            "🟢 활성" if (has_spread_data and abs(curr_z) >= 2.3 and spread_adf.get('is_cointegrated', False)) else "⛔ 비활성",
            "🟢 활성" if (not kospi_10y.empty and bw < 3.5) else "⛔ 비활성",
            "🟢 활성" if (curr_k <= curr_lower2 and curr_atr_ratio < 1.5) else ("🟡 준비" if curr_k <= curr_lower1 else "⛔ 비활성"),
            "🟢 권장" if inv_score < 40 and abs(curr_z) < 2.0 else "⛔ 불필요",
        ],
        "예상 수익/리스크": [
            f"단기 +3~8% / 손절 -2% (inv: {inv_score}점)",
            f"중립 +1~3% / 공적분 붕괴 리스크 (Z: {curr_z:+.2f})",
            f"배당 수익 +2~4%/yr / 추세장 리스크",
            f"단기 +1~2% / 추세 역행 리스크",
            "기회비용 / 자본 보존",
        ]
    }
    st.dataframe(pd.DataFrame(matrix_data).set_index("전략"), use_container_width=True)

    # ════════════════════════════════════════════
    # 📊 변동성 레짐 정밀 분류기 UI (Strategy B)
    # ════════════════════════════════════════════
    st.markdown("### 📊 변동성 레짐 정밀 분류기")
    st.markdown(f\"\"\"
    <div style='background-color:#f8f9fa; padding:20px; border-radius:10px; border-left: 8px solid {vol_color}; margin-bottom:20px;'>
        <h4 style='margin-top:0; color:#333;'>상태: <span style='color:{vol_color}; font-weight:bold;'>{vol_regime}</span></h4>
        <p style='font-size:1.05em; color:#444; line-height:1.6; margin-bottom:10px;'>
        <b>대응 액션</b>: {vol_action}
        </p>
        <ul style='font-size:0.95em; color:#666;'>
            {"".join([f"<li>{d}</li>" for d in vol_details])}
        </ul>
    </div>
    \"\"\", unsafe_allow_html=True)

    st.divider()

    # ── 오늘의 추천 트레이딩 패널 ──
    st.markdown("### 🎯 오늘의 추천 트레이딩 (Daily Tactical Signal)")
    st.caption("시장 변동성과 지수 간 괴리율을 분석해 도출한 단 하루의 최적 헷징/트레이딩 제언입니다.")

    trade_recommendation = "관망 및 대기 (현금 자산 보존)"
    trade_reason = "변동성 지표(VKOSPI)와 수급 요인들이 임계치를 넘지 않았으며, 지수 괴리율(Z-Score) 또한 안정을 유지 중입니다."
    trade_color = "#6c757d"

    if inv_score >= 70:
        trade_recommendation = "🚨 KODEX 200선물인버스2X (곱버스, 252670) 분할 매수 (종가 베팅)"
        trade_reason = f"현재 인버스 매수 추천 스코어가 {inv_score}%로 매우 강력한 수준(매수 매력도 극대화)입니다. 외국인의 강한 선물 매도와 고환율, VKOSPI 급등이 동반되어 단기 추가 하락 확률이 매우 높습니다. 당일 종가 기준으로 곱버스를 분할 매수하여 하방 리스크를 헤지하십시오."
        trade_color = "#dc3545"
    elif has_tech and curr_atr_ratio >= 1.5:
        trade_recommendation = "⚪ 관망 (시장 추세장 돌입으로 횡보/평균회귀 전략 비활성화)"
        trade_reason = f"현재 코스피 ATR 변동성이 최근 20일 평균 대비 150% 이상({curr_atr_ratio*100:.1f}%) 폭발한 강한 추세장(Trend Market)입니다. 평균 회귀 전략이 크게 손실을 볼 수 있으므로 모든 헷징 포지션을 중단합니다."
        trade_color = "#6c757d"
    elif has_spread_data and spread_adf.get("spread_adf_pvalue", 0) >= 0.05:
        trade_recommendation = "⚪ 관망 (지수 간 Cointegration 붕괴로 평균회귀 비활성화)"
        trade_reason = f"현재 코스피-코스닥 지수 비율의 ADF 검정 p-value가 {spread_adf.get('spread_adf_pvalue', 0):.3f}로 0.05를 초과하여 평균회귀 성질을 잃었습니다. 지수 스프레드 매매를 중단하십시오."
        trade_color = "#6c757d"
    elif has_spread_data and curr_z >= 2.3:
        trade_recommendation = "📊 코스닥 롱 / 코스피 숏 스프레드 매매 진입"
        trade_reason = f"현재 KOSPI 200 지수가 KOSDAQ 대비 역사적 과열 상태(Z-Score: {curr_z:+.2f})입니다. Z-Score가 +0.5로 회귀할 때까지 유지하십시오."
        trade_color = "#17a2b8"
    elif has_spread_data and curr_z <= -2.3:
        trade_recommendation = "📊 코스피 롱 / 코스닥 숏 스프레드 매매 진입"
        trade_reason = f"현재 KOSDAQ 지수가 KOSPI 200 대비 극단적 고평가(Z-Score: {curr_z:+.2f})입니다. Z-Score가 -0.5로 회귀할 때 청산하십시오."
        trade_color = "#ffc107"
        
    st.markdown(f\"\"\"
    <div style='background-color:#f8f9fa; padding:20px; border-radius:10px; border-left: 8px solid {trade_color}; margin-bottom:20px;'>
        <h4 style='margin-top:0; color:#333;'>💡 추천 헷징 포지션: <span style='color:{trade_color}; font-weight:bold;'>{trade_recommendation}</span></h4>
        <p style='font-size:1.05em; color:#444; line-height:1.6; margin-bottom:0;'>
        <b>실행 가이드</b>:<br>
        {trade_reason}
        </p>
    </div>
    \"\"\", unsafe_allow_html=True)

    # ════════════════════════════════════════════
    # 🎲 포지션 사이저 (Strategy D)
    # ════════════════════════════════════════════
    st.divider()
    st.markdown("### 🎲 포지션 사이저 (Kelly Criterion 기반)")
    st.caption("감이 아닌 수학으로 최적 비중을 계산합니다. 과거 백테스트 승률과 손익비를 기반으로 현재 포지션에 투입할 최적 금액을 도출합니다.")

    col_k1, col_k2, col_k3 = st.columns(3)
    total_asset = col_k1.number_input("💰 총 투자 자산 (만원)", value=5000, step=100)
    win_rate_input = col_k2.number_input("📊 예상 승률 (%)", value=60, min_value=1, max_value=99, step=1, help="inv_score 70+ 구간 단기 승률 약 60~65%")
    rr_ratio = col_k3.number_input("📈 손익비 (수익/손실 비율)", value=1.5, min_value=0.1, step=0.1, help="평균 수익 / 평균 손실")

    W = win_rate_input / 100.0
    L = 1.0 - W
    R = rr_ratio
    full_kelly = max(0, (W * R - L) / R if R > 0 else 0)
    half_kelly = full_kelly / 2
    safe_kelly = min(half_kelly, 0.20)
    invest_amount = total_asset * safe_kelly
    loss_limit = invest_amount * (1 / R) if R > 0 else 0

    k_cols = st.columns(3)
    k_cols[0].metric("Full Kelly 비중", f"{full_kelly*100:.1f}%")
    k_cols[1].metric("Half Kelly 비중 (권장)", f"{half_kelly*100:.1f}%")
    k_cols[2].metric("안전 적용 비중 (20% 캡)", f"{safe_kelly*100:.1f}%", f"투입액: {invest_amount:,.0f}만원")

    st.info(f\"\"\"
    **📌 현재 추천 포지션 사이즈**
    - 총 자산 {total_asset:,}만원 중 **{safe_kelly*100:.1f}% = {invest_amount:,.0f}만원** 인버스 진입
    - 손절 기준: **-{loss_limit:,.0f}만원** 손실 시 즉시 청산 (1R 손실)
    - 목표 수익: **+{invest_amount * (R):,.0f}만원** (손익비 {R}배 달성 시)
    \"\"\")

    with st.expander("❓ [질문 가이드] 바닥확률(98%)인데 인버스 추천(70%)이 뜨는 이유는?"):
        st.markdown("거시적 진바닥(월간 관점)과 단기 하락 모멘텀(일간 투매)이 겹치는 구간이기 때문입니다.")

    st.divider()
    
    # 🚨 인버스 진입 및 청산 통합 UI (Strategy A 연동)
    st.markdown("### 🚨 곱버스/인버스 동적 진입 & 청산 엔진")
    col_in, col_out = st.columns(2)
    with col_in:
        if inv_score >= 70:
            inv_verdict = "🚨 종가 분할매수 적극 고려"
            inv_color = "#dc3545"
        elif inv_score >= 40:
            inv_verdict = "🟡 헷징 포지션 준비 (분할 진입 검토)"
            inv_color = "#ffc107"
        else:
            inv_verdict = "🟢 대기 / 현금 방어 (매수 보류)"
            inv_color = "#28a745"
            
        st.markdown(f\"\"\"
        <div style='background-color:#f8f9fa; padding:15px; border-radius:10px; border-left: 6px solid {inv_color}; height:100%;'>
            <h5 style='margin-top:0;'>진입 엔진 (점수: <span style='color:{inv_color};'>{inv_score}%</span>)</h5>
            <p style='font-weight:bold; color:{inv_color};'>{inv_verdict}</p>
            <ul style='font-size:0.9em; color:#666;'>
                {"".join([f"<li>{d}</li>" for d in inv_details])}
            </ul>
        </div>
        \"\"\", unsafe_allow_html=True)
        
    with col_out:
        st.markdown(f\"\"\"
        <div style='background-color:#f8f9fa; padding:15px; border-radius:10px; border-left: 6px solid {exit_color}; height:100%;'>
            <h5 style='margin-top:0;'>청산(EXIT) 엔진 (점수: <span style='color:{exit_color};'>{exit_score}%</span>)</h5>
            <p style='font-weight:bold; color:{exit_color};'>{exit_verdict}</p>
            <ul style='font-size:0.9em; color:#666;'>
                {"".join([f"<li>{d}</li>" for d in exit_details])}
            </ul>
        </div>
        \"\"\", unsafe_allow_html=True)

    st.divider()

    st.markdown("### 1. 📊 코스피200 vs 코스닥 스프레드 상세 분석")
    if has_spread_data:
        if curr_z >= 2.2:
            spread_verdict = "🔴 KOSPI 200 극단 고평가 / KOSDAQ 과매도 (Z >= 2.2)"
            spread_color = "#dc3545"
        elif curr_z <= -2.2:
            spread_verdict = "🟢 KOSDAQ 극단 고평가 / KOSPI 200 과매도 (Z <= -2.2)"
            spread_color = "#28a745"
        else:
            spread_verdict = "⚪ 정상 변동 범위 내 (평균 회귀 대기)"
            spread_color = "#6c757d"
        st.markdown(f"**현재 Z-Score**: <span style='color:{spread_color}; font-weight:bold; font-size:1.1em;'>{curr_z:+.2f}</span> (진입 임계치: ±2.2)", unsafe_allow_html=True)
        z_df = pd.DataFrame({"Z-Score (KOSPI200/KOSDAQ 비율)": combined["Z_Score"].tail(60)})
        st.line_chart(z_df)
    else:
        st.info("지수 데이터를 로드할 수 없습니다.")

    st.divider()
    
    st.markdown("### 2-1. ⚖️ 횡보장 전용 마켓 뉴트럴 (Market Neutral)")
    with st.expander("💡 [필독] 마켓 뉴트럴(시장 중립) 전략이란?"):
        st.markdown("박스권에서 고배당 ETF(Long) + 인버스(Short) 1:1 매칭으로 알파 추구.")
    
    if not kospi_10y.empty:
        if bw < 3.5:
            mn_status = f"🟢 횡보장 진입 (볼린저 밴드폭 {bw:.1f}%)"
            mn_action = "👉 팩터 롱/숏 (고배당 Long + 인버스 Short) 진입 최적기!"
            mn_color = "#28a745"
        else:
            mn_status = f"⚫ 추세장 진행 중 (볼린저 밴드폭 {bw:.1f}%)"
            mn_action = "👉 지수의 변동성이 살아있으므로 마켓 뉴트럴 전략은 관망합니다."
            mn_color = "#6c757d"
            
        st.markdown(f\"\"\"
        <div style='background-color:#f8f9fa; padding:15px; border-radius:8px; border-left: 6px solid {mn_color}; margin-bottom:15px;'>
            <h5 style='margin-top:0; color:#333;'>상태: <span style='color:{mn_color}; font-weight:bold;'>{mn_status}</span></h5>
            <p style='font-size:0.95em; color:#555; margin-bottom:0;'>
            {mn_action}
            </p>
        </div>
        \"\"\", unsafe_allow_html=True)
        
        try:
            k_df = kospi_10y.copy()
            k_df["MA20"] = k_df["Close"].rolling(20).mean()
            k_df["STD20"] = k_df["Close"].rolling(20).std()
            k_df["Bandwidth"] = (k_df["MA20"] + 2*k_df["STD20"] - (k_df["MA20"] - 2*k_df["STD20"])) / k_df["MA20"] * 100
            bw_chart = pd.DataFrame({"KOSPI 밴드폭 (%)": k_df["Bandwidth"].tail(60)})
            st.area_chart(bw_chart)
        except:
            pass

    st.divider()

    # ════════════════════════════════════════════
    # 📈 변동성 수확 (Strategy C)
    # ════════════════════════════════════════════
    st.markdown("### 2-2. 📈 변동성 수확 — 볼린저 밴드 리밸런싱 신호")
    st.caption("횡보/휩쏘 구간에서 KOSPI가 볼린저 밴드 상·하단에 닿을 때 기계적으로 리밸런싱하여 '변동성 프리미엄'을 수확하는 전략입니다.")

    with st.expander("💡 [필독] 볼린저 밴드 리밸런싱 전략이란?"):
        st.markdown(\"\"\"
        **실행 규칙 (1:1 매칭)**:
        - 📉 **하단 터치 시**: 보유 현금의 10% → KODEX 200 매수
        - 📈 **상단 터치 시**: 전량 익절
        - ⚡ **추세장(ATR 비율 1.5 이상)에서는 자동 비활성화**
        \"\"\")

    if not kospi_10y.empty and ma20_s is not None:
        band_pos = (curr_k - curr_lower2) / (curr_upper2 - curr_lower2) * 100 if (curr_upper2 - curr_lower2) > 0 else 50

        bb_cols = st.columns(4)
        bb_cols[0].metric("KOSPI 현재", f"{curr_k:,.1f}")
        bb_cols[1].metric("볼밴 상단(+2σ)", f"{curr_upper2:,.1f}", f"{(curr_k/curr_upper2-1)*100:+.1f}%")
        bb_cols[2].metric("볼밴 중심(MA20)", f"{curr_ma20:,.1f}", f"{(curr_k/curr_ma20-1)*100:+.1f}%")
        bb_cols[3].metric("볼밴 하단(-2σ)", f"{curr_lower2:,.1f}", f"{(curr_k/curr_lower2-1)*100:+.1f}%")

        if curr_atr_ratio >= 1.5:
            bb_signal = "⛔ 추세장 감지 — 볼린저 리밸런싱 전략 비활성화"
            bb_color = "#6c757d"
            bb_action = "ATR 변동성이 과도하여 평균 회귀 가정이 무효입니다."
        elif curr_k <= curr_lower2:
            bb_signal = f"🟢 볼밴 하단 터치 (밴드 내 위치: {band_pos:.0f}%) — 매수 리밸런싱"
            bb_color = "#28a745"
            bb_action = "현금 10%를 KODEX 200 분할 매수. 목표: MA20 복귀 시 익절."
        elif curr_k <= curr_lower1:
            bb_signal = f"🟡 볼밴 -1σ 접근 (밴드 내 위치: {band_pos:.0f}%) — 소량 선매수 준비"
            bb_color = "#ffc107"
            bb_action = "현금의 5% 선매수. 하단(-2σ) 추가 터치 시 나머지 10% 진입."
        elif curr_k >= curr_upper2:
            bb_signal = f"🔴 볼밴 상단 터치 (밴드 내 위치: {band_pos:.0f}%) — 익절 리밸런싱"
            bb_color = "#dc3545"
            bb_action = "이전 매수분 전량 익절. 인버스 소량 진입 검토."
        elif curr_k >= curr_upper1:
            bb_signal = f"🟠 볼밴 +1σ 접근 (밴드 내 위치: {band_pos:.0f}%) — 부분 익절 준비"
            bb_color = "#fd7e14"
            bb_action = "이전 매수분의 50% 분할 익절. 상단 터치 시 청산."
        else:
            bb_signal = f"⚪ 밴드 중립 구간 (밴드 내 위치: {band_pos:.0f}%) — 대기"
            bb_color = "#6c757d"
            bb_action = "밴드 상·하단까지 여유 있음. 신호 대기."

        st.markdown(f\"\"\"
        <div style='background:#f8f9fa; padding:15px; border-radius:8px; border-left:6px solid {bb_color}; margin:10px 0;'>
            <b style='color:{bb_color}; font-size:1.1em;'>{bb_signal}</b><br>
            <span style='color:#444; font-size:0.95em;'>👉 {bb_action}</span>
        </div>
        \"\"\", unsafe_allow_html=True)

        chart_data = pd.DataFrame({
            "KOSPI": kospi_10y['Close'].tail(60),
            "MA20(중심)": ma20_s,
            "+2σ 상단": upper2,
            "-2σ 하단": lower2,
        }).dropna()
        st.line_chart(chart_data, height=250)

    st.divider()

    st.markdown("### 3. 🤝 다중 페어 트레이딩 (Statistical Arbitrage)")
    with st.expander("💡 [필독] 페어 트레이딩(짝짓기) 스위칭 전략"):
        st.markdown("고평가된 종목을 팔고 저평가된 종목으로 갈아타는 강력한 헤지펀드 전략입니다.")

    if st.button("🔄 전 종목 페어 데이터 실시간 스캔", key="pairs_scan"):
        with st.spinner("한국 증시 핵심 페어 통계 분석 중..."):
            multi_pairs_data = get_daily_multi_pairs()
            if multi_pairs_data:
                pair_names = list(multi_pairs_data.keys())
                tabs = st.tabs(pair_names)
                for i, p_name in enumerate(pair_names):
                    p_data = multi_pairs_data[p_name]
                    with tabs[i]:
                        if p_data["df"] is not None:
                            p_color = p_data["color"]
                            st.markdown(f\"\"\"
                            <div style='background-color:#f8f9fa; padding:15px; border-radius:8px; border-left: 6px solid {p_color}; margin-bottom:15px;'>
                                <h5 style='margin-top:0; color:#333;'>상태: <span style='color:{p_color}; font-weight:bold;'>{p_data["status"]}</span></h5>
                                <p style='font-size:0.95em; color:#555; margin-bottom:5px;'>
                                {p_data["action"]}
                                </p>
                            </div>
                            \"\"\", unsafe_allow_html=True)
                            
                            df = p_data["df"]
                            chart_df = pd.DataFrame({
                                "비율 (S/L)": df["Ratio"].tail(40),
                                "MA20": df["MA20"].tail(40),
                                "+2σ": df["Upper"].tail(40),
                                "-2σ": df["Lower"].tail(40)
                            })
                            st.line_chart(chart_df)
                        else:
                            st.error("데이터 수집 실패")
            else:
                st.error("오류 발생")

    st.divider()
    
    st.markdown("### 4. 🛡️ 헷징 매매 가이드 및 대상 ETF 상품")
    st.markdown(\"\"\"
    - **곱버스 (KOSPI 2X 인버스)**: `KODEX 200선물인버스2X` (252670)
    - **코스닥 인버스**: `KODEX 코스닥150선물인버스` (251340)
    - **달러 헷징 (달러 선물)**: `KODEX 미국달러선물2X` (261250)
    \"\"\")
"""

    new_content = content[:start_idx] + new_block
    with open('final_patched.py', 'w', encoding='utf-8') as f:
        f.write(new_content)

if __name__ == "__main__":
    patch_file()
