with open('final.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()
for i, line in enumerate(lines):
    if 'liq_val = metrics.get' in line:
        # The next line is if liq_val:
        # The next line is u_col4.metric...
        pass
    if 'u_col4.metric' in line and ('f"B"' in line or r'f"\B"' in line):
        # We replace the f-string part
        lines[i] = line.replace('f"B"', 'f"B"').replace(r'f"\B"', 'f"B"')

with open('final.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)
