import re

with open(r'C:\Users\로컬\Desktop\my-quant-bot\final.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Update the tab name
content = content.replace('"🎯 14:50 실전 타격",', '"🎯 14:50 국장 실전 타격",')

# 2. Update the backtest call inside the expander
old_bt_call = '''        vix_10y = macro_charts.get("vix_10y", pd.DataFrame())
        vix3m_10y = macro_charts.get("vix3m_10y", pd.DataFrame())
        spy_10y = macro_charts.get("spy_10y", pd.DataFrame())
        bt_us = run_historical_backtest(spy_10y, vix_10y, vix3m_10y)
        
        if bt_us:
            score = bt_us.get("바닥점수", 0)
            rec_score = bt_us.get("반등신뢰도", 0)
            danger = bt_us.get("위험경보", 0)'''

new_bt_call = '''        vkospi_10y = macro_charts.get("vkospi_10y", pd.DataFrame())
        usd_krw = macro_charts.get("usdkrw_10y", pd.DataFrame())
        kospi_10y = macro_charts.get("kospi_10y", pd.DataFrame())
        bt_kr = run_kr_historical_backtest(kospi_10y, vkospi_10y, usd_krw)
        
        if bt_kr:
            score = bt_kr.get("바닥점수", 0)
            rec_score = bt_kr.get("반등신뢰도", 0)
            danger = bt_kr.get("위험경보", 0)'''

content = content.replace(old_bt_call, new_bt_call)

# 3. Update the metric label for danger
content = content.replace('"VIX 위험 경보치"', '"VKOSPI 위험 경보치"')

with open(r'C:\Users\로컬\Desktop\my-quant-bot\final.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("KR backtest and tab name updated.")
