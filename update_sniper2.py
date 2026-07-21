import re

with open(r'C:\Users\로컬\Desktop\my-quant-bot\final.py', 'r', encoding='utf-8') as f:
    content = f.read()

start_idx = content.find("with tab_sniper:")
end_idx = content.find("with tab_radar:")

tab_sniper_code = '''with tab_sniper:
    st.subheader("🎯 11원칙 퀀트 머신 통제실 (v26.5.2)")
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
            return kospi_current, kospi_5day
        except Exception as e:
            return 0, 0

    @st.cache_data(ttl=60)
    def get_target_stock_data(ticker):
        try:
            import yfinance as yf
            import pandas as pd
            import warnings
            warnings.filterwarnings("ignore")
            
            from data_loader import mapping
            actual_ticker = mapping.get(ticker, {}).get('yf_code', ticker)
            
            stock = yf.Ticker(actual_ticker).history(period='30d')
            if stock.empty:
                return 0, 0, 0
                
            current = float(stock['Close'].iloc[-1])
            ma5 = float(stock['Close'].iloc[-5:].mean())
            
            delta = stock['Close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs.iloc[-1]))
            if pd.isna(rsi):
                rsi = 50.0
            
            return current, ma5, rsi
        except Exception as e:
            return 0, 0, 0

    kospi_current, kospi_5day = get_sniper_market_data()

    kospi_df = macro_charts.get("kospi_10y", pd.DataFrame())
    kospi_drawdown = 0.0
    if not kospi_df.empty and len(kospi_df) >= 252:
        kospi_latest = float(kospi_df['Close'].iloc[-1])
        kospi_max_52w = float(kospi_df['Close'].tail(252).max())
        kospi_drawdown = (kospi_latest / kospi_max_52w - 1) * 100
        
    is_true_bottom = (cnn_score <= 25) or (kospi_drawdown <= -15.0)
    
    with st.expander("📊 Step 1: 현재 시장이 진바닥인가? (상세 리포트)", expanded=is_true_bottom):
        if cnn_score <= 15 or kospi_drawdown <= -20.0:
            prob = 99
            tier = "Tier 3 (극단 패닉 - 대폭락)"
            action = "🚨 전 재산 투입 준비. 14시 50분 반등 확인 즉시 풀매수 (스나이퍼 예산 100%)"
        elif cnn_score <= 25 or kospi_drawdown <= -15.0:
            prob = 90
            tier = "Tier 3 (패닉 - 진바닥)"
            action = "🎯 스나이퍼 예산 30% 실전 타격 허가. 반등 확인 즉시 기계적 매수."
        elif cnn_score <= 45 or kospi_drawdown <= -10.0:
            prob = 50
            tier = "Tier 2 (조정장/횡보)"
            action = "⚠️ 보수적 접근. 하락이 진정될 때까지 코어 적립만 유지."
        else:
            prob = 10
            tier = "Tier 1 (평상시/상승장)"
            action = "🛑 현금 관망. 현재는 추세 추종장이며 낙폭 과대 매수 시점이 아님."
            
        st.markdown(f"#### 🎯 현재 진바닥 확률: **{prob}%**")
        st.markdown(f"#### 🚩 현재 국면: **{tier}**")
        st.markdown(f"#### 🛡️ 액션 지침: **{action}**")
        st.divider()
        
        c1, c2 = st.columns(2)
        with c1:
            fg_status = "극단 공포 (폭락 신호)" if cnn_score <= 25 else "공포" if cnn_score <= 45 else "평시"
            st.metric("CNN F&G (현재)", f"{cnn_score:.0f}", fg_status, delta_color="inverse" if cnn_score > 25 else "normal")
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
            st.markdown("##### 💰 타겟 종목 진입 모드")
            entry_mode = st.radio("진입 전략 선택", ["🆕 신규 진입 (안전마진 확인)", "🔥 기존 종목 불타기 (수익금 버퍼)"], horizontal=True)
            target_ticker = st.text_input("타겟 종목명 또는 티커 (예: SK하이닉스 또는 000660.KS)", value="SK하이닉스")
            
            target_check = False
            target_current, target_ma5, target_rsi = get_target_stock_data(target_ticker)
            
            if target_current == 0:
                st.warning("종목 데이터를 불러오는 중이거나 티커가 잘못되었습니다.")
            else:
                if "신규 진입" in entry_mode:
                    is_safe_rsi = target_rsi < 70
                    is_above_ma = target_current > target_ma5
                    target_check = is_safe_rsi and is_above_ma
                    
                    c5, c6 = st.columns(2)
                    c5.metric("현재가", f"{target_current:,.0f}원", f"5일선: {target_ma5:,.0f}원")
                    c6.metric("RSI (14일)", f"{target_rsi:.1f}", "과매수(70) 미만 안전" if is_safe_rsi else "과매수 위험", delta_color="inverse" if not is_safe_rsi else "normal")
                    
                    if target_check:
                        st.success("✅ 신규 진입 안전마진 확인 (5일선 위 & 과매수 아님)")
                    else:
                        st.error("❌ 신규 진입 보류 (5일선 아래 또는 과매수 상태)")
                        
                else:
                    anchor = st.number_input("내 평단가 (또는 1차 앵커)", min_value=1000, value=62100, step=100)
                    insurance = (target_current / anchor - 1) * 100 if anchor > 0 else 0
                    target_check = insurance >= 6.0
                    
                    c5, c6 = st.columns(2)
                    c5.metric("현재가", f"{target_current:,.0f}원")
                    c6.metric("내 수익률 (보험료)", f"{insurance:.2f}%")
                    
                    if target_check:
                        st.success(f"✅ +6% 이상 ({insurance:.2f}%) 수익 버퍼 확인. 불타기 승인.")
                    else:
                        st.error(f"❌ +6% 미만 ({insurance:.2f}%) - 버퍼 부족, 불타기 금지.")
        
        st.divider()
        
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
        
        st.subheader("🚨 Step 4: 최종 판정 (진바닥 + 반등신뢰도)")
        
        conditions = {
            "📈 외국인 선물 +5,000계약 이상": foreign_futures >= 5000,
            "📊 미결제약정 당일 증가 (숏커버링 방지)": oi_increase,
            "📈 RSP +2.5% 이상 (시장 폭넓은 회복)": rsp_rise,
            "📉 KOSPI 5일선 완벽 지지 (+0.2% 버퍼)": kospi_check,
            "🎯 타겟 종목 진입 조건 (안전마진 또는 버퍼)": target_check
        }
        
        passed = sum(conditions.values())
        total = len(conditions)
        
        st.write(f"### 🛡️ 반등 신뢰도 조건 충족: {passed} / {total}")
        
        for cond, result in conditions.items():
            if result:
                st.success(f"✅ {cond}")
            else:
                st.error(f"❌ {cond}")
                
        final_go = is_true_bottom and (passed == total)
        
        if final_go:
            st.success(f"""
            # 🟢 강력 매수 승인 (GO!)
            ### 🎯 진바닥 및 반등 신뢰도 모두 충족. 스나이퍼 예산의 30%를 즉시 투입하십시오.
            * **타겟:** {target_ticker}
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

print("tab_sniper successfully updated with new features.")
