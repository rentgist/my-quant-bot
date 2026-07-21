with open(r'C:\Users\로컬\Desktop\my-quant-bot\final.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if "with tab_sniper:" in line or "kr_score, kr_verdict" in line or "kr_rec_verdict" in line or "kr_risk_grade" in line or "macro_charts.get" in line:
        print(f"{i+1}: {line.strip()[:100]}")
