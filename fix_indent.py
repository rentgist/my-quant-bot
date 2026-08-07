import re

with open('final.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
for i, line in enumerate(lines):
    if line.startswith('    with tab_radar:'):
        line = '    with tab_radar:\n'
    elif line.startswith('with tab_radar:'):
        line = '    with tab_radar:\n'
    # Need to make sure the subsequent lines are indented properly. But wait, they were properly indented originally.
    # Ah, the problem was I did inal_content = content_before + new_us_tab_code + '\n    ' + content_after.
    # content_after was     with tab_radar:\n    st.subheader...
    # So '\n    ' + content_after became \n        with tab_radar:\n    st.subheader or something?
    # No, content_after started with "with tab_radar:", so '\n    ' + content_after became:
    #     with tab_radar:
    #     st.subheader... (no extra indentation for st.subheader!)
    
    new_lines.append(line)
    
# Let's just fix the block starting with "with tab_radar:"
with open('final.py', 'w', encoding='utf-8') as f:
    for line in new_lines:
        if line.startswith('    with tab_radar:'):
            f.write(line)
        elif line.startswith('    st.subheader("🎯 타점 선택 (Entry Point Selection)') or line.startswith('    st.subheader("? ????택 (Entry Point Selection)'):
            f.write('        ' + line.lstrip())
        elif line.startswith('    st.caption("스나이퍼 탭에서') or line.startswith('    st.caption("?나?퍼 ??'):
            f.write('        ' + line.lstrip())
        elif line.startswith('    st.markdown("""') and "background-color:#e8f4f8" in ''.join(lines):
            pass # We'll do a proper regex replace or string manipulation
        else:
            f.write(line)
