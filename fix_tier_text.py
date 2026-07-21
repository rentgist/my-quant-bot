with open(r'C:\Users\로컬\Desktop\my-quant-bot\final.py', 'r', encoding='utf-8') as f:
    content = f.read()

old_block = '''    with st.expander("📊 Step 1: 현재 시장이 진바닥인가? (상세 리포트)", expanded=is_true_bottom):
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
            action = "🛑 현금 관망. 현재는 추세 추종장이며 낙폭 과대 매수 시점이 아님."'''

new_block = '''    with st.expander("📊 Step 1: 현재 시장이 진바닥인가? (상세 리포트)", expanded=is_true_bottom):
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
            action = "✅ 평온한 추세장. 무리한 매수 금지. 예산의 30~40% 내에서 우량주 GTC(지정가) 적립만 유지."'''

content = content.replace(old_block, new_block)

with open(r'C:\Users\로컬\Desktop\my-quant-bot\final.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Text updated successfully.")
