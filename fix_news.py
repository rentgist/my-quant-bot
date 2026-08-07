import os

with open('signals.py', 'r', encoding='utf-8') as f:
    content = f.read()

old_news = '''        if top_news:
            latest_important = top_news[0]
            action = latest_important.get("action_point")
            if action:
                actions.append(f"📰 **최신 주요 뉴스 기반 대응**: {action}")'''

new_news = '''        if top_news:
            latest_important = top_news[0]
            action = latest_important.get("action_point")
            if action:
                # Resolve contradiction
                sentiment = latest_important.get("sentiment", "")
                prefix = "📰 **최신 주요 뉴스 기반 대응**"
                if sentiment == "악재" and us_phase == "CLEAR":
                    prefix = "📰 **단기 노이즈 주의(단기 악재 뉴스 포착)**"
                elif sentiment == "호재" and us_phase == "ALERT":
                    prefix = "📰 **단기 반등 재료(호재 뉴스 포착)**"
                actions.append(f"{prefix}: {action}")'''

content = content.replace(old_news, new_news)

with open('signals.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Fixed news logic")
