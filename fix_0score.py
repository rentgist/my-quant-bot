import re

with open(r'C:\Users\로컬\Desktop\my-quant-bot\final.py', 'r', encoding='utf-8') as f:
    content = f.read()

old_expander = '''    with st.expander("📊 Step 1: 현재 시장이 진바닥인가? (상세 리포트)", expanded=is_true_bottom):
        vkospi_10y = macro_charts.get("vkospi_10y", pd.DataFrame())
        usd_krw = macro_charts.get("usdkrw_10y", pd.DataFrame())
        kospi_10y = macro_charts.get("kospi_10y", pd.DataFrame())
        bt_kr = run_kr_historical_backtest(kospi_10y, vkospi_10y, usd_krw)
        
        if bt_kr:
            score = bt_kr.get("바닥점수", 0)
            rec_score = bt_kr.get("반등신뢰도", 0)
            danger = bt_kr.get("위험경보", 0)
            
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
            c_c.metric("VKOSPI 위험 경보치", f"{danger}/100", "위험" if danger > 50 else "안전", delta_color="inverse")
        else:
            st.error("매크로 백테스트 데이터를 불러오지 못했습니다.")'''

new_expander = '''    with st.expander("📊 Step 1: 현재 시장이 진바닥인가? (상세 리포트)", expanded=is_true_bottom):
        # Use globally calculated real-time variables from final.py
        score = kr_score
        rec_score = kr_rec_score
        danger = kr_danger
        
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
        c_c.metric("위험 경보치 (환율/파생)", f"{danger} 개", "위험" if danger >= 3 else "안전", delta_color="inverse")'''

content = content.replace(old_expander, new_expander)

with open(r'C:\Users\로컬\Desktop\my-quant-bot\final.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Expander fixed to use global variables.")
