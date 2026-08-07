with open('final.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

start_idx = -1
end_idx = -1
for i, line in enumerate(lines):
    if line.startswith('with tab_orion_us:'):
        start_idx = i
    elif line.startswith('    with tab_radar:') or line.startswith('with tab_radar:'):
        if start_idx != -1:
            end_idx = i
            break

new_us_tab_code = '''    with tab_orion_us:
        st.subheader("🦅 ORION Signal (미장)")
        st.caption("미국 증시 특화 매크로, 유동성, 심리 통합 스코어링 시스템")
        
        if "calculate_us_orion_score" in globals() and "get_us_strategic_advice" in globals():
            try:
                total_score, us_phase, components, triggers, metrics = calculate_us_orion_score(macro_charts)
                adv_head, adv_color, adv_actions = get_us_strategic_advice(us_phase, total_score, triggers)
                
                # 1. AI Strategic Advice Box
                st.markdown(
                    f"<div style='background:{adv_color}22; border-left: 8px solid {adv_color}; padding:20px; border-radius:10px; margin-bottom:20px;'>"
                    f"<h2 style='margin-top:0; color:{adv_color};'>{adv_head}</h2>"
                    f"<p style='font-size:0.95em; color:#888; margin-bottom:10px;'>종합 스코어 {total_score:.1f}점 · {us_phase}</p>"
                    f"<ul>" + "".join([f"<li style='font-size:1.05em; margin-bottom:5px;'>{a}</li>" for a in adv_actions]) + "</ul>"
                    f"</div>", unsafe_allow_html=True
                )
                
                st.divider()
                st.markdown("### 🌐 글로벌 매크로 & 유동성 통합 지표")
                
                # 2. 4-Column Metrics
                u_col1, u_col2, u_col3, u_col4 = st.columns(4)
                
                tnx_val = metrics.get('tnx')
                if tnx_val:
                    u_col1.metric("미 10년물 국채금리", f"{tnx_val:.2f}%")
                else:
                    u_col1.metric("미 10년물 국채금리", "N/A")
                    
                dxy_val = metrics.get('dxy')
                if dxy_val:
                    u_col2.metric("달러 인덱스 (DXY)", f"{dxy_val:.2f}")
                else:
                    u_col2.metric("달러 인덱스 (DXY)", "N/A")
                    
                hy_val = metrics.get('hy_spread')
                if hy_val:
                    u_col3.metric("하이일드 스프레드", f"{hy_val:.2f}%")
                else:
                    u_col3.metric("하이일드 스프레드", "N/A")
                    
                liq_val = metrics.get('net_liquidity')
                if liq_val:
                    u_col4.metric("연준 순유동성", f"\B")
                else:
                    u_col4.metric("연준 순유동성", "N/A")
                    
                # 3. Score Details and BTC Caveat
                st.markdown("---")
                st.markdown("#### 📊 세부 스코어보드 및 보조 지표")
                score_col1, score_col2 = st.columns(2)
                with score_col1:
                    st.progress(components['macro'] / 35.0, text=f"매크로 유동성 (35점 만점): {components['macro']:.1f}점")
                    st.progress(components['credit'] / 35.0, text=f"신용 및 심리 (35점 만점): {components['credit']:.1f}점")
                with score_col2:
                    st.progress(components['strength'] / 20.0, text=f"시장 체력 (20점 만점): {components['strength']:.1f}점")
                    st.progress(components['aux'] / 10.0, text=f"비트코인 등 보조지표 (10점 만점): {components['aux']:.1f}점")
                    
                st.info("⚠️ **비트코인(BTC) 해석 주의**: 비트코인은 글로벌 유동성의 선행 지표 성격을 띠지만, 가상자산 시장 고유의 이슈(거래소 리스크 등)로 인해 매크로 흐름과 무관하게 가격이 왜곡될 수 있으므로 절대적인 지표로 맹신하지 마십시오.")

            except Exception as e:
                st.error(f"미국 시그널 로딩 중 오류: {e}")
        else:
            st.info("US Macro logic not loaded yet.")

'''
if start_idx != -1 and end_idx != -1:
    import_str = '        calculate_us_orion_score,'
    new_import_str = '        calculate_us_orion_score,\n        get_us_strategic_advice,'
    
    # Check if with tab_orion_us: has indent
    indent = lines[start_idx][:-len(lines[start_idx].lstrip())]
    
    indented_new_code = []
    for line in new_us_tab_code.splitlines():
        indented_new_code.append(indent + line[4:] + '\n') # strip 4 spaces and add original indent
        
    final_lines = lines[:start_idx] + indented_new_code + lines[end_idx:]
    
    content = "".join(final_lines)
    content = content.replace(import_str, new_import_str)
    
    with open('final.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("UI replaced perfectly.")
else:
    print(f"Could not find bounds. start: {start_idx}, end: {end_idx}")
