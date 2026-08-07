import os

with open('final.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix final_us_phase
old_phase_code = '''    # 통합 점수에 flow score 반영 (가중치 조절)
    final_us_score = total_score + (us_flow_score * 0.2)
    final_us_phase = "🟢 STRONGBUY" if final_us_score >= 80 else "📈 BUY" if final_us_score >= 60 else "⚠️ CAUTION" if final_us_score >= 40 else "🚨 SELL"'''

new_phase_code = '''    # 통합 점수에 flow score 반영 (가중치 조절)
    final_us_score = total_score + (us_flow_score * 0.2)
    final_us_phase = "CLEAR" if final_us_score >= 60 else "CAUTION" if final_us_score >= 40 else "ALERT"'''

content = content.replace(old_phase_code, new_phase_code)

# Fix ETF flow caption
old_etf = '''    st.markdown("### 🦅 미국 주요 ETF 수급 동향 프록시 리포트")
    us_flow = get_us_flow_report()'''

new_etf = '''    st.markdown("### 🦅 미국 주요 ETF 수급 동향 프록시 리포트")
    st.caption("💡 팁: API 제약으로 인해 미국 ETF 거래량과 종가 등락을 결합해 추산한 **가상 수급 점수(Proxy Score)**입니다. 양수일수록 매수 우위, 음수일수록 매도 우위를 나타냅니다.")
    us_flow = get_us_flow_report()'''

content = content.replace(old_etf, new_etf)

# Fix playbook import
old_playbook = '''    # ── [NEW] Phase별 비중 가이드 박스 ──
    from regime_playbook import get_playbook
    us_playbook = get_playbook(final_us_phase)'''

new_playbook = '''    # ── [NEW] Phase별 비중 가이드 박스 ──
    from regime_playbook import REGIME_POLICIES
    if final_us_phase == "CLEAR":
        us_playbook = REGIME_POLICIES.get("UPTREND", {})
        playbook_strategy = "위험 자산 비중을 확대하고 AI/Tech 주도주의 추세를 추종하십시오."
    elif final_us_phase == "CAUTION":
        us_playbook = REGIME_POLICIES.get("SIDEWAYS", {})
        playbook_strategy = "신규 매수를 자제하고 리밸런싱을 통해 현금을 확보하십시오."
    else:
        us_playbook = REGIME_POLICIES.get("CRASH", {})
        playbook_strategy = "하방 리스크가 큽니다. 단기채(SGOV 등) 및 현금 비중을 대폭 늘리십시오."
'''

content = content.replace(old_playbook, new_playbook)

old_playbook_render = '''    st.info(f"**주식 비중:** {us_playbook.get('Equity', 'N/A')} | **현금 비중:** {us_playbook.get('Cash', 'N/A')} | **헷지 비중:** {us_playbook.get('Hedge', 'N/A')}")
    st.markdown(f"**핵심 전략:** {us_playbook.get('Strategy', 'N/A')}")'''

new_playbook_render = '''    band = us_playbook.get('equity_band', (0.0, 0.0))
    st.info(f"**주식 권장 비중:** {int(band[0]*100)}% ~ {int(band[1]*100)}% | **현금/헷지 비중:** {100 - int(band[1]*100)}% ~ {100 - int(band[0]*100)}%")
    st.markdown(f"**핵심 전략:** {playbook_strategy}")
    st.markdown(f"**행동 지침:** {us_playbook.get('core_strategy', '')}")
    st.markdown(f"**피해야 할 행동:** {us_playbook.get('avoid', '')}")'''

content = content.replace(old_playbook_render, new_playbook_render)

with open('final.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Modified final.py")
