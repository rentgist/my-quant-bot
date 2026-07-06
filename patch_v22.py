import sys

def patch():
    with open('final.py', 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. Page title
    content = content.replace('st.set_page_config(page_title="11원칙 퀀트 대시보드 v21.0"', 'st.set_page_config(page_title="11원칙 퀀트 대시보드 v22.0"')

    # 2. Main title & caption
    content = content.replace('st.title("🧭 11원칙 퀀트 트레이딩 대시보드 v21.0")\nst.caption("v21.0: 텐배거 Rule of 40 신설 + 자본집약 기업 EV 밸류에이션 + 어닝 서프라이즈 8Q 확장")', 'st.title("🧭 11원칙 퀀트 트레이딩 대시보드 v22.0")\nst.caption("v22.0: 글로벌 마스터 킬 스위치 (신용스프레드 교차 검증) + 환율 조기경보 탑재")')

    # 3. US Risk Radar 
    us_old = '''                if curr < ma50 * 0.97:
                    alerts.append(("🔴", f"신용 스프레드 위험 이탈. 기관 투매 감지."))
                    danger_count += 2
                elif curr < ma20:
                    alerts.append(("🟠", f"신용 스프레드 단기 이탈. 주시 필요."))
                    danger_count += 1
                else:
                    alerts.append(("🟢", "신용 스프레드 안정 (정배열)."))
        except:
            alerts.append(("⚪", "신용 스프레드 산출 불가."))

    if danger_count >= 4:
        grade = "🔴 미국 위기 경보 — 폭락 초입 가능성."
        color = "#ff4b4b"
    elif danger_count >= 2:
        grade = "🟠 미국 주의 단계 — 신규 진입 자제."
        color = "#ff9900"
    elif danger_count >= 1:
        grade = "🟡 미국 관찰 단계 — 경미한 이상 신호."
        color = "#fcca46"
    else:
        grade = "🟢 미국 이상 없음 — 매크로 환경 정상."
        color = "#21c354"'''

    us_new = '''                if curr < ma50 * 0.97:
                    alerts.append(("🔴", f"신용 스프레드 위험 이탈. 기관 투매 감지."))
                    danger_count += 2
                    credit_danger = True
                elif curr < ma20:
                    alerts.append(("🟠", f"신용 스프레드 단기 이탈. 주시 필요."))
                    danger_count += 1
                    credit_danger = True
                else:
                    alerts.append(("🟢", "신용 스프레드 안정 (정배열)."))
        except:
            alerts.append(("⚪", "신용 스프레드 산출 불가."))

    # SPY 급락 교차 검증 로직 (원인 분석)
    if not spy_hist.empty and len(spy_hist) >= 6:
        spy_1d_ret = (float(spy_hist['Close'].iloc[-1]) / float(spy_hist['Close'].iloc[-2]) - 1) * 100
        spy_5d_ret = (float(spy_hist['Close'].iloc[-1]) / float(spy_hist['Close'].iloc[-6]) - 1) * 100
        
        if spy_1d_ret <= -1.5 or spy_5d_ret <= -3.0:
            if credit_danger:
                alerts.append(("🚨", f"글로벌 킬 스위치 발동: SPY 급락({spy_1d_ret:.1f}%) & 신용 경색. 진짜 위기."))
                danger_count += 3
            else:
                alerts.append(("⚪", f"SPY 급락({spy_1d_ret:.1f}%) 발생, 단 신용 시장 평온. (단순 차익실현 추정)"))
        else:
            alerts.append(("🟢", f"SPY 단기 매크로 추세 안정적 ({spy_1d_ret:+.1f}%)."))

    if danger_count >= 5:
        grade = "🚨 글로벌 마스터 킬 스위치 작동 — 시스템적 유동성 위기."
        color = "#ff0000"
    elif danger_count >= 3:
        grade = "🔴 글로벌 위기 경보 — 폭락 초입 가능성."
        color = "#ff4b4b"
    elif danger_count >= 2:
        grade = "🟠 글로벌 주의 단계 — 신규 진입 자제."
        color = "#ff9900"
    elif danger_count >= 1:
        grade = "🟡 글로벌 관찰 단계 — 경미한 이상 신호."
        color = "#fcca46"
    else:
        grade = "🟢 글로벌 마스터 이상 없음 — 매크로 환경 정상."
        color = "#21c354"'''
    
    content = content.replace(us_old, us_new)
    
    # Inject credit_danger init
    content = content.replace('    if not hyg_hist.empty and not ief_hist.empty:', '    credit_danger = False\n    if not hyg_hist.empty and not ief_hist.empty:')

    # 4. KR Risk Radar
    kr_old = '''    # 1. 환율 급변동 (외국인 자본 이탈 강력 프록시)
    if not usdkrw_hist.empty and len(usdkrw_hist) >= 6:
        curr_krw = float(usdkrw_hist['Close'].iloc[-1])
        krw_5d_ago = float(usdkrw_hist['Close'].iloc[-6])
        krw_surge = (curr_krw - krw_5d_ago) / krw_5d_ago * 100
        krw_rsi = calc_rsi(usdkrw_hist['Close'], 14)
        
        if krw_surge >= 2.0 or (krw_rsi and krw_rsi >= 70):
            alerts.append(("🔴", f"환율 단기 폭등 (+{krw_surge:.1f}%, RSI {krw_rsi:.1f}) — 외국인 순매도 엑소더스 징후."))
            danger_count += 2
        elif krw_surge >= 1.0 or (krw_rsi and krw_rsi >= 60):
            alerts.append(("🟠", f"환율 상승세 (+{krw_surge:.1f}%) — 외국인 수급 악화 주의."))
            danger_count += 1
        else:
            alerts.append(("🟢", f"환율 안정적 ({curr_krw:,.1f}원) — 외인 수급 이탈 우려 낮음."))'''

    kr_new = '''    # 1. 환율 급변동 (외국인 자본 이탈 강력 프록시)
    if not usdkrw_hist.empty and len(usdkrw_hist) >= 20:
        curr_krw = float(usdkrw_hist['Close'].iloc[-1])
        krw_5d_ago = float(usdkrw_hist['Close'].iloc[-6])
        krw_surge = (curr_krw - krw_5d_ago) / krw_5d_ago * 100
        krw_rsi = calc_rsi(usdkrw_hist['Close'], 14)
        krw_ma20 = float(usdkrw_hist['Close'].rolling(20).mean().iloc[-1])
        
        # 민감도 상향: 5일 1.5% 급등 또는 MA20 상향 이탈
        if krw_surge >= 1.5 or (curr_krw > krw_ma20 and krw_rsi and krw_rsi >= 65):
            alerts.append(("🔴", f"환율 단기 폭등/추세이탈 (+{krw_surge:.1f}%, RSI {krw_rsi:.1f}) — 외국인 엑소더스 징후."))
            danger_count += 2
        elif krw_surge >= 0.8 or (krw_rsi and krw_rsi >= 55):
            alerts.append(("🟠", f"환율 상승세 (+{krw_surge:.1f}%) — 외국인 수급 악화 조기 경보."))
            danger_count += 1
        else:
            alerts.append(("🟢", f"환율 안정적 ({curr_krw:,.1f}원) — 외인 수급 이탈 우려 낮음."))'''
            
    content = content.replace(kr_old, kr_new)

    # 5. UI Layout
    ui_old = '''    st.markdown("#### 🧭 시장 진단 시스템 v21.0 — 이중 레이어 구조")
    st.info(
        "**📌 이 시스템은 두 가지 질문에 각각 답합니다.**\\n\\n"
        "**[레이어 1] 위험 탐지기** — *'지금 폭락이 시작되려는가?'* "
        "상승/횡보장에서도 작동. 미국/한국 시장 특성에 맞춘 별도 지표로 위기 초입을 잡아내는 경보등.\\n\\n"
        "**[레이어 2] 바닥 탐지기** — *'지금 이 하락이 바닥인가?'* "
        "낙폭이 클수록 점수 상승. **고점권에서 점수가 낮은 건 정상입니다.** "
        "점수가 50%를 넘으면 분할매수, 70%를 넘길 때가 강력 매수 타이밍입니다."
    )

    # ── 레이어 1: 위험 탐지기 (미국/한국 분리) ──
    st.markdown("##### 🚨 레이어 1: 위험 탐지기 (지금 폭락 초입인가?)")
    us_risk_grade, us_risk_color, us_risk_alerts = calculate_us_risk_radar(vix_10y, vix3m_10y, hyg_10y, ief_10y, spy_10y)
    kr_risk_grade, kr_risk_color, kr_risk_alerts = calculate_kr_risk_radar(vkospi_10y, usd_krw, kospi_10y)

    c_risk1, c_risk2 = st.columns(2)
    with c_risk1:
        st.markdown(f"<div style='background:{us_risk_color}22; border-left: 4px solid {us_risk_color}; padding:10px; border-radius:6px; font-weight:bold;'>{us_risk_grade}</div>", unsafe_allow_html=True)
        for icon, msg in us_risk_alerts:
            st.markdown(f"<div style='font-size:0.9em; margin-top:5px;'>{icon} {msg}</div>", unsafe_allow_html=True)
    with c_risk2:
        st.markdown(f"<div style='background:{kr_risk_color}22; border-left: 4px solid {kr_risk_color}; padding:10px; border-radius:6px; font-weight:bold;'>{kr_risk_grade}</div>", unsafe_allow_html=True)
        for icon, msg in kr_risk_alerts:
            st.markdown(f"<div style='font-size:0.9em; margin-top:5px;'>{icon} {msg}</div>", unsafe_allow_html=True)'''

    ui_new = '''    st.markdown("#### 🧭 시장 진단 시스템 v22.0 — 글로벌 통합 매크로 구조")
    st.info(
        "**📌 글로벌 킬 스위치 시스템:**\\n\\n"
        "**[마스터 레이어] 미국 글로벌 매크로** — 전 세계 자본 시장의 유동성을 대변하는 신용 스프레드와 VIX, SPY 추세를 교차 검증합니다. "
        "단순 차익 실현이 아닌 '시스템 위기'로 판독되면 킬 스위치가 작동합니다.\\n\\n"
        "**[종속 레이어] 한국 수급 탐지기** — 글로벌이 평온해도, 한국 시장 내 외국인 자본 이탈(환율 발작, 파생 베팅)을 조기 경보합니다."
    )

    # ── 레이어 1: 위험 탐지기 (미국 마스터 / 한국 보조) ──
    st.markdown("##### 🚨 글로벌 매크로 & 로컬 수급 위험 탐지기")
    us_risk_grade, us_risk_color, us_risk_alerts = calculate_us_risk_radar(vix_10y, vix3m_10y, hyg_10y, ief_10y, spy_10y)
    kr_risk_grade, kr_risk_color, kr_risk_alerts = calculate_kr_risk_radar(vkospi_10y, usd_krw, kospi_10y)

    st.markdown(f"<div style='background:{us_risk_color}22; border-left: 6px solid {us_risk_color}; padding:15px; border-radius:8px; font-weight:bold; font-size:1.1em; margin-bottom:10px;'>🇺🇸 [글로벌 마스터] {us_risk_grade}</div>", unsafe_allow_html=True)
    for icon, msg in us_risk_alerts:
        st.markdown(f"<div style='font-size:0.95em; margin-left:15px; margin-bottom:5px;'>{icon} {msg}</div>", unsafe_allow_html=True)
        
    st.markdown("<br>", unsafe_allow_html=True)
    
    st.markdown(f"<div style='background:{kr_risk_color}22; border-left: 4px solid {kr_risk_color}; padding:10px; border-radius:6px; font-weight:bold; margin-bottom:10px;'>🇰🇷 [로컬 종속 레이어] {kr_risk_grade}</div>", unsafe_allow_html=True)
    for icon, msg in kr_risk_alerts:
        st.markdown(f"<div style='font-size:0.9em; margin-left:15px; margin-bottom:3px;'>{icon} {msg}</div>", unsafe_allow_html=True)'''

    content = content.replace(ui_old, ui_new)
    
    content = content.replace('v21.0', 'v22.0')

    with open('final.py', 'w', encoding='utf-8') as f:
        f.write(content)
        
    print("Patch applied.")

patch()
