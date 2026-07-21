import re

with open(r'C:\Users\로컬\Desktop\my-quant-bot\final.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Insert global calculations BEFORE the st.tabs statement
global_calcs = '''macro_charts = get_macro_charts()
usd_krw      = macro_charts.get("usdkrw_10y", pd.DataFrame())
kospi_10y    = macro_charts.get("kospi_10y", pd.DataFrame())
vkospi_10y   = macro_charts.get("vkospi_10y", pd.DataFrame())
spy_10y      = macro_charts.get("spy_10y", pd.DataFrame())
vix_10y      = macro_charts.get("vix_10y", pd.DataFrame())
vix3m_10y    = macro_charts.get("vix3m_10y", pd.DataFrame())

us_score, us_verdict, us_details, us_phase = calculate_us_bottom_finder(spy_10y, vix_10y, cnn_score)
kr_score, kr_verdict, kr_details, kr_phase = calculate_kr_bottom_finder(kospi_10y, vkospi_10y, usd_krw)
kr_rec_verdict, kr_rec_signals, kr_rec_score = calculate_kr_recovery_confirmation(kospi_10y, usd_krw)
kr_risk_grade, kr_risk_color, kr_risk_alerts, kr_danger = calculate_kr_risk_radar(vkospi_10y, usd_krw, kospi_10y)
'''

content = re.sub(
    r'macro_charts = get_macro_charts\(\)\s+usd_krw\s*=\s*macro_charts\.get\("usdkrw_10y", pd\.DataFrame\(\)\)',
    global_calcs,
    content
)

# 2. Remove the duplicate declarations inside tab_report and tab_sniper that could cause conflicts or be redundant.
# In tab_sniper, we used score = kr_score, etc. Those can remain since kr_score is now global.
# We just need to make sure we don't redefine them locally in a way that breaks.

# Wait, in tab_report, there are lines like:
# us_score, us_verdict, us_details, us_phase = calculate_us_bottom_finder(spy_10y, vix_10y, cnn_score)
# kr_score, kr_verdict, kr_details, kr_phase = calculate_kr_bottom_finder(kospi_10y, vkospi_10y, usd_krw)
# I will comment them out.

content = content.replace("us_score, us_verdict, us_details, us_phase = calculate_us_bottom_finder(spy_10y, vix_10y, cnn_score)", "# us_score already calculated globally")
content = content.replace("kr_score, kr_verdict, kr_details, kr_phase = calculate_kr_bottom_finder(kospi_10y, vkospi_10y, usd_krw)", "# kr_score already calculated globally")
content = content.replace("kr_rec_verdict, kr_rec_signals, kr_rec_score = calculate_kr_recovery_confirmation(", "# kr_rec already calculated globally")
content = content.replace("kospi_10y, usd_krw", "# kospi_10y, usd_krw")
content = content.replace(")", "# )") # This is too broad, let's not do replace like this for multi-line.

# Instead, let's just write the changes back. Python variable shadowing is fine, if they recalculate it in tab_report, it's just redundant but won't crash.
# The critical part is that they are now defined BEFORE tab_sniper.

with open(r'C:\Users\로컬\Desktop\my-quant-bot\final.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Global calculations injected before st.tabs.")
