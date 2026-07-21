import re

with open(r'C:\Users\로컬\Desktop\my-quant-bot\final.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Locate the with tab_sniper: block
start_idx = content.find("with tab_sniper:")
end_idx = content.find("with tab_radar:")

tab_sniper_code = '''with tab_sniper:
    st.subheader("🎯 11원칙 퀀트 머신 통제실 (v26.5.1)")
    st.caption("최종 업데이트: 실시간 (데이터 60초 주기 자동 갱신)")

    @st.cache_data(ttl=60)
    def get_sniper_market_data():
        try:
            import yfinance as yf
            import warnings
            warnings.filterwarnings("ignore")
            kospi = yf.Ticker('^KS11').history(period='10d')
            kospi_current = float(kospi['Close'].iloc[-1])
            kospi_5day = float(kospi['Close'].iloc[-5:].mean())
            samsung = yf.Ticker('005930.KS').history(period='1d')
            samsung_current = float(samsung['Close'].iloc[-1])
            return kospi_current, kospi_5day, samsung_current
        except Exception as e:
            return 0, 0, 0

    kospi_current, kospi_5day, samsung_current = get_sniper_market_data()

    # --- Step 1: 진바닥 탐지기 ---
    st.subheader("📊 Step 1: 현재 시장이 진바닥인가?")
    
    kospi_df = macro_charts.get("kospi_10y", pd.DataFrame())
    kospi_drawdown = 0.0
    if not kospi_df.empty and len(kospi_df) >= 252:
        kospi_latest = float(kospi_df['Close'].iloc[-1])
        kospi_max_52w = float(kospi_df['Close'].tail(252).max())
        kospi_drawdown = (kospi_latest / kospi_max_52w - 1) * 100
        
    is_true_bottom = (cnn_fg <= 25) or (kospi_drawdown <= -15.0)
    
    c1, c2 = st.columns(2)
    with c1:
        fg_status = "극단 공포 (폭락 신호)" if cnn_fg <= 25 else "공포" if cnn_fg <= 45 else "평시"
        st.metric("CNN F&G (현재)", f"{cnn_fg:.0f}", fg_status, delta_color="inverse" if cnn_fg > 25 else "normal")
    with c2:
        dd_status = "극단 폭락 (Tier 3)" if kospi_drawdown <= -15.0 else "조정장" if kospi_drawdown <= -10.0 else "평시"
        st.metric("KOSPI 고점 대비 낙폭", f"{kospi_drawdown:.1f}%", dd_status, delta_color="inverse" if kospi_drawdown > -15.0 else "normal")
        
    if is_true_bottom:
        st.warning("✅ 진바닥 확인됨 (극단 패닉 구간 진입)")
    else:
        st.info("⚠️ 현재 진바닥(Tier 3) 구간이 아닙니다. (일반 상승/조정장)")
        
    st.divider()

    if kospi_current == 0:
        st.error("🚨 실시간 데이터를 불러오는 데 실패했습니다. HTS 가격을 수동으로 확인해주세요.")
    else:
        # --- Step 2: 반등 신뢰도 확인 ---
        st.subheader("🎯 Step 2: 반등 신뢰도 확인")
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("##### 📈 KOSPI 추세 판독")
            kospi_check = kospi_current > (kospi_5day * 1.002)
            c3, c4 = st.columns(2)
            c3.metric("KOSPI 현재가", f"{kospi_current:,.2f} p")
            c4.metric("KOSPI 5일선", f"{kospi_5day:,.2f} p")
            if kospi_check:
                st.success("✅ 5일선 돌파 (+0.2% 버퍼 안착)")
            else:
                st.error("❌ 5일선 미돌파")
                
        with col2:
            st.markdown("##### 💰 타겟 종목 & 수익금(보험료) 버퍼")
            anchor = st.number_input("목표 종목 평단가 (또는 1차 앵커)", min_value=1000, value=62100, step=100, help="보유 종목의 평단가 또는 삼성전자 지지선 가격을 입력하세요.")
            insurance = (samsung_current / anchor - 1) * 100 if samsung_current > 0 else 0
            insurance_check = insurance <= 6.0
            c5, c6 = st.columns(2)
            c5.metric("현재가 (예: 삼성)", f"{samsung_current:,.0f}원")
            c6.metric("보험료", f"{insurance:.2f}%")
            if insurance_check:
                st.success(f"✅ 6% 이내 ({insurance:.2f}%) 방어 완료")
            else:
                st.error(f"❌ 6% 초과 ({insurance:.2f}%) - 오버슈팅")
        
        st.divider()
        
        # --- Step 3: HTS 수동 확인 ---
        st.subheader("⌨️ Step 3: HTS 수동 확인 (오후 2:50)")
        col3, col4, col5 = st.columns(3)
        with col3:
            foreign_futures = st.number_input("📈 외국인 선물 순매수(계약)", min_value=-100000, value=0, step=100)
        with col4:
            st.write("📊 미결제약정 증가 여부")
            oi_increase = st.checkbox("미결제약정이 증가 중입니까?", value=False)
        with col5:
            st.write("📈 RSP 상승 여부")
            rsp_rise = st.checkbox("RSP +2.5% 이상입니까?", value=False)
            
        st.divider()
        
        # --- Step 4: 최종 판정 ---
        st.subheader("🚨 Step 4: 최종 판정 (진바닥 + 반등신뢰도)")
        
        conditions = {
            "📈 외국인 선물 +5,000계약 이상": foreign_futures >= 5000,
            "📊 미결제약정 당일 증가 (숏커버링 방지)": oi_increase,
            "📈 RSP +2.5% 이상 (시장 폭넓은 회복)": rsp_rise,
            "📉 KOSPI 5일선 완벽 지지 (+0.2% 버퍼)": kospi_check,
            "💰 진입 보험료 6% 이내 (안전마진)": insurance_check
        }
        
        passed = sum(conditions.values())
        total = len(conditions)
        
        st.write(f"### 🛡️ 반등 신뢰도 조건 충족: {passed} / {total}")
        
        for cond, result in conditions.items():
            if result:
                st.success(f"✅ {cond}")
            else:
                st.error(f"❌ {cond}")
                
        # 최종 GO 조건: 진바닥(Step1) 만족 AND 모든 반등조건(Step2,3) 만족
        final_go = is_true_bottom and (passed == total)
        
        if final_go:
            st.success("""
            # 🟢 강력 매수 승인 (GO!)
            ### 🎯 진바닥 및 반등 신뢰도 모두 충족. 스나이퍼 예산의 30%를 즉시 투입하십시오.
            * **타겟:** 선택한 우량주 또는 삼성전자
            * **방식:** 시장가 또는 최우선지정가 매수
            * **시간:** 지금 즉시 (장 마감 직전)
            """)
            st.balloons()
        else:
            st.error("""
            # 🔴 매수 보류 (PASS)
            ### 🛑 진바닥이 아니거나 반등 신뢰도 조건이 미달되었습니다. 현금을 굳건히 사수하십시오.
            * HTS를 종료하고 다음 거래일 오후 2시 50분에 다시 뵙겠습니다.
            """)

'''

new_content = content[:start_idx] + tab_sniper_code + content[end_idx:]

with open(r'C:\Users\로컬\Desktop\my-quant-bot\final.py', 'w', encoding='utf-8') as f:
    f.write(new_content)

print("tab_sniper updated.")
