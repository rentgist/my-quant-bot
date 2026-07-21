import re

with open(r'C:\Users\로컬\Desktop\my-quant-bot\final.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Update the Tier Expander text again to pull real data instead of static text
# We need to display the actual Backtest variables (score, rec_score, danger)
# Since the backtest happens in the background via run_historical_backtest, 
# we should fetch the US backtest results at the top of tab_sniper and display them.

old_expander_start = '''    with st.expander("📊 Step 1: 현재 시장이 진바닥인가? (상세 리포트)", expanded=is_true_bottom):
        if cnn_score <= 25 or kospi_drawdown <= -15.0:
            prob = 90
            tier = "Tier 3 (극단 패닉 - 투매 극점)"
            action = "🚨 낙폭 과대 진바닥. 스나이퍼 예산의 10%를 '선발대'로 투입하여 정찰 매수."
        elif cnn_score <= 45 or kospi_drawdown <= -10.0:
            prob = 50
            tier = "Tier 2 (추세 전환 - 반등 확인)"
            action = "🎯 반등 신뢰도(Step 2) 통과 시, 예산의 30~50%를 '본대 불타기'로 강하게 투입 (실질적 풀매수 타이밍)."
        else:
            prob = 10
            tier = "Tier 1 (평상시 - 정상 적립)"
            action = "✅ 평온한 추세장. 무리한 매수 금지. 예산의 30~40% 내에서 우량주 GTC(지정가) 적립만 유지."
            
        st.markdown(f"#### 🎯 현재 진바닥 확률: **{prob}%**")
        st.markdown(f"#### 🚩 현재 국면: **{tier}**")
        st.markdown(f"#### 🛡️ 액션 지침: **{action}**")'''

new_expander_start = '''    with st.expander("📊 Step 1: 현재 시장이 진바닥인가? (상세 리포트)", expanded=is_true_bottom):
        vix_10y = macro_charts.get("vix_10y", pd.DataFrame())
        vix3m_10y = macro_charts.get("vix3m_10y", pd.DataFrame())
        spy_10y = macro_charts.get("spy_10y", pd.DataFrame())
        bt_us = run_historical_backtest(spy_10y, vix_10y, vix3m_10y)
        
        if bt_us:
            score = bt_us.get("바닥점수", 0)
            rec_score = bt_us.get("반등신뢰도", 0)
            danger = bt_us.get("위험경보", 0)
            
            # Use the actual Tier logic from get_strategic_advice
            if score >= 80:
                tier_label = "Tier 3 (극단적 패닉)"
                action = "🚨 낙폭 과대 진바닥 (점수 80점 이상). 스나이퍼 예산의 10%를 '선발대'로 1차 분할 투입. (반등 확인 전)"
                prob = score
            elif score >= 50:
                tier_label = "Tier 2 (추세 전환 / 반등 구간)"
                action = f"🎯 바닥 확인 중 (점수 {score}점). 반등 신뢰도(Step 2~3) 조건 충족 시, 예산의 30~50%를 '본대 불타기'로 강하게 투입."
                prob = score
            else:
                tier_label = "Tier 1 (정상 적립 구간)"
                action = "✅ 평온한 추세장. 무리한 매수 금지. 예산의 30~40% 내에서 우량주 GTC(지정가) 적립만 유지."
                prob = score
                
            st.markdown(f"#### 🎯 매크로 알고리즘 진바닥 확률: **{prob}%**")
            st.markdown(f"#### 🚩 시스템 판독 국면: **{tier_label}**")
            st.markdown(f"#### 🛡️ 액션 지침: **{action}**")
            
            st.markdown("**🔍 매크로 상세 데이터**")
            c_a, c_b, c_c = st.columns(3)
            c_a.metric("알고리즘 바닥 점수", f"{score}/100")
            c_b.metric("매크로 반등 신뢰도", f"{rec_score}/100")
            c_c.metric("VIX 위험 경보치", f"{danger}/100", "위험" if danger > 50 else "안전", delta_color="inverse")
        else:
            st.error("매크로 백테스트 데이터를 불러오지 못했습니다.")
'''

content = content.replace(old_expander_start, new_expander_start)

# 2. Fix the Ticker mapping issue in get_target_stock_data
old_mapping_code = '''            from data_loader import mapping
            actual_ticker = mapping.get(ticker, {}).get('yf_code', ticker)'''

new_mapping_code = '''            try:
                from data_loader import get_krx_mapping_v2
                mapping = get_krx_mapping_v2()
            except ImportError:
                mapping = {}
            actual_ticker = mapping.get(ticker, {}).get('yf_code', ticker)'''

content = content.replace(old_mapping_code, new_mapping_code)

with open(r'C:\Users\로컬\Desktop\my-quant-bot\final.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Expander logic and mapping import fixed.")
