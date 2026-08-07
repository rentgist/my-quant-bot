import sys

with open('final.py', 'r', encoding='utf-8') as f:
    content = f.read()

target = '''        # 수동 입력 폼
        f_col1, f_col2 = st.columns(2)
        with f_col1:
            foreign_futures = st.number_input("① 외국인 선물 순매수 (계약)", step=100, key="sniper_futures", on_change=sync_futures_sniper)
        with f_col2:
            oi_trend = st.radio("② 선물 미결제약정", ["증가 추세", "감소/정체"], index=1)
            
        kr_flow_score, kr_flow_status, kr_flow_details = calculate_cashflow_signal(foreign_futures, oi_trend, rsp_change_pct, kospi_10y)
        
        st.markdown(f"**상태:** {kr_flow_status}")
        for icon, msg in kr_flow_details:
            st.write(f"{icon} {msg}")

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("#### Step 3: 🎯 통합 판정 (Action Plan)")

    kospi_above_ma20 = False
    if not kospi_10y.empty and len(kospi_10y) >= 20:
        try:
            kospi_close = float(kospi_10y["Close"].iloc[-1])
            kospi_ma20 = float(kospi_10y["Close"].rolling(20).mean().iloc[-1])
            kospi_above_ma20 = kospi_close >= kospi_ma20
        except (KeyError, TypeError, ValueError):
            kospi_above_ma20 = False

    regime, action, r_color = calculate_regime_classification(
        kr_macro_score,
        kr_flow_score,
        kospi_above_ma20,
    )'''

replacement = '''        # 수동 입력 폼
        f_col1, f_col2 = st.columns(2)
        with f_col1:
            foreign_futures = st.number_input("① 외국인 선물 순매수 (계약)", step=100, key="sniper_futures", on_change=sync_futures_sniper)
        with f_col2:
            oi_trend = st.radio("② 선물 미결제약정", ["증가 추세", "감소/정체"], index=1)
            
        st.markdown("<br>", unsafe_allow_html=True)
        save_col1, save_col2 = st.columns([2, 1])
        with save_col1:
            st.info("💡 장중에는 체크를 풀고 자유롭게 테스트하세요. 장 마감 후 최종 확정 시에만 체크하세요.")
            save_regime = st.checkbox("✅ 오늘 장마감 결과로 확정 및 영구 저장 (GitHub 연동)", value=False)
        with save_col2:
            with st.expander("⚙️ 강제 오버라이드"):
                wdo = st.number_input("수동 경고일수 (-1: 자동)", min_value=-1, max_value=5, value=-1, step=1)
                override_val = wdo if wdo != -1 else None

        kr_flow_score, kr_flow_status, kr_flow_details = calculate_cashflow_signal(foreign_futures, oi_trend, rsp_change_pct, kospi_10y)
        
        st.markdown(f"**상태:** {kr_flow_status}")
        for icon, msg in kr_flow_details:
            st.write(f"{icon} {msg}")

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("#### Step 3: 🎯 통합 판정 (Action Plan)")

    kospi_above_ma20 = False
    if not kospi_10y.empty and len(kospi_10y) >= 20:
        try:
            kospi_close = float(kospi_10y["Close"].iloc[-1])
            kospi_ma20 = float(kospi_10y["Close"].rolling(20).mean().iloc[-1])
            kospi_above_ma20 = kospi_close >= kospi_ma20
        except (KeyError, TypeError, ValueError):
            kospi_above_ma20 = False

    regime, action, r_color = calculate_regime_classification(
        kr_macro_score,
        kr_flow_score,
        kospi_above_ma20,
        warning_days_override=override_val,
        save_state=save_regime,
    )'''

if target in content:
    new_content = content.replace(target, replacement)
    with open('final.py', 'w', encoding='utf-8') as f:
        f.write(new_content)
    print("Success")
else:
    print("Target not found.")