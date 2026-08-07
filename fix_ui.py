import os

with open('final.py', 'r', encoding='utf-8') as f:
    content = f.read()

old_render = '''    def render_us_flow(col, label, ticker):
        score = flow_dict.get(ticker, 0.0)
        state = "순매수" if score > 0 else "순매도" if score < 0 else "중립"
        col.metric(f"{label} 수급 프록시", f"{score:+.2f}", f"{state}")'''

new_render = '''    def render_us_flow(col, label, ticker):
        score = flow_dict.get(ticker, 0.0)
        state = "순매수 우위" if score > 0 else "순매도 우위" if score < 0 else "중립"
        col.metric(f"{label}", f"스코어: {score:+.2f}", f"{state}", delta_color="normal" if score > 0 else "inverse" if score < 0 else "off")'''

content = content.replace(old_render, new_render)

with open('final.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Fixed UI")
