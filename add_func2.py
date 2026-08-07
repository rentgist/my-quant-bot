import os

with open('signals.py', 'r', encoding='utf-8') as f:
    content = f.read()

new_func = '''
def calculate_us_flow_signal(spy_flow, qqq_flow, soxx_flow):
    """
    US ETF 자금흐름 점수를 기반으로 수급 강도를 판정합니다.
    """
    score = 0
    details = []
    
    avg_flow = (spy_flow + qqq_flow) / 2
    
    if avg_flow > 0.5:
        score += 40
        status = "🟢 강한 수급 유입 (Strong Inflow)"
    elif avg_flow > 0:
        score += 20
        status = "🟡 약한 매수 우위 (Mild Inflow)"
    elif avg_flow > -0.5:
        score -= 20
        status = "🟠 약한 매도 우위 (Mild Outflow)"
    else:
        score -= 40
        status = "🔴 강한 수급 유출 (Strong Outflow)"
        
    details.append(("🏢", f"SPY 수급 프록시: {spy_flow:+.2f}"))
    details.append(("🚀", f"QQQ 수급 프록시: {qqq_flow:+.2f}"))
    details.append(("💻", f"SOXX 수급 프록시: {soxx_flow:+.2f}"))
    
    if soxx_flow < -1.0:
        details.append(("⚠️", "반도체(SOXX) 섹터의 강한 자금 유출 경고"))
    elif soxx_flow > 1.0:
        details.append(("🔥", "반도체(SOXX) 섹터의 강한 자금 유입 포착"))
        
    return score, status, details
'''

if 'def calculate_us_flow_signal' not in content:
    with open('signals.py', 'a', encoding='utf-8') as f:
        f.write('\n\n' + new_func + '\n')
    print("Added calculate_us_flow_signal")
else:
    print("Already exists")
