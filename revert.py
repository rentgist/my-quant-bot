import re

# 1. Update final.py Tier colors
with open(r'C:\Users\로컬\Desktop\my-quant-bot\final.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace color:#fff; with empty or inherit
content = content.replace("color:#fff;", "color:inherit;")

# Replace the Universe import back to the dictionary
old_import = '''    # ── 텐배거 유니버스 선택 (config.py 통합 관리) ──
    from config import TENBAGGER_UNIVERSE
    selected_theme = st.selectbox("🎯 테마 선택:", list(TENBAGGER_UNIVERSE.keys()))
    if st.button("🚀 해당 테마 실시간 스캔"):
        is_korea = "한국" in selected_theme
        radar_data = []
        tickers = TENBAGGER_UNIVERSE[selected_theme]'''

new_dict = '''    # ── 텐배거 유니버스 선택 ──
    # (사용자가 원하는 종목군을 카테고리별로 관리)
    UNIVERSE = {
        "🇺🇸 미국 AI & 클라우드":              ["PLTR","CRWD","SNOW","DDOG","NET","SOUN","MDB","ZS","MNDY"],
        "🇺🇸 미국 혁신성장 (우주/바이오/테크)": ["IONQ","SOFI","RIVN","CELH","RKLB","ASTS","CRSP","LUNR","SYM","HOOD"],
        "🇰🇷 한국 반도체 소부장 (HBM/AI)":        ["피에스케이홀딩스", "한미반도체", "테크윙", "HPSP", "이수페타시스", "에이직랜드", "와이아이케이", "원익IPS", "에스티아이", "주성엔지니어링", "리노공업", "하나마이크론"],
        "🇰🇷 한국 K-뷰티 & K-푸드":            ["실리콘투","클리오","파마리서치","삼양식품","에이피알","브이티","코스메카코리아"],
        "🇰🇷 한국 바이오 & 헬스케어":          ["알테오젠","HLB","삼천당제약","리가켐바이오","에이비엘바이오","파마리서치"],
        "🇰🇷 한국 전력기기 & 로봇":             ["HD현대일렉트릭","두산로보틱스","레인보우로보틱스","LS ELECTRIC"],
    }
    selected_theme = st.selectbox("🎯 테마 선택:", list(UNIVERSE.keys()))
    if st.button("🚀 해당 테마 실시간 스캔"):
        is_korea = "한국" in selected_theme
        radar_data = []
        tickers = UNIVERSE[selected_theme]'''

if old_import in content:
    content = content.replace(old_import, new_dict)
else:
    # Try alternate if format is slightly different
    old_import2 = '''    # ── 텐배거 유니버스 선택 ──
    # (사용자가 원하는 종목군을 카테고리별로 관리)
    from config import TENBAGGER_UNIVERSE as UNIVERSE
    selected_theme = st.selectbox("🎯 테마 선택:", list(UNIVERSE.keys()))
    if st.button("🚀 해당 테마 실시간 스캔"):
        is_korea = "한국" in selected_theme
        radar_data = []
        tickers = UNIVERSE[selected_theme]'''
    if old_import2 in content:
        content = content.replace(old_import2, new_dict)
    else:
        print("Warning: Could not find UNIVERSE import to revert in final.py")

with open(r'C:\Users\로컬\Desktop\my-quant-bot\final.py', 'w', encoding='utf-8') as f:
    f.write(content)

# 2. Update alert_bot.py
with open(r'C:\Users\로컬\Desktop\my-quant-bot\alert_bot.py', 'r', encoding='utf-8') as f:
    content2 = f.read()

old_bot_import = "from config import TENBAGGER_UNIVERSE"
new_bot_dict = '''# ─────────────────────────────────────────
# 텐배거 스크리닝 유니버스
# ─────────────────────────────────────────
TENBAGGER_UNIVERSE = {
    "🇺🇸 미국 AI & 클라우드":      ["PLTR","CRWD","SNOW","DDOG","NET","SOUN","MDB","ZS","MNDY"],
    "🇺🇸 미국 혁신성장":           ["IONQ","SOFI","RIVN","CELH","RKLB","ASTS","CRSP","LUNR","SYM","HOOD"],
    "🇰🇷 한국 반도체 소부장":       ["한미반도체","디아이","테크윙","HPSP","이수페타시스","에이직랜드",
                                    "와이아이케이","원익IPS","에스티아이","주성엔지니어링","리노공업","하나마이크론"],
    "🇰🇷 한국 K-뷰티/푸드":        ["실리콘투","클리오","삼양식품","빙그레","에이피알","브이티","코스메카코리아"],
    "🇰🇷 한국 바이오/헬스케어":     ["알테오젠","HLB","삼천당제약","리가켐바이오","에이비엘바이오","파마리서치"],
    "🇰🇷 한국 전력/인프라":        ["HD현대일렉트릭","제룡전기","효성중공업","LS ELECTRIC"],
}'''

if old_bot_import in content2:
    content2 = content2.replace(old_bot_import, new_bot_dict)
else:
    print("Warning: Could not find import in alert_bot.py")

with open(r'C:\Users\로컬\Desktop\my-quant-bot\alert_bot.py', 'w', encoding='utf-8') as f:
    f.write(content2)

print("Revert complete")
