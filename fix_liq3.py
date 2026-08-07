with open('final.py', 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace('u_col4.metric("연준 순유동성", f"B")', 'u_col4.metric("연준 순유동성", f"\B")')

with open('final.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("Replaced net liquidity string.")
