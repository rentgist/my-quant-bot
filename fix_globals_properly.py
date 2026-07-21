with open(r'C:\Users\로컬\Desktop\my-quant-bot\final.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
inserted_globals = False

for line in lines:
    if 'macro_charts = get_macro_charts()' in line and not inserted_globals:
        new_lines.append(line)
        # Add the rest of the global initializations
        new_lines.append('usd_krw      = macro_charts.get("usdkrw_10y", pd.DataFrame())\n')
        new_lines.append('kospi_10y    = macro_charts.get("kospi_10y", pd.DataFrame())\n')
        new_lines.append('vkospi_10y   = macro_charts.get("vkospi_10y", pd.DataFrame())\n')
        new_lines.append('spy_10y      = macro_charts.get("spy_10y", pd.DataFrame())\n')
        new_lines.append('vix_10y      = macro_charts.get("vix_10y", pd.DataFrame())\n')
        new_lines.append('vix3m_10y    = macro_charts.get("vix3m_10y", pd.DataFrame())\n')
        new_lines.append('hyg_10y      = macro_charts.get("hyg_10y", pd.DataFrame())\n')
        new_lines.append('ief_10y      = macro_charts.get("ief_10y", pd.DataFrame())\n')
        new_lines.append('rsp_10y      = macro_charts.get("rsp_10y", pd.DataFrame())\n')
        new_lines.append('\n')
        new_lines.append('us_score, us_verdict, us_details, us_phase = calculate_us_bottom_finder(spy_10y, vix_10y, cnn_score)\n')
        new_lines.append('kr_score, kr_verdict, kr_details, kr_phase = calculate_kr_bottom_finder(kospi_10y, vkospi_10y, usd_krw)\n')
        new_lines.append('kr_rec_verdict, kr_rec_signals, kr_rec_score = calculate_kr_recovery_confirmation(kospi_10y, usd_krw)\n')
        new_lines.append('kr_risk_grade, kr_risk_color, kr_risk_alerts, kr_danger = calculate_kr_risk_radar(vkospi_10y, usd_krw, kospi_10y)\n')
        inserted_globals = True
        continue
        
    if inserted_globals and 'usd_krw      = macro_charts.get("usdkrw_10y", pd.DataFrame())' in line:
        continue # Skip the original usd_krw line
        
    # Comment out redundant definitions in tab_report later
    if 'us_score, us_verdict, us_details, us_phase = calculate_us_bottom_finder' in line:
        new_lines.append('# ' + line)
        continue
    if 'kr_score, kr_verdict, kr_details, kr_phase = calculate_kr_bottom_finder' in line:
        new_lines.append('# ' + line)
        continue
    if 'kr_rec_verdict, kr_rec_signals, kr_rec_score = calculate_kr_recovery_confirmation' in line:
        new_lines.append('# ' + line)
        continue
    if 'kr_risk_grade, kr_risk_color, kr_risk_alerts, kr_danger = calculate_kr_risk_radar' in line:
        new_lines.append('# ' + line)
        continue
        
    new_lines.append(line)

with open(r'C:\Users\로컬\Desktop\my-quant-bot\final.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print("Global calculations fixed properly.")
