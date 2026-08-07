import os

with open('ai_reporter.py', 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace('def generate_smart_control_room_report(market_context: str) -> str:', 'def generate_smart_control_room_report(market_context: str, target_market: str = "KR") -> str:')

# Filter news by market inside the function
old_filter = '''        for item in data:
            if item.get("importance", 0) >= 3:
                filtered_news.append(item)'''

new_filter = '''        for item in data:
            m = item.get("market", "")
            if target_market == "KR" and m not in ("KR", "GLOBAL"): continue
            if target_market == "US" and m not in ("US", "GLOBAL"): continue
            
            if item.get("importance", 0) >= 3:
                filtered_news.append(item)'''

content = content.replace(old_filter, new_filter)

with open('ai_reporter.py', 'w', encoding='utf-8') as f:
    f.write(content)
