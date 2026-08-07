with open('final.py', 'r', encoding='utf-8') as f:
    content = f.read()

# We need to insert the news and flow report at the bottom of tab_orion_us.
# Find where the tab_orion_us block ends.
# It ends with st.info("US Macro logic not loaded yet.")

old_block = '''        else:
            st.info("US Macro logic not loaded yet.")'''

new_block = '''        else:
            st.info("US Macro logic not loaded yet.")
            
        st.markdown("---")
        st.markdown("### 📰 실시간 미장 핵심 뉴스")
        from data_loader import get_market_news, get_us_flow_report
        
        us_news = get_market_news("US", limit=7)
        if us_news:
            for n in us_news:
                title = n.get("title_ko", n.get("title", ""))
                link = n.get("link", "#")
                source = n.get("source", "N/A")
                importance = n.get("importance", 0)
                sentiment = n.get("sentiment", "중립")
                
                stars = "⭐" * importance
                color = "red" if sentiment == "악재" else "green" if sentiment == "호재" else "gray"
                
                with st.expander(f"[{source}] {title} (중요도: {stars})"):
                    st.markdown(f"**판단 근거**: {n.get('reason', '')}")
                    st.markdown(f"**대응 액션**: <span style='color:{color}; font-weight:bold;'>{n.get('action_point', '')}</span>", unsafe_allow_html=True)
                    st.markdown(f"[원문 기사 보러가기]({link})")
        else:
            st.write("수집된 미장 뉴스가 없습니다.")
            
        st.markdown("---")
        us_flow = get_us_flow_report()
        if us_flow:
            st.markdown(us_flow)
        else:
            st.write("미장 수급 동향 리포트를 불러올 수 없습니다.")'''

content = content.replace(old_block, new_block)

# Also we need to fix the KR tab which currently fetches its own news.
# The user said: 국장 탭 기존 로직도 get_market_news("KR")로 통일하면 코드 중복 제거
# The KR news fetch block starts with 
ews_data = [] and ends around if True: or if news_data: inside inal.py.
# But for safety, since we already added get_market_news to data_loader.py, we can just replace the KR news fetch.

# The KR news code block starts at 
ews_data = [] and emote_url = "https://raw.githubusercontent.com/...
old_kr_fetch = '''    news_data = []
    remote_url = "https://raw.githubusercontent.com/rentgist/quant-alpha-engine/main/data/news_archive.json"
    try:
        resp = requests.get(remote_url, timeout=5)
        if resp.status_code == 200:
            news_data = resp.json()
    except:
        pass
        
    if not news_data:
        news_file = os.path.join("..", "quant-alpha-engine", "data", "news_archive.json")
        if not os.path.exists(news_file):
            news_file = "data/news_archive.json"
        if os.path.exists(news_file):
            try:
                with open(news_file, "r", encoding="utf-8") as f:
                    news_data = json.load(f)
            except:
                pass
                
    if True:
        try:
            if news_data:
                import datetime
                recent_news = []
                now = datetime.datetime.now()
                for n in news_data:
                    dt_str = n.get("fetched_at", "")
                    try:
                        # Only include news within the last 3 days (72 hours)
                        dt = datetime.datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
                        if (now - dt).days <= 3:
                            recent_news.append(n)
                    except:
                        # If date parsing fails, just include it to be safe
                        recent_news.append(n)
                
                news_data = sorted(recent_news, key=lambda x: (x.get("importance", 0), x.get("fetched_at", "")), reverse=True)'''

new_kr_fetch = '''    from data_loader import get_market_news
    news_data = get_market_news("KR", limit=60)
                
    if True:
        try:
            if news_data:'''

content = content.replace(old_kr_fetch, new_kr_fetch)

with open('final.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("Updated final.py with US news rendering and KR news refactoring")
