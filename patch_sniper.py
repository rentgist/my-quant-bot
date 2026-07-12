with open(r'C:\Users\로컬\Desktop\my-quant-bot\final.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Replace the tab definitions
old_tabs = '''tab1, tab2, tab4, tab3, tab_port, tab5, tab_risk = st.tabs([
    "📊 실시간 포트폴리오",
    "🌐 매크로 & F&G Index",
    "🚀 오늘의 텐배거 레이더",
    "🤖 AI 참모 리포트",
    "💼 내 포트폴리오 장투 전략",
    "📖 11원칙 매매 가이드라인",
    "🌋 리스크 등급 가이드"
])'''

new_tabs = '''tab_sniper, tab1, tab2, tab4, tab3, tab_port, tab5, tab_risk = st.tabs([
    "🎯 14:50 스나이퍼 타점",
    "📊 실시간 포트폴리오",
    "🌐 매크로 & F&G Index",
    "🚀 오늘의 텐배거 레이더",
    "🤖 AI 참모 리포트",
    "💼 내 포트폴리오 장투 전략",
    "📖 11원칙 매매 가이드라인",
    "🌋 리스크 등급 가이드"
])'''

if old_tabs in content:
    content = content.replace(old_tabs, new_tabs)
else:
    print("Could not find old_tabs")

# 2. Add the tab_sniper content right before tab1 content
sniper_content = '''
# -------------------------------------------------------------
# TAB 0: 🎯 14:50 스나이퍼 타점
# -------------------------------------------------------------
with tab_sniper:
    st.subheader("🎯 11원칙 퀀트 머신 통제실 (v26.5.1)")
    st.caption("최종 업데이트: 현재 (데이터 60초 주기 자동 갱신)")

    @st.cache_data(ttl=60)
    def get_sniper_market_data():
        try:
            import yfinance as yf
            # KOSPI 데이터
            kospi = yf.Ticker('^KS11').history(period='10d')
            kospi_current = float(kospi['Close'].iloc[-1])
            kospi_5day = float(kospi['Close'].iloc[-5:].mean())
            
            # 삼성전자 데이터
            samsung = yf.Ticker('005930.KS').history(period='1d')
            samsung_current = float(samsung['Close'].iloc[-1])
            
            return kospi_current, kospi_5day, samsung_current
        except Exception as e:
            return 0, 0, 0

    kospi_current, kospi_5day, samsung_current = get_sniper_market_data()

    if kospi_current == 0:
        st.error("⚠️ 데이터를 불러오는 중 오류가 발생했습니다. HTS 가격을 수동으로 확인해주세요.")
    else:
        # === 구역 A: 자동 연산 ===
        st.subheader("⚙️ 구역 A: 자동 연산 (실시간 API)")
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("##### 📈 KOSPI 추세 판독")
            kospi_check = kospi_current > (kospi_5day * 1.002)
            
            c1, c2 = st.columns(2)
            c1.metric("KOSPI 현재가", f"{kospi_current:,.2f} p")
            c2.metric("KOSPI 5일선", f"{kospi_5day:,.2f} p")
            
            if kospi_check:
                st.success("✅ 5일선 돌파 (+0.2% 버퍼 위 안착)")
            else:
                st.error("❌ 5일선 미돌파")
                
        with col2:
            st.markdown("##### 💰 삼성전자 1차 앵커 & 보험료")
            anchor = 62100
            insurance = (samsung_current / anchor - 1) * 100 if samsung_current > 0 else 0
            insurance_check = insurance <= 6.0
            
            c3, c4 = st.columns(2)
            c3.metric("삼성전자 현재가", f"{samsung_current:,.0f}원")
            c4.metric("보험료", f"{insurance:.2f}%")
            
            if insurance_check:
                st.success(f"✅ 6% 이내 ({insurance:.2f}%) 방어 완료")
            else:
                st.error(f"❌ 6% 초과 ({insurance:.2f}%) - 오버슈팅")
        
        # === 구역 B: 수동 입력 ===
        st.divider()
        st.subheader("⌨️ 구역 B: HTS 사령관 수동 입력 (오후 2:50)")
        
        col3, col4, col5 = st.columns(3)
        with col3:
            foreign_futures = st.number_input("① 외국인 선물 순매수 (계약)", min_value=-100000, value=0, step=100)
        with col4:
            st.write("② 미결제약정 증가 여부")
            oi_increase = st.checkbox("미결제약정이 증가 중입니까?", value=False)
        with col5:
            st.write("③ RSP 상승 여부")
            rsp_rise = st.checkbox("RSP +2.5% 이상입니까?", value=False)
            
        # === 구역 C: 자동 판정 ===
        st.divider()
        st.subheader("🚨 구역 C: 알고리즘 최종 판정")
        
        conditions = {
            "① 외국인 선물 +5,000계약 이상": foreign_futures >= 5000,
            "② 미결제약정 당일 증가 (숏커버링 방지)": oi_increase,
            "③ RSP +2.5% 이상 (시장 폭 회복)": rsp_rise,
            "④ KOSPI 5일선 완벽 지지 (+0.2% 버퍼)": kospi_check,
            "⑤ 진입 보험료 6% 이내 (안전마진)": insurance_check
        }
        
        passed = sum(conditions.values())
        total = len(conditions)
        
        st.write(f"### 📊 현재 조건 충족률: {passed} / {total}")
        
        for cond, result in conditions.items():
            if result:
                st.success(f"✅ {cond}")
            else:
                st.error(f"❌ {cond}")
                
        if passed == total:
            st.success("""
            # 🟢 매수 승인 (GO!)
            ### ➔ 스나이퍼 예산의 30% 본대 투입을 허가합니다.
            * **타겟:** 삼성전자
            * **방식:** 시장가 또는 최우선 지정가 매수
            * **집행 시간:** 지금 즉시 (장 마감 직전)
            """)
            st.balloons()
        else:
            st.error("""
            # 🔴 매수 보류 (PASS)
            ### ➔ 조건 미달. 남은 현금 90%를 굳건히 사수하십시오.
            * 가짜 반등(Bull Trap)의 위험이 도사리고 있습니다.
            * HTS를 종료하고 다음 거래일 오후 2시 50분에 다시 뵙겠습니다.
            """)

# -------------------------------------------------------------
# TAB 1: 실시간 포트폴리오
# -------------------------------------------------------------
'''

content = content.replace('''# -------------------------------------------------------------
# TAB 1: 실시간 포트폴리오
# -------------------------------------------------------------''', sniper_content)

with open(r'C:\Users\로컬\Desktop\my-quant-bot\final.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('Patch applied')
