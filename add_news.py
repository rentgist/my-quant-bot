import os
import json
import requests
import datetime
import streamlit as st

@st.cache_data(ttl=600)
def get_market_news(market="KR", limit=20):
    news_data = []
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
                
    recent_news = []
    now = datetime.datetime.now()
    if news_data:
        for n in news_data:
            m = n.get("market", "KR")
            if m not in (market, "GLOBAL"):
                continue
                
            dt_str = n.get("fetched_at", "")
            try:
                dt = datetime.datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
                if (now - dt).days <= 3:
                    recent_news.append(n)
            except:
                recent_news.append(n)
                
        sorted_news = sorted(recent_news, key=lambda x: (x.get("importance", 0), x.get("fetched_at", "")), reverse=True)
        return sorted_news[:limit]
    return []

@st.cache_data(ttl=600)
def get_us_flow_report():
    remote_url = "https://raw.githubusercontent.com/rentgist/quant-alpha-engine/main/data/us_flow_report.md"
    try:
        resp = requests.get(remote_url, timeout=5)
        if resp.status_code == 200:
            return resp.text
    except:
        pass
        
    local_file = os.path.join("..", "quant-alpha-engine", "data", "us_flow_report.md")
    if os.path.exists(local_file):
        with open(local_file, "r", encoding="utf-8") as f:
            return f.read()
    return ""
