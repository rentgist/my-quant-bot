with open('final.py', 'r', encoding='utf-8') as f:
    content = f.read()
    
broken = '''    with tab_radar:
    st.subheader("🎯 타점 선택 (Entry Point Selection) - 포트폴리오 종목 타점")
    st.caption("스나이퍼 탭에서 'GO' 신호가 떨어졌을 때, 어떤 종목을 살지 재무 및 수급을 점검하는 레이더입니다.")'''

fixed = '''    with tab_radar:
        st.subheader("🎯 타점 선택 (Entry Point Selection) - 포트폴리오 종목 타점")
        st.caption("스나이퍼 탭에서 'GO' 신호가 떨어졌을 때, 어떤 종목을 살지 재무 및 수급을 점검하는 레이더입니다.")'''

content = content.replace(broken, fixed)

# Also fix the markdown block that follows
broken2 = '''    st.markdown("""
    <div style='background-color:#e8f4f8; padding:15px; border-radius:8px; border-left: 6px solid #17a2b8; margin-bottom:20px;'>'''

fixed2 = '''        st.markdown("""
    <div style='background-color:#e8f4f8; padding:15px; border-radius:8px; border-left: 6px solid #17a2b8; margin-bottom:20px;'>'''

content = content.replace(broken2, fixed2)

with open('final.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("Indentation fixed.")
