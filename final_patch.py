# 1. Update final.py Tier colors
with open(r'C:\Users\로컬\Desktop\my-quant-bot\final.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace color:#fff; with nothing so it inherits Streamlit's default (which adapts to light/dark mode)
content = content.replace("color:#fff;", "")

with open(r'C:\Users\로컬\Desktop\my-quant-bot\final.py', 'w', encoding='utf-8') as f:
    f.write(content)

# 2. Remove TENBAGGER_UNIVERSE from config.py
with open(r'C:\Users\로컬\Desktop\my-quant-bot\config.py', 'r', encoding='utf-8') as f:
    config_content = f.read()

import re
config_content = re.sub(r'# ─+.*?TENBAGGER_UNIVERSE = \{.*?\}\n', '', config_content, flags=re.DOTALL)

with open(r'C:\Users\로컬\Desktop\my-quant-bot\config.py', 'w', encoding='utf-8') as f:
    f.write(config_content.strip() + '\n')

print("Final patch complete")
