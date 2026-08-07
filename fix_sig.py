with open('signals.py', 'r', encoding='utf-8') as f:
    content = f.read()

old_advice = '''    if triggers:
        for t in list(set(triggers)):
            actions.append(f"💡 {t}")
    else:
        actions.append("💡 주요 매크로 지표들이 중립적인 수준을 유지하고 있습니다.")'''

new_advice = '''    if triggers:
        for t in list(set(triggers)):
            actions.append(f"💡 {t}")
    else:
        actions.append("💡 주요 매크로 지표들이 중립적인 수준을 유지하고 있습니다.")
        
    # Add top news action point if we can fetch it
    try:
        from data_loader import get_market_news
        us_news = get_market_news("US", limit=5)
        top_news = [n for n in us_news if n.get("importance", 0) >= 4]
        if top_news:
            latest_important = top_news[0]
            action = latest_important.get("action_point")
            if action:
                actions.append(f"📰 **최신 주요 뉴스 기반 대응**: {action}")
    except Exception as e:
        pass'''

content = content.replace(old_advice, new_advice)

with open('signals.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("Updated signals.py")
