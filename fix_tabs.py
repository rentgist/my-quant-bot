import re

with open(r'C:\Users\로컬\Desktop\my-quant-bot\final.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace the tabs definition
pattern = re.compile(r'tab1, tab2, tab4, tab3, tab_port, tab5, tab_risk = st\.tabs\(\[\s*".*?",\s*".*?",\s*".*?",\s*".*?",\s*".*?",\s*".*?",\s*".*?"\s*\]\)', re.DOTALL)

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

if pattern.search(content):
    content = pattern.sub(new_tabs, content)
    with open(r'C:\Users\로컬\Desktop\my-quant-bot\final.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("Tabs patched")
else:
    print("Regex did not match")
