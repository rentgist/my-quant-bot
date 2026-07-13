import os

file_path = "final.py"
with open(file_path, "r", encoding="utf-8") as f:
    lines = f.readlines()

# 1. Rename tab
for i, line in enumerate(lines):
    if '"🎯 14:50 국장 실전 타격"' in line:
        lines[i] = line.replace('"🎯 14:50 국장 실전 타격"', '"🎯 AI 스마트 관제실"')
        break

# 2. Delete the redundant tier logic (find start and end)
start_idx = -1
end_idx = -1
for i, line in enumerate(lines):
    if "##### 🚦 v24.0 실시간 Tier 판정" in line:
        start_idx = i - 1  # include the st.markdown line and comment above it
    if start_idx != -1 and "False Signal 경보" in line:
        end_idx = i
        break

if start_idx != -1 and end_idx != -1:
    del lines[start_idx:end_idx]

# 3. Replace tab_sniper section
start_idx = -1
end_idx = -1
for i, line in enumerate(lines):
    if line.startswith("with tab_sniper:"):
        start_idx = i
    if line.startswith("with tab_radar:"):
        end_idx = i
        break

if start_idx != -1 and end_idx != -1:
    new_sniper_code = """with tab_sniper:
    st.subheader("🎯 AI 스마트 관제실 (v27.0)")
    st.caption("최종 업데이트: 실시간 (매크로/위험도/바닥 지표 + AI 브리핑 통합)")

    adv_head, adv_color, adv_actions = get_strategic_advice(
        kr_danger, kr_score, kr_verdict, kr_phase, recovery_score=kr_rec_score
    )

    st.markdown(
        f"<div style='background:{adv_color}22; border-left: 8px solid {adv_color}; "
        f"padding:20px; border-radius:10px; margin-bottom:20px;'>"
        f"<h2 style='margin-top:0; color:{adv_color};'>{adv_head}</h2>"
        f"<p style='font-size:1.1em; font-weight:bold; margin-bottom:10px;'>📌 알고리즘 시스템 판독 근거: 위험도 {kr_danger}점 / 바닥확률 {kr_score}% / 반등신뢰도 {kr_rec_score}점 / {kr_phase}</p>"
        f"<ul>" + "".join([f"<li style='font-size:1.05em; margin-bottom:5px;'>{a}</li>" for a in adv_actions]) + "</ul>"
        f"</div>", unsafe_allow_html=True
    )

    st.markdown("### 🤖 실시간 AI 종합 브리핑")
    
    if st.button("🔄 AI 종합 관제 리포트 생성 (뉴스 + 매크로 종합)", type="primary"):
        with st.spinner("Gemini 2.5 Flash가 글로벌 속보와 매크로 수치를 종합하여 리포트를 작성 중입니다..."):
            market_ctx = f"판정결과: {adv_head}\\n위험도: {kr_danger}점\\n바닥점수: {kr_score}점\\n현재국면: {kr_phase}"
            
            try:
                from ai_reporter import generate_smart_control_room_report
                report = generate_smart_control_room_report(market_ctx)
                st.session_state["ai_report_cache"] = report
            except Exception as e:
                st.error(f"리포트 생성 모듈 로드 실패: {e}")

    if "ai_report_cache" in st.session_state:
        st.markdown(st.session_state["ai_report_cache"])
    else:
        st.info("👈 상단의 버튼을 눌러 최신 시황 리포트를 생성하세요.")

    st.divider()

    st.markdown("### 📰 최근 글로벌 주요 뉴스 (AI 수집)")
    news_file = "data/news_archive.json"
    import os, json
    if os.path.exists(news_file):
        try:
            with open(news_file, "r", encoding="utf-8") as f:
                news_data = json.load(f)
            if news_data:
                for n in news_data[:8]:
                    title = n.get("title_ko", n.get("title", ""))
                    link = n.get("link", "#")
                    source = n.get("source", "N/A")
                    importance = n.get("importance", 0)
                    sentiment = n.get("sentiment", "중립")
                    
                    stars = "⭐" * importance
                    color = "red" if sentiment == "악재" else "green" if sentiment == "호재" else "gray"
                    
                    with st.expander(f"[{source}] {title} (중요도: {stars})"):
                        st.markdown(f"**판단 근거**: {n.get('reason', '')}")
                        st.markdown(f"**대응 액션**: <span style='color:{color}; font-weight:bold;'>{n.get('action_point', '')}</span>", unsafe_allow_html=True)
                        st.markdown(f"[원문 기사 보러가기]({link})")
            else:
                st.write("수집된 뉴스가 없습니다.")
        except Exception as e:
            st.error(f"뉴스 로드 중 오류: {e}")
    else:
        st.write("현재 수집된 뉴스 아카이브가 존재하지 않습니다.")

    st.divider()

    with st.expander("✅ 14:50 실전 타격 간편 체크리스트", expanded=False):
        st.markdown("매수 승인(비중 확대) 지시가 떨어졌을 때만 확인하세요.")
        c1, c2, c3 = st.columns(3)
        with c1:
            st.checkbox("외국인 선물 순매수 (+5000계약 이상 확인)")
        with c2:
            st.checkbox("KOSPI 5일선 버퍼 지지 (종가 기준)")
        with c3:
            st.checkbox("타겟 종목 RSI 과매수(70) 미만 확인")
        st.info("위 3가지가 모두 만족될 때, 오후 2시 50분에 시장가로 매수 집행합니다.")

"""
    lines = lines[:start_idx] + [new_sniper_code + "\n"] + lines[end_idx:]

with open(file_path, "w", encoding="utf-8") as f:
    f.writelines(lines)

print("final.py patched successfully.")
