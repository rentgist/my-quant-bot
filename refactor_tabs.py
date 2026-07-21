import re

with open(r'C:\Users\로컬\Desktop\my-quant-bot\final.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Replace st.tabs
old_tabs_regex = r"tab_sniper, tab1, tab2, tab4, tab3, tab_port, tab5, tab_risk = st\.tabs\(\[.*?\]\)"
new_tabs = '''tab_sniper, tab_radar, tab_report, tab_port = st.tabs([
    "🎯 14:50 실전 타격",
    "🔍 종목 발굴 & 레이더",
    "🌐 매크로 & 딥 리포트",
    "💼 포트폴리오 & 가이드",
])'''

content = re.sub(old_tabs_regex, new_tabs, content, flags=re.DOTALL)

# 2. Swap tab5 and tab_risk blocks (using basic string manipulation since they are at the end)
lines = content.split('\n')
try:
    idx_tab5 = lines.index('with tab5:')
    idx_tab_risk = lines.index('with tab_risk:')
    
    pre_tab5 = lines[:idx_tab5]
    tab5_block = lines[idx_tab5:idx_tab_risk]
    tab_risk_block = lines[idx_tab_risk:]
    
    # Trim trailing newlines from tab_risk_block if any
    while tab_risk_block and not tab_risk_block[-1].strip():
        tab_risk_block.pop()
    
    # Reassemble: pre -> tab_risk -> tab5
    lines = pre_tab5 + tab_risk_block + [''] + tab5_block + ['']
    content = '\n'.join(lines)
except ValueError as e:
    print(f"Error finding tab blocks: {e}")

# 3. Rename with statements
content = content.replace('with tab1:', 'with tab_radar:')
content = content.replace('with tab4:', 'with tab_radar:  # 🚀 오늘의 텐배거 레이더')
content = content.replace('with tab2:', 'with tab_report:')
content = content.replace('with tab3:', 'with tab_report:  # 🤖 AI 참모 리포트')
content = content.replace('with tab_port:', 'with tab_port:')
content = content.replace('with tab_risk:', 'with tab_port:  # 🚨 리스크 등급 가이드')
content = content.replace('with tab5:', 'with tab_port:  # 📖 11원칙 매매 가이드라인')

with open(r'C:\Users\로컬\Desktop\my-quant-bot\final.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Tabs refactored successfully.")
