import re

with open('final.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Extract the appended code
split_idx = content.find('# --- US Orion Signal ---')
appended_code = content[split_idx:]
base_code = content[:split_idx]

# Split the appended code into US Signal block and Port block
port_idx = appended_code.find('# --- Custom Portfolio Advice ---')
us_code = appended_code[:port_idx]
port_code = appended_code[port_idx:]

# 2. Insert US Signal block before "with tab_radar:"
# (Wait, if I insert before tab_radar, it will run correctly without being blocked by st.stop)
radar_idx = base_code.find('with tab_radar:')
base_code = base_code[:radar_idx] + us_code + '\n' + base_code[radar_idx:]

# 3. Insert Custom Portfolio block before "with tab_calendar:"
cal_idx = base_code.find('with tab_calendar:')
base_code = base_code[:cal_idx] + port_code + '\n' + base_code[cal_idx:]

# 4. Replace Flags with Emojis that work on Windows
# 🇰🇷 -> 🐯 (Tiger)
# 🇺🇸 -> 🦅 (Eagle)
base_code = base_code.replace('🇰🇷', '🐯').replace('🇺🇸', '🦅')

with open('final.py', 'w', encoding='utf-8') as f:
    f.write(base_code)
    
print("Code injected correctly.")
