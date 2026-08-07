with open('final.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i in range(len(lines)):
    if lines[i].startswith('    with tab_radar:'):
        # We check subsequent lines
        j = i + 1
        while j < len(lines) and not lines[j].startswith('    with '):
            if lines[j].startswith('    st.'):
                lines[j] = '    ' + lines[j]
            elif lines[j].startswith('    </div>'):
                lines[j] = '    ' + lines[j]
            elif lines[j].startswith('    """,'):
                lines[j] = '    ' + lines[j]
            j += 1
        break

with open('final.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)
