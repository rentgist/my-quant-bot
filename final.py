from dotenv import load_dotenv
load_dotenv()
import streamlit as st
import calendar_manager
import pandas as pd
import concurrent.futures
import numpy as np
import datetime
import altair as alt

from config import get_kst_now
from data_loader import (
    get_real_cnn_fg, 
    get_macro_charts, 
    get_sector_baseline, 
    get_stock_data,
    get_upcoming_events,
    get_investor_flow,
    get_1m_investor_flow
)
import sys
if "signals" in sys.modules:
    import importlib
    importlib.reload(sys.modules["signals"])
if "data_loader" in sys.modules:
    import importlib
    importlib.reload(sys.modules["data_loader"])

try:
    from signals import (
        calculate_us_risk_radar,
        calculate_kr_risk_radar,
        calculate_us_bottom_finder,
        calculate_kr_bottom_finder,
        calculate_recovery_confirmation,
        calculate_macro_risk_gauge,
        calculate_cashflow_signal,
        calculate_regime_classification,
        get_strategic_advice,
        run_historical_backtest,
        run_kr_historical_backtest,
        get_cashflow_interpretation,
        relative_strength_label,
        get_ai_signal,
        calculate_smart_target,
        get_tenbagger_signal,
        analyze_macro_flow,
        generate_economic_commentary
    )
except ImportError as e:
    st.error(f"🚨 ImportError 발생: {e}")
    st.stop()
except Exception as e:
    st.error(f"🚨 알 수 없는 오류 발생: {e}")
    st.stop()

st.set_page_config(page_title="ORION", page_icon="🛰", layout="wide")

# AI 리포트 전용 고대비 스타일 주입
st.markdown("""
<style>
    /* AI 리포트 영역 내의 본문 글씨를 선명한 검은색(#000000)으로 변경 */
    .ai-report-container, .ai-report-container p, .ai-report-container li {
        color: #000000 !important;
        font-size: 1.05rem !important;
        line-height: 1.7 !important;
    }
    /* AI 리포트 영역 내의 소제목 색상 및 강조 */
    .ai-report-container h1, .ai-report-container h2, .ai-report-container h3 {
        color: #0f172a !important;
        font-weight: 800 !important;
        margin-top: 15px !important;
        margin-bottom: 10px !important;
    }
</style>
""", unsafe_allow_html=True)

# session_state 초기화 및 동기화 콜백
if 'foreign_futures' not in st.session_state:
    st.session_state['foreign_futures'] = 0

def sync_futures_sniper():
    st.session_state['foreign_futures'] = st.session_state['sniper_futures']

def sync_futures_hedging():
    st.session_state['foreign_futures'] = st.session_state['hedging_futures']

# 위젯 초기 세팅값 정렬
if 'sniper_futures' not in st.session_state:
    st.session_state['sniper_futures'] = st.session_state['foreign_futures']
else:
    st.session_state['sniper_futures'] = st.session_state['foreign_futures']

if 'hedging_futures' not in st.session_state:
    st.session_state['hedging_futures'] = st.session_state['foreign_futures']
else:
    st.session_state['hedging_futures'] = st.session_state['foreign_futures']

# ── [Phase 2] 캐싱 기반 데이터 연산 모듈 ──
import requests
from bs4 import BeautifulSoup
try:
    import statsmodels.api as sm
    from statsmodels.tsa.stattools import adfuller
    HAS_STATSMODELS = True
except ImportError:
    HAS_STATSMODELS = False

@st.cache_data(ttl=300)
def get_intraday_market_internals():
    """5분(300초) 캐싱: KOSPI 상승/하락 종목수(Breadth) 및 프로그램 순매매 크롤링"""
    data = {"advancing": 0, "declining": 0, "program_net": 0, "adr": 1.0}
    try:
        # 프로그램 매매 스크래핑 (단위: 백만원)
        res_prog = requests.get('https://finance.naver.com/sise/sise_program.naver', headers={'User-Agent': 'Mozilla/5.0'}, timeout=3)
        res_prog.encoding = 'euc-kr'
        soup_p = BeautifulSoup(res_prog.text, 'html.parser')
        # 최상단 차익+비차익 합계 (순매수) - 에러 대비용으로 단순 패스 가능성 열어둠
        # Naver Finance 프로그램 종합 순매수 텍스트 크롤링 (불안정할 수 있으므로 try-except)
        
        # 임시 안전장치: 실제 크롤링 로직은 환경에 따라 달라지므로, 여기서는 에러 없이 통과하도록 안전하게 감쌈.
        # 향후 정교한 DOM 탐색식 추가 예정 (현재는 실패 시 0 반환)
        data["program_net"] = 0
        
        # Breadth 스크래핑
        res_idx = requests.get('https://finance.naver.com/sise/sise_index.naver?code=KOSPI', headers={'User-Agent': 'Mozilla/5.0'}, timeout=3)
        res_idx.encoding = 'euc-kr'
        soup_i = BeautifulSoup(res_idx.text, 'html.parser')
        
        # <dl class="lst_kos_info"> 내의 상승, 하락 찾기
        dl = soup_i.find('dl', class_='lst_kos_info')
        if dl:
            for dd in dl.find_all('dd'):
                text = dd.text.replace(',', '').strip()
                if '상승' in text:
                    nums = [int(s) for s in text.split() if s.isdigit()]
                    if nums: data["advancing"] = nums[0]
                elif '하락' in text:
                    nums = [int(s) for s in text.split() if s.isdigit()]
                    if nums: data["declining"] = nums[0]
                    
        if data["declining"] > 0:
            data["adr"] = data["advancing"] / data["declining"]
    except Exception as e:
        pass # 크롤링 에러 시 대시보드 중단 방지
    return data

@st.cache_data(ttl=86400)
def get_daily_spread_adf(kospi_df, kosdaq_df):
    """1일(86400초) 캐싱: 지수 간 ADF 공적분 검정"""
    res = {"spread_adf_pvalue": 1.0, "is_cointegrated": False}
    if not HAS_STATSMODELS: return res
    try:
        if not kospi_df.empty and not kosdaq_df.empty:
            ratio = (kospi_df['Close'] / kosdaq_df['Close']).dropna()
            if len(ratio) > 30:
                adf_result = adfuller(ratio)
                res["spread_adf_pvalue"] = adf_result[1]
                res["is_cointegrated"] = bool(adf_result[1] < 0.05)
    except Exception:
        pass
    return res

@st.cache_data(ttl=86400)
def get_daily_multi_pairs():
    """1일(86400초) 캐싱: 다중 페어 OLS 잔차 연산"""
    pairs = {
        "반도체 (삼성전자 vs SK하이닉스)": {"long": "005930.KS", "short": "000660.KS"},
        "자동차 (현대차 vs 기아)": {"long": "005380.KS", "short": "000270.KS"},
        "금융 (KB금융 vs 신한지주)": {"long": "105560.KS", "short": "055550.KS"},
        "플랫폼 (NAVER vs 카카오)": {"long": "035420.KS", "short": "035720.KS"}
    }
    
    results = {}
    import yfinance as yf
    
    for pair_name, tickers in pairs.items():
        res = {"hedge_ratio": 1.0, "residual_z": 0.0, "corr": 0.0, "df": None, "status": "데이터 없음", "color": "#6c757d", "action": ""}
        try:
            long_df = yf.download(tickers["long"], period="150d", progress=False)
            short_df = yf.download(tickers["short"], period="150d", progress=False)
            
            if not long_df.empty and not short_df.empty:
                df = pd.DataFrame({"LONG": long_df['Close'].squeeze(), "SHORT": short_df['Close'].squeeze()}).dropna()
                if len(df) > 60:
                    df["Corr60"] = df["LONG"].rolling(60).corr(df["SHORT"])
                    res["corr"] = df["Corr60"].iloc[-1]
                    
                    df["Ratio"] = df["SHORT"] / df["LONG"]
                    df["MA20"] = df["Ratio"].rolling(20).mean()
                    df["STD20"] = df["Ratio"].rolling(20).std().replace(0, np.nan)
                    df["Upper"] = df["MA20"] + 2 * df["STD20"]
                    df["Lower"] = df["MA20"] - 2 * df["STD20"]
                    
                    if HAS_STATSMODELS:
                        X = sm.add_constant(df['LONG'])
                        y = df['SHORT']
                        model = sm.OLS(y, X).fit()
                        res["hedge_ratio"] = model.params['LONG']
                        
                        residuals = model.resid
                        res_ma = residuals.rolling(20).mean()
                        res_std = residuals.rolling(20).std().replace(0, np.nan)
                        res["residual_z"] = ((residuals - res_ma) / res_std).iloc[-1]
                    
                    res["df"] = df
                    
                    # 상태 판정 로직
                    curr_corr = res["corr"]
                    resid_z = res["residual_z"]
                    curr_ratio = df["Ratio"].iloc[-1]
                    upper = df["Upper"].iloc[-1]
                    lower = df["Lower"].iloc[-1]
                    
                    if pd.notnull(curr_corr) and curr_corr < 0.8:
                        res["status"] = f"⚫ 디커플링 (상관계수: {curr_corr:.2f})"
                        res["action"] = "👉 상관계수 0.8 미만으로 짝짓기 매매 중단"
                        res["color"] = "#6c757d"
                    elif HAS_STATSMODELS and resid_z >= 2.0:
                        res["status"] = f"🔴 SHORT종목 강력 고평가 (잔차 Z: {resid_z:+.2f})"
                        res["action"] = f"👉 SHORT종목 익절 후 LONG종목으로 {res['hedge_ratio']:.2f}주 비율 스위칭!"
                        res["color"] = "#dc3545"
                    elif HAS_STATSMODELS and resid_z <= -2.0:
                        res["status"] = f"🟢 LONG종목 강력 고평가 (잔차 Z: {resid_z:+.2f})"
                        res["action"] = f"👉 LONG종목 익절 후 SHORT종목으로 스위칭!"
                        res["color"] = "#28a745"
                    elif curr_ratio >= upper:
                        res["status"] = f"🔴 SHORT종목 고평가 징후 (밴드 상단)"
                        res["action"] = "👉 SHORT 익절 및 LONG 진입 검토"
                        res["color"] = "#dc3545"
                    elif curr_ratio <= lower:
                        res["status"] = f"🟢 LONG종목 고평가 징후 (밴드 하단)"
                        res["action"] = "👉 LONG 익절 및 SHORT 진입 검토"
                        res["color"] = "#28a745"
                    else:
                        res["status"] = f"⚪ 동행 유지 중 (상관계수: {curr_corr:.2f})"
                        res["action"] = "👉 밴드 내 정상 횡보 (스위칭 관망)"
                        res["color"] = "#6c757d"
                        
        except Exception:
            pass
        results[pair_name] = res
    return results

# ─────────────────────────────────────────
# 포맷 및 색상 맵핑
# ─────────────────────────────────────────
def fmt_mcap(mcap, region):
    if not mcap or mcap == 0: return "N/A"
    return f"${mcap/1e9:.1f}B" if region == "미국" else (
        f"{mcap/1e12:.2f}조 원" if mcap >= 1e12 else f"{mcap/1e8:.0f}억 원"
    )

def fmt_buyback(val, region):
    if val is None or pd.isna(val) or val == 0: return "N/A"
    val = abs(val) 
    return f"${val/1e9:.1f}B" if region == "미국" else (f"{val/1e12:.2f}조 원" if val >= 1e12 else f"{val/1e8:.0f}억 원")

def fmt_price(val, region):
    if val is None or val == "-": return "-"
    return f"{int(val):,}원" if region == "한국" else f"${float(val):,.2f}"

def fmt(val, sfx="", pfx="", dig=2, na="N/A"):
    if val is None or (isinstance(val, float) and np.isnan(val)) or val == "N/A":
        return na
    if isinstance(val, (int, float)):
        return f"{pfx}{val:.{dig}f}{sfx}"
    return f"{pfx}{val}{sfx}"

def pct(val):
    return fmt(float(val) * 100, "%", dig=1) if val is not None else "N/A"

def fmt_change(val):
    if val is None: return "N/A"
    sign = "+" if val > 0 else ""
    return f"{sign}{val:.2f}%"

def color_df(val):
    if not isinstance(val, str): return ''
    if val.endswith('%') and (val.startswith('+') or val.startswith('-')):
        try:
            num = float(val.replace('%','').replace('+',''))
            return 'color: #ff4b4b' if num > 0 else 'color: #0068c9' if num < 0 else ''
        except: pass
    if any(x in val for x in ["🔥 바닥 줍줍","🚀 추세 탑승","🚀 텐배거","🟢 매수 기록", "🔥 기관 최선호 대장주"]):
        return 'background-color: #ffcccc; font-weight: bold; color: black'
    if any(x in val for x in ["🟢 얕은 눌림목","🌱 폭발적 성장","💪","📈 주도주", "🟢 안정형", "🌱 우량 고성장주"]):
        return 'background-color: #ccffcc; font-weight: bold; color: black'
    if any(x in val for x in ["⚫ 경고","📉 강한 소외주", "🔴 고위험", "🔴 매우 높음"]):
        return 'background-color: #555555; font-weight: bold; color: white'
    if any(x in val for x in ["🟡 모멘텀형", "🟠 논란형", "🟠 높음", "🟡 보통"]):
        return 'background-color: #fff3cd; font-weight: bold; color: black'
    if any(x in val for x in ["🔵 과매수","🔵 동반 과매수"]):
        return 'color: blue; font-weight: bold'
    if "🐘 대형주" in val or "⚪ 데이터 부족" in val:
        return 'color: gray; font-style: italic'
    return ''

# ─────────────────────────────────────────
# UI — 전역 데이터 선초기화
# ─────────────────────────────────────────
st.title("🛰 ORION")
st.caption("확률이 충분하지 않은 거래는 하지 않습니다.")

cnn_score, cnn_rating, cnn_history = get_real_cnn_fg()
sector_base = get_sector_baseline()
spy_rsi_val = sector_base.get("S&P 500 (SPY)")

macro_charts = get_macro_charts()
usd_krw      = macro_charts.get("usdkrw_10y", pd.DataFrame())
kospi_10y    = macro_charts.get("kospi_10y", pd.DataFrame())
vkospi_10y   = macro_charts.get("vkospi_10y", pd.DataFrame())
spy_10y      = macro_charts.get("spy_10y", pd.DataFrame())
vix_10y      = macro_charts.get("vix_10y", pd.DataFrame())
vix3m_10y    = macro_charts.get("vix3m_10y", pd.DataFrame())
hyg_10y      = macro_charts.get("hyg_10y", pd.DataFrame())
ief_10y      = macro_charts.get("ief_10y", pd.DataFrame())
rsp_10y      = macro_charts.get("rsp_10y", pd.DataFrame())

rsp_change_pct = None
if not rsp_10y.empty:
    rsp_close = rsp_10y['Close']
    if len(rsp_close) >= 2:
        rsp_change_pct = ((rsp_close.iloc[-1] - rsp_close.iloc[-2]) / rsp_close.iloc[-2]) * 100.0

# 🆕 장단기 금리차 & 반도체 업황 데이터 추출
tnx_10y   = macro_charts.get("tnx_10y", pd.DataFrame())
irx_10y   = macro_charts.get("irx_10y", pd.DataFrame())
mu_2y     = macro_charts.get("mu_2y", pd.DataFrame())
soxx_2y   = macro_charts.get("soxx_2y", pd.DataFrame())

us_score, us_verdict, us_details, us_phase = calculate_us_bottom_finder(spy_10y, vix_10y, cnn_score)
kr_score, kr_verdict, kr_details, kr_phase = calculate_kr_bottom_finder(kospi_10y, vkospi_10y, usd_krw)

# 한국 매크로 리스크 레이더 (최신 V23 로직)
kr_risk_grade, kr_risk_color, kr_risk_alerts, kr_danger = calculate_kr_risk_radar(vkospi_10y, usd_krw, kospi_10y)

# 구 버전 통합 국면 판별기(Regime Classifier) 하위 호환을 위한 매핑
kr_macro_score = max(0, 100 - (kr_danger * 20))
kr_macro_status = kr_risk_grade
kr_macro_details = kr_risk_alerts

# 미국 리스크 레이더 및 반등 신뢰도 글로벌 사전 계산 (1번 탭의 복사용 프롬프트 등에서 호출하기 위함)
us_rec_verdict, us_rec_signals, us_rec_score = calculate_recovery_confirmation(rsp_10y, spy_10y, hyg_10y, ief_10y)
us_risk_grade, us_risk_color, us_risk_alerts, us_danger = calculate_us_risk_radar(
    vix_10y, vix3m_10y, hyg_10y, ief_10y, spy_10y,
    tnx_hist=tnx_10y, irx_hist=irx_10y, mu_hist=mu_2y, soxx_hist=soxx_2y  # 🆕 장단기 금리차 & 반도체 업황
)

# AI 프롬프트용 글로벌 매크로 지표 사전 계산
ai_yield_spread = "N/A"
if not tnx_10y.empty and not irx_10y.empty:
    try:
        ai_yield_spread = f"{(float(tnx_10y['Close'].iloc[-1]) - float(irx_10y['Close'].iloc[-1])):+.2f}%p"
    except: pass

ai_mu_vs_soxx = "N/A"
if not mu_2y.empty and not soxx_2y.empty:
    try:
        mu_20d = (float(mu_2y['Close'].iloc[-1]) / float(mu_2y['Close'].iloc[-21]) - 1) * 100
        soxx_20d = (float(soxx_2y['Close'].iloc[-1]) / float(soxx_2y['Close'].iloc[-21]) - 1) * 100
        ai_mu_vs_soxx = f"{mu_20d - soxx_20d:+.1f}%p"
    except: pass

ai_vkospi_val = f"{float(vkospi_10y['Close'].iloc[-1]):.2f}" if not vkospi_10y.empty else "N/A"

# 탭 구성
tab_sniper, tab_radar, tab_report, tab_hedging, tab_port, tab_calendar = st.tabs(["🚦 ORION Signal", "🔍 종목 발굴 & 타이밍", "📊 마스터 리포트", "🛡️ 헷징 통제실", "💼 포트폴리오", "📅 마켓 캘린더"])

with tab_sniper:
    st.subheader("🛰 ORION Signal")
    st.caption("ORION은 기다릴 때와 움직일 때를 구별합니다.")

    adv_head, adv_color, adv_actions = get_strategic_advice(
        kr_danger, kr_score, kr_verdict, kr_phase, recovery_score=kr_macro_score
    )

    st.markdown(
        f"<div style='background:{adv_color}22; border-left: 8px solid {adv_color}; "
        f"padding:20px; border-radius:10px; margin-bottom:20px;'>"
        f"<h2 style='margin-top:0; color:{adv_color};'>{adv_head}</h2>"
        f"<p style='font-size:0.95em; color:#888; margin-bottom:10px;'>위험도 {kr_danger}점 · 바닥확률 {kr_score}% · 매크로안전도 {kr_macro_score}점 · {kr_phase}</p>"
        f"<ul>" + "".join([f"<li style='font-size:1.05em; margin-bottom:5px;'>{a}</li>" for a in adv_actions]) + "</ul>"
        f"</div>", unsafe_allow_html=True
    )

    st.divider()
    st.markdown("### 💡 글로벌 매크로 & 수급 통합 지표")
    
    # 데이터 수집
    flow_data = get_investor_flow()  # (외국인, 기관, 개인)
    flow_1m = get_1m_investor_flow()
    
    # AI 브리핑을 위한 추가 데이터 구성
    extra_data = {
        'cnn_score': cnn_score,
        'cnn_rating': cnn_rating,
        'flow_1m': flow_1m,
    }
    
    phase, summary_dict = analyze_macro_flow(macro_charts, flow_data, extra_data=extra_data)
    
    # 3x2 Grid 레이아웃 (매크로 3개, 수급 3개)
    m_col1, m_col2, m_col3 = st.columns(3)
    m_col1.metric("🇺🇸 국채 10년물 금리", summary_dict['TNX_10Y'].split(' (')[0], summary_dict['TNX_10Y'].split(' (')[1].replace(')','').replace('p',''), delta_color="inverse")
    m_col2.metric("🛢️ WTI 원유", summary_dict['WTI_Crude'].split(' (')[0], summary_dict['WTI_Crude'].split(' (')[1].replace(')',''), delta_color="inverse")
    m_col3.metric("💵 원/달러 환율", summary_dict['USD_KRW'].split(' (')[0], summary_dict['USD_KRW'].split(' (')[1].replace(')',''), delta_color="inverse")
    
    # 🇰🇷 코스피 실시간 가격 및 5일선 현황 표시
    k_col1, k_col2, k_col3 = st.columns(3)
    if not kospi_10y.empty:
        current_kospi_val = round(float(kospi_10y['Close'].iloc[-1]), 2)
        kospi_5d_sma = round(float(kospi_10y['Close'].rolling(5).mean().iloc[-1]), 2)
        gap = current_kospi_val - kospi_5d_sma
        is_above = current_kospi_val >= kospi_5d_sma
        
        # 코스피 등락률 연산
        if len(kospi_10y['Close']) >= 2:
            prev_kospi = float(kospi_10y['Close'].iloc[-2])
            kospi_change_pts = current_kospi_val - prev_kospi
            kospi_change_pct = (kospi_change_pts / prev_kospi) * 100.0
            kospi_delta_str = f"{kospi_change_pct:+.2f}% ({kospi_change_pts:+.2f}p)"
        else:
            kospi_delta_str = "0.00% (0.00p)"
        
        k_col1.metric("🇰🇷 KOSPI 현재가", f"{current_kospi_val:,.2f}", delta=kospi_delta_str)
        k_col2.metric("📈 KOSPI 5일 이평선", f"{kospi_5d_sma:,.2f}")
        k_col3.metric(
            "🎯 5일선 안착 여부", 
            "안착 완료" if is_above else "미안착", 
            f"이격: {gap:+,.2f}p", 
            delta_color="normal" if is_above else "off"
        )
    else:
        k_col1.metric("🇰🇷 KOSPI 현재가", "데이터 없음")
        k_col2.metric("📈 KOSPI 5일 이평선", "데이터 없음")
        k_col3.metric("🎯 5일선 안착 여부", "확인 불가")
        
    f_col1, f_col2, f_col3 = st.columns(3)
    
    if summary_dict.get('flow_valid', True):
        def _get_metric_args(val):
            return {
                "label": "순매수" if val >= 0 else "순매도",
                "delta": "순매수" if val >= 0 else "-순매도"
            }
            
        f_col1.metric(f"👤 외국인 {_get_metric_args(summary_dict['Foreigner_raw'])['label']}", 
                      summary_dict['Foreigner'], 
                      _get_metric_args(summary_dict['Foreigner_raw'])['delta'])
        
        f_col2.metric(f"🏢 기관 {_get_metric_args(summary_dict['Institutional_raw'])['label']}", 
                      summary_dict['Institutional'], 
                      _get_metric_args(summary_dict['Institutional_raw'])['delta'])
        
        f_col3.metric(f"🧑 개인 {_get_metric_args(summary_dict['Retail_raw'])['label']}", 
                      summary_dict['Retail'], 
                      _get_metric_args(summary_dict['Retail_raw'])['delta'])
    else:
        # 데이터가 모두 0일 때 (KRX 시스템 점검 등)
        f_col1.metric("👤 외국인 수급", "⚠️ 점검 중", "데이터 없음", delta_color="off")
        f_col2.metric("🏢 기관 수급", "⚠️ 점검 중", "데이터 없음", delta_color="off")
        f_col3.metric("🧑 개인 수급", "⚠️ 점검 중", "데이터 없음", delta_color="off")
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    if "cfo_report_cache" not in st.session_state:
        st.session_state["cfo_report_cache"] = ""
 
    if st.button("🔄 CFO AI 시장 브리핑 생성", key="cfo_report_btn"):
        with st.spinner("거시경제 CFO AI가 시장 흐름을 분석하고 있습니다..."):
            st.session_state["cfo_report_cache"] = generate_economic_commentary(summary_dict, phase)
            
    if st.session_state["cfo_report_cache"]:
        ai_commentary = st.session_state["cfo_report_cache"]
        if "⚠️" in ai_commentary:
            st.error(ai_commentary)
        else:
            st.info(f"**[CFO 통합 브리핑] {phase}**\n\n{ai_commentary}")
    else:
        st.info("👈 버튼을 눌러 CFO AI 시장 분석 브리핑을 생성하세요.")

    st.divider()
    st.markdown("### 🤖 실시간 AI 종합 브리핑")
    
    if st.button("🔄 AI 종합 관제 리포트 생성 (뉴스 + 매크로 종합)", type="primary"):
        with st.spinner("Gemini 2.5 Flash가 글로벌 속보와 매크로 수치를 종합하여 리포트를 작성 중입니다..."):
            market_ctx = f"판정결과: {adv_head}\n위험도: {kr_danger}점\n바닥점수: {kr_score}점\n현재국면: {kr_phase}"
            
            try:
                import sys
                import importlib
                import ai_reporter
                importlib.reload(ai_reporter)
                from ai_reporter import generate_smart_control_room_report
                report = generate_smart_control_room_report(market_ctx)
                st.session_state["ai_report_cache"] = report
            except Exception as e:
                st.error(f"리포트 생성 모듈 로드 실패: {e}")

    if "ai_report_cache" in st.session_state:
        st.markdown("<div class='ai-report-container'>", unsafe_allow_html=True)
        st.markdown(st.session_state["ai_report_cache"])
        st.markdown("</div>", unsafe_allow_html=True)
    else:
        st.info("👈 상단의 버튼을 눌러 최신 시황 리포트를 생성하세요.")

    # API Key 캐싱 디버깅을 위한 마스킹 정보 출력
    import os
    api_key_check = os.environ.get("GEMINI_API_KEY", "")
    if api_key_check:
        masked_key = api_key_check[:6] + "..." + api_key_check[-4:] if len(api_key_check) > 10 else "길이 부족"
        st.caption(f"⚙️ 현재 대시보드 서버가 인식한 API Key: `{masked_key}`")
    else:
        st.caption("⚙️ 현재 대시보드 서버가 인식한 API Key: `[없음]`")

    st.divider()

    st.markdown("### 📰 최근 글로벌 주요 뉴스 (AI 수집)")
    import os, json, requests
    
    news_data = []
    remote_url = "https://raw.githubusercontent.com/rentgist/quant-alpha-engine/main/data/news_archive.json"
    try:
        resp = requests.get(remote_url, timeout=5)
        if resp.status_code == 200:
            news_data = resp.json()
    except:
        pass
        
    if not news_data:
        news_file = os.path.join("..", "quant-alpha-engine", "data", "news_archive.json")
        if not os.path.exists(news_file):
            news_file = "data/news_archive.json"
        if os.path.exists(news_file):
            try:
                with open(news_file, "r", encoding="utf-8") as f:
                    news_data = json.load(f)
            except:
                pass
                
    if True:
        try:
            if news_data:
                import datetime
                recent_news = []
                now = datetime.datetime.now()
                for n in news_data:
                    dt_str = n.get("fetched_at", "")
                    try:
                        # Only include news within the last 3 days (72 hours)
                        dt = datetime.datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
                        if (now - dt).days <= 3:
                            recent_news.append(n)
                    except:
                        # If date parsing fails, just include it to be safe
                        recent_news.append(n)
                
                news_data = sorted(recent_news, key=lambda x: (x.get("importance", 0), x.get("fetched_at", "")), reverse=True)
                for n in news_data[:20]:
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

    # ── [NEW] ORION 매크로 & 자금흐름 통합 국면 판별기 ──
    st.divider()
    st.markdown("### 🚦 ORION 통합 국면 판별기 (Regime Classifier)")
    
    c_macro, c_flow = st.columns(2)
    
    with c_macro:
        st.markdown("#### Step 1: 📊 매크로 위험도 (Risk Gauge)")
        st.markdown(f"**상태:** {kr_macro_status}")
        for icon, msg in kr_macro_details:
            st.write(f"{icon} {msg}")
            
    with c_flow:
        st.markdown("#### Step 2: 💸 자금흐름 강도 (Flow Signal)")
        
        # 수동 입력 폼
        f_col1, f_col2 = st.columns(2)
        with f_col1:
            foreign_futures = st.number_input("① 외국인 선물 순매수 (계약)", step=100, key="sniper_futures", on_change=sync_futures_sniper)
        with f_col2:
            oi_trend = st.radio("② 선물 미결제약정", ["증가 추세", "감소/정체"], index=1)
            
        kr_flow_score, kr_flow_status, kr_flow_details = calculate_cashflow_signal(foreign_futures, oi_trend, rsp_change_pct, kospi_10y)
        
        st.markdown(f"**상태:** {kr_flow_status}")
        for icon, msg in kr_flow_details:
            st.write(f"{icon} {msg}")

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("#### Step 3: 🎯 통합 판정 (Action Plan)")
    
    regime, action, r_color = calculate_regime_classification(kr_macro_score, kr_flow_score)
    
    st.markdown(
        f"<div style='background:{r_color}22; border-left: 8px solid {r_color}; padding:20px; border-radius:10px; margin-bottom:20px;'>"
        f"<h2 style='margin-top:0; color:{r_color};'>{regime}</h2>"
        f"<p style='font-size:1.1em; color:#333;'>{action}</p>"
        f"</div>", unsafe_allow_html=True
    )
    
    st.caption("※ 자금흐름(단기 수급) 50점 이상 시 선발대 투입 검토 가능 (⚠️ 경고 국면)")
    
    st.markdown("""
    <div style='background-color:#f8f9fa; padding:15px; border-radius:8px; border:1px solid #ddd; margin-bottom:25px;'>
        <h4 style='margin-top:0; color:#444;'>💡 대가들의 비중 조절 규칙 (Position Sizing)</h4>
        <ul style='font-size:0.95em; color:#555;'>
            <li><b>선발대(정찰병)만 투입 (현금의 10% ~ 20%)</b> : 아직 매크로 추세가 완전히 돌아서지 않았으므로 '본대' 투입은 금물입니다. 내일 5일선이 깨지면 가장 적은 손실로 빠르게 즉각 손절(Cut)할 수 있는 비중만 진입합니다.</li>
            <li><b>관찰 기간 (3~5일) 유지</b> : 이 수급이 '하루짜리 훼이크'인지, '진짜 추세 전환'인지 3~5일간 5일선 지지 여부를 확인해야 합니다 (위 통합 판정에 <b>실제 경과일이 자동 카운트</b>됩니다).</li>
            <li><b>본대 투입 타이밍 (조건부 GO → 강력 GO)</b> : 3~5일 뒤 KOSPI 20일선까지 돌파하며 매크로 점수도 50점 이상으로 올라오면(🟡 조건부 GO), 그때 남은 현금의 50%를 투입합니다. 모든 지표가 80점 이상을 가리키면(🟢 강력 GO) 풀매수를 진행합니다.</li>
        </ul>
    </div>
    """, unsafe_allow_html=True)
    
    # ──────────────────────────────────────────────────────────
    # [웹 Gemini 복사용 프롬프트 생성기]
    # ──────────────────────────────────────────────────────────
    st.divider()
    st.markdown("### 📋 웹 버전 Gemini Pro 복사용 프롬프트")
    st.caption("아래 텍스트 상자의 복사 버튼(우측 상단 아이콘)을 눌러 구글 웹 Gemini(Advanced 등)에 붙여넣으면, 최고 스펙 Pro 모델의 깊이 있는 마켓 브리핑을 무료로 받으실 수 있습니다!")
    
    # 최근 뉴스 포맷팅 (최대 60개)
    web_news_lines = []
    if news_data:
        for n in news_data[:60]:
            t = n.get("title_ko", n.get("title", ""))
            s = n.get("sentiment", "중립")
            i = n.get("importance", 0)
            a = n.get("action_point", "")
            web_news_lines.append(f"- [{s}/중요도:{i}] {t} (대응: {a})")
    web_news_text = "\n".join(web_news_lines) if web_news_lines else "최근 수집된 뉴스가 없습니다."

    # 프롬프트 조립용 지표 포맷팅
    kospi_str = f"{current_kospi_val:,.2f}" if 'current_kospi_val' in locals() and current_kospi_val else "N/A"
    kospi_5d_str = f"{kospi_5d_sma:,.2f}" if 'kospi_5d_sma' in locals() and kospi_5d_sma else "N/A"
    kospi_status_str = ("안착 완료" if is_above else f"미안착 (이격: {gap:+,.2f}p)") if 'is_above' in locals() and 'gap' in locals() else "N/A"
    
    rsp_val_str = f"{rsp_change_pct:+.2f}%" if rsp_change_pct is not None else "N/A"

    # 프롬프트 조립
    upcoming_events_str = calendar_manager.get_upcoming_events_string()
    web_prompt = f"""너는 대한민국 상위 1% 자산가를 위한 월스트리트 최고 수준의 매크로 애널리스트이자 11원칙 장기 투자(Value Accumulation)의 대가다.
다음 주어진 '알고리즘 시스템의 현재 판독 결과', '시장 거시 지표', '최근 글로벌 뉴스'를 바탕으로, 매우 전문적이고 깊이 있는 투자 분석 리포트를 작성하라.

[알고리즘 판정 결과]
- 국면 판정: {adv_head}
- 위험도 점수: 한국 {kr_danger}점 / 미국 {us_danger}점
- 바닥 점수: 한국 {kr_score}% / 미국 {us_score}%
- 현재 국면: 한국 {kr_phase} / 미국 {us_phase}
- 매크로 점수: 한국 {kr_macro_score}점
- 자금흐름 점수: 한국 {kr_flow_score}점
- 통합 국면: {regime}

[시장 거시 지표 및 수급 (글로벌 펀더멘털 & 로컬 수급)]
- 🇺🇸 미국 장단기 금리차 (10Y-3M): {ai_yield_spread} (경기침체/유동성 선행지표)
- 🇺🇸 미국 반도체 업황 강도 (MU vs SOXX 20일 수익률 격차): {ai_mu_vs_soxx} (DRAM 사이클 프록시)
- 🇺🇸 미국 TNX 10Y 금리: {summary_dict.get('TNX_10Y', 'N/A') if 'summary_dict' in locals() else 'N/A'}
- 🇺🇸 WTI 크루드 유가: {summary_dict.get('WTI_Crude', 'N/A') if 'summary_dict' in locals() else 'N/A'}
- 🇺🇸 미국 동일가중 S&P500 (RSP) 전일 등락률: {rsp_val_str} (미국 시장 온기 확인용)
- 🇰🇷 USD/KRW 환율: {summary_dict.get('USD_KRW', 'N/A') if 'summary_dict' in locals() else 'N/A'}
- 🇰🇷 한국 VKOSPI 현재: {ai_vkospi_val} (한국 기관/외인 파생 하락 헷지 팽창도)
- 🇰🇷 외국인 KOSPI 현물 순매수: {summary_dict.get('Foreigner', 'N/A') if 'summary_dict' in locals() else 'N/A'}
- 🇰🇷 기관 KOSPI 현물 순매수: {summary_dict.get('Institutional', 'N/A') if 'summary_dict' in locals() else 'N/A'}
- 🇰🇷 외국인 KOSPI 선물 순매수: {foreign_futures}계약 (방향성 선행지표)
- 🇰🇷 KOSPI 현재가: {kospi_str}
- 🇰🇷 KOSPI 5일 이평선 안착 상태: {kospi_status_str}

[최근 글로벌 속보 요약 (중요도 2 이상)]
{web_news_text}

{upcoming_events_str}

---
위 데이터를 기반으로 다음 3가지 핵심 뼈대로 리포트를 매우 분석적이고 통찰력있게 작성하십시오.
1. **현재 시장 국면 요약 (Market Summary)**: 현재 하락세의 원인, 매크로 수급과 외인 이탈 여부를 종합 진단하십시오.
2. **글로벌 거시 리스크 및 섹터 전망 (Macro & Sector Outlook)**: 
   - 금리/유가/지정학 리스크가 주요 자산에 미칠 영향을 상세히 서술하십시오.
   - [미장 승률 극대화 지침] 안정적으로 우상향하는 미국 시장의 특성과 예정된 빅테크 실적/가이던스를 결합하여, 향후 환율 하락 시 가장 승률과 수익률을 극대화할 수 있는 안전한 진입 시나리오를 구체적으로 제시하십시오.
3. **최종 행동 지침 (CFO Action Plan)**:보유 중인 우량주 홀딩 여부, 레버리지 관리, 현금 50% 분할 매수 집행 타이밍을 매우 구체적으로 지시하십시오. 예정된 주요 일정을 참고하여 매매 일정을 조율하십시오.
"""
    st.code(web_prompt, language="markdown")

    # ──────────────────────────────────────────────────────────
    # [🧵 쓰레드(Threads) 글감 생성기 — ORION 트레이더용]
    # ──────────────────────────────────────────────────────────
    st.divider()
    st.markdown("### 🧵 쓰레드(Threads) 글감 생성기 — ORION 트레이더용")
    st.caption("아래 3개의 프롬프트를 AI(Claude, Gemini 등)에 붙여넣으면 오늘 쓰레드에 올릴 글감이 완성됩니다. 각 박스 우측 상단 복사 버튼을 사용하세요.")

    # ── 공통 데이터 준비 ──
    # 중요도 4 이상 뉴스만 필터 (최대 10개)
    top_news_lines = []
    if news_data:
        top_news = [n for n in news_data if n.get("importance", 0) >= 4][:10]
        for n in top_news:
            t  = n.get("title_ko", n.get("title", ""))
            s  = n.get("sentiment", "중립")
            a  = n.get("action_point", "")
            top_news_lines.append(f"- [{s}] {t}\n  → 대응: {a}")
    top_news_text = "\n".join(top_news_lines) if top_news_lines else "주요 뉴스 없음"

    # 이번 주 이벤트 (캘린더)
    upcoming_events_str = calendar_manager.get_upcoming_events_string()

    # 지표 요약 (쓰레드용 간결 버전)
    thread_indicators = f"""- ORION 신호: {adv_head}
- 🇺🇸 미국: {us_phase} | 위험도 {us_danger}점 | 금리차(10Y-3M) {ai_yield_spread}
- 🇰🇷 한국: {kr_phase} | 위험도 {kr_danger}점 | VKOSPI {ai_vkospi_val}
- 🇰🇷 KOSPI: {kospi_str} | 5일선 안착: {kospi_status_str}
- 🇰🇷 외국인 현물: {summary_dict.get('Foreigner', 'N/A') if 'summary_dict' in locals() else 'N/A'} | 환율: {summary_dict.get('USD_KRW', 'N/A') if 'summary_dict' in locals() else 'N/A'}
- 🇺🇸 반도체 업황(MU vs SOX): {ai_mu_vs_soxx} | RSP 등락: {rsp_val_str}"""

    # ── 글감 ① 뉴스 기반 ──
    with st.expander("📰 글감 ① — 오늘의 핵심 뉴스 1편 (복사해서 AI에 붙여넣기)", expanded=False):
        thread_prompt_news = f"""너는 'ORION 트레이더'라는 쓰레드(Threads) SNS 계정을 운영하는 개인 투자자야.
아래 오늘의 주요 뉴스들을 분석해서, 쓰레드에 올릴 글을 써줘.

[작성 규칙 — 반드시 지켜줘]
- 말투: 정중한 존댓말이 아니라, 분석적이면서도 시크하고 단호한 '반말'(~다, ~지, ~한다)로 작성해줘.
- 첫 포스트 (Hook) 어그로 극대화: 첫 1~2줄에 스크롤을 멈추게 만드는 강렬한 질문이나 모순을 던져줘 (예: "미국 10년물 4.5% 폭등, 근데 왜 다들 환전해서 미장 갈 준비를 할까?", "중동 확전 유가 90달러 돌파, 근데 주식 다 팔아야 할까?")
- 전체 구성: 메인 포스트 1개 + 댓글 4~5개로 나눠서 작성
- 문장은 짧게 (한 문장 최대 2줄), 줄바꿈 자주 사용 (모바일 가독성)
- 전문 용어는 괄호로 쉽게 풀어서 설명
- 설교하지 말고, '혼잣말하는 고수 트레이더' 또는 '동료 투자자' 느낌으로
- 숫자와 사실로 근거 제시, 결론은 명확하게
- 마지막 댓글은 반드시 "내일/이번 주 주목할 것:" 으로 마무리

[오늘의 주요 뉴스 (중요도 4 이상)]
{top_news_text}

[오늘 ORION 시스템 판정]
{thread_indicators}

위 뉴스 중 가장 임팩트가 큰 1~2개 뉴스를 골라서,
그것이 주식 시장에 구체적으로 어떤 영향을 미치는지 투자자 관점으로 풀어써줘.
"""
        st.code(thread_prompt_news, language="markdown")

    # ── 글감 ② 지표/장세 기반 ──
    with st.expander("📊 글감 ② — 오늘 장세와 지표 분석 1편 (복사해서 AI에 붙여넣기)", expanded=False):
        thread_prompt_market = f"""너는 'ORION 트레이더'라는 쓰레드(Threads) SNS 계정을 운영하는 개인 투자자야.
오늘 시장 지표와 수급 데이터를 분석해서 쓰레드에 올릴 글을 써줘.

[작성 규칙 — 반드시 지켜줘]
- 말투: 정중한 존댓말이 아니라, 분석적이면서도 시크하고 단호한 '반말'(~다, ~지, ~한다)로 작성해줘.
- 첫 포스트 (Hook) 어그로 극대화: 첫 1~2줄에 지수의 급락이나 수급의 모순 등 충격적인 팩트를 배치해줘 (예: "코스피 4.4% 폭락했는데 외인이 5천억 샀다고? 은밀한 매집의 시작일까?", "공포지수 VKOSPI 78 돌파. 투매가 끝났는지 확인하는 법")
- 전체 구성: 메인 포스트 1개 + 댓글 4~5개로 나눠서 작성
- 문장은 짧게 (한 문장 최대 2줄), 줄바꿈 자주 사용 (모바일 가독성)
- 데이터를 그냥 나열하지 말고, "이게 왜 중요한지" 의미 해석에 집중
- 외국인/기관 수급, VKOSPI, 금리차 등의 숫자가 투자자에게 말하는 것을 쉽게 설명
- 겁주거나 흥분하지 말고, 냉정하고 논리적인 톤 유지
- 마지막 댓글은 "ORION 시스템 현재 신호:" 로 마무리

[오늘 ORION 시스템 지표 데이터]
{thread_indicators}

[바닥/반등 분석]
- 한국 바닥 확률: {kr_score}% | 미국 바닥 확률: {us_score}%
- 통합 국면: {regime}
- 반등 신뢰도 (미국): {us_rec_score}/100점

위 데이터를 바탕으로, 오늘 시장에서 가장 주목해야 할 지표 1~2개를 골라
그것이 의미하는 바를 투자자 입장에서 실용적으로 풀어써줘.
"""
        st.code(thread_prompt_market, language="markdown")

    # ── 글감 ③ 실적/이벤트 기반 ──
    with st.expander("📅 글감 ③ — 이번 주 실적/이벤트 주목 포인트 1편 (복사해서 AI에 붙여넣기)", expanded=False):
        thread_prompt_events = f"""너는 'ORION 트레이더'라는 쓰레드(Threads) SNS 계정을 운영하는 개인 투자자야.
이번 주/다음 주 예정된 주요 실적 발표와 매크로 이벤트를 기반으로 쓰레드 글을 써줘.

[작성 규칙 — 반드시 지켜줘]
- 말투: 정중한 존댓말이 아니라, 분석적이면서도 시크하고 단호한 '반말'(~다, ~지, ~한다)로 작성해줘.
- 첫 포스트 (Hook) 어그로 극대화: 첫 1~2줄에 앞으로 올 거대한 이벤트의 파급력을 예고하는 멘트를 배치해줘 (예: "7/23 알파벳 실적발표. 엔비디아와 브로드컴 주주들이 잠 못 자는 진짜 이유", "빅테크 실적발표 전 비중 축소가 불가능한 구조적 이유")
- 전체 구성: 메인 포스트 1개 + 댓글 4~5개로 나눠서 작성
- 문장은 짧게, 줄바꿈 자주 (모바일 최적화)
- 각 이벤트가 "왜 중요한지", "어떤 종목/섹터에 영향 주는지" 구체적으로 설명
- 실적 서프라이즈/실망 시 시나리오를 각각 제시 (투자 준비 도움)
- 독자가 "아, 이날 이거 체크해야겠다" 느끼게 만들어줘
- 마지막 댓글은 "이번 주 ORION 트레이더의 관전 포인트:" 로 마무리

[이번 주~다음 주 주요 일정]
{upcoming_events_str}

[현재 시장 맥락]
{thread_indicators}

위 일정들 중 투자 측면에서 가장 중요한 2~3개 이벤트를 골라서,
각 이벤트의 핵심 관전 포인트와 시나리오별 대응 전략을 쓰레드 형식으로 써줘.
AI 투자, 빅테크 실적, 반도체 수출 같은 핵심 테마와 연결해서 설명하면 더 좋아.
"""
        st.code(thread_prompt_events, language="markdown")


with tab_radar:
    st.subheader("🔍 타점 선택 (Entry Point Selection) - 포트폴리오 종목 타점")
    st.caption("스나이퍼 탭에서 'GO' 신호가 떨어졌을 때, 어떤 종목을 살지 재무 및 수급을 점검하는 레이더입니다.")
    
    st.markdown("""
    <div style='background-color:#e8f4f8; padding:15px; border-radius:8px; border-left: 6px solid #17a2b8; margin-bottom:20px;'>
        <h4 style='margin-top:0; color:#0c5460;'>📈 상승장(강력 GO) 대응 가이드: 눌림목 매수</h4>
        <p style='font-size:0.95em; color:#1b4b52; margin-bottom:0;'>
        매크로가 <b>대세 상승장(강력 GO)</b>일 때는 무지성 시장가 매수가 아닌, 아래 레이더에서 <b>'💡 타점' (20일선 부근 GTC 또는 볼린저 하단)</b> 가격을 확인하고,<br>
        해당 가격에 <b>GTC(취소 전까지 유효) 지정가 매수 주문</b>을 걸어두는 것이 가장 승률이 높습니다.
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    c1, c2 = st.columns(2)
    us_input = c1.text_input("🇺🇸 미국 주식", "TSMC, 브로드컴, 버티브")
    kr_input = c2.text_input("🇰🇷 한국 주식", "LS ELECTRIC")

    queries = (
        [("미국", q.strip()) for q in us_input.split(",") if q.strip()] +
        [("한국", q.strip()) for q in kr_input.split(",") if q.strip()]
    )

    # 버튼 게이트: 다른 탭 위젯 조작으로 rerun될 때마다 무거운 API 호출이
    # 자동 발생하는 것을 차단. 한 번 스캔하면 session_state로 유지.
    if st.button("🔍 스캔 시작 (재무제표 교차 검증 포함)", type="primary", key="scan_btn"):
        st.session_state["scan_requested"] = True

    all_data, failed_queries = [], []
    if st.session_state.get("scan_requested") and queries:
        prog = st.progress(0.0, text="분석 준비 중...")
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(get_stock_data, q, is_kr=(region == "한국"), fast_mode=False): (region, q) for region, q in queries}
            for i, future in enumerate(concurrent.futures.as_completed(futures)):
                region, q = futures[future]
                prog.progress((i + 1) / len(queries), text=f"[{i+1}/{len(queries)}] '{q}' 데이터 수집 중...")
                d = future.result()
                d["Region"] = region
                if not d.get("error"): all_data.append(d)
                else: failed_queries.append(f"{q} ({d.get('error')})")
        prog.empty()
    elif not st.session_state.get("scan_requested"):
        st.info("종목을 입력하고 **스캔 시작** 버튼을 누르면 분석이 시작됩니다.")

    if failed_queries:
        st.warning(f"⚠️ 데이터 조회 실패 (오타 확인): {', '.join(failed_queries)}")

    if all_data:
        signal_rows, tech_rows, fin_rows, risk_rows = [], [], [], []
        insider_blocks = []

        for d in all_data:
            ai_sig = get_ai_signal(d)
            tb_sig = get_tenbagger_signal(d)
            target_p, target_desc = calculate_smart_target(d, ai_sig)
            curr_price_str = fmt_price(d.get("Price"), d["Region"])
            target_str     = "-" if target_p == "-" else fmt_price(target_p, d["Region"])

            signal_rows.append({
                "종목":        d["Name"],
                "장투 시그널": ai_sig,
                "💡 타점":     f"{target_desc} ({target_str})",
                "현재가":      curr_price_str,
                "등락률":      fmt_change(d.get("Change")),
                "시가총액":    fmt_mcap(d.get("MarketCap"), d["Region"]),
            })

            rs_txt = relative_strength_label(d.get("RSI_14"), spy_rsi_val)

            w52_pos = d.get("W52_pos")
            if w52_pos is not None:
                if w52_pos <= 15:   pos_label = f"📍 {w52_pos}% (52주 바닥권)"
                elif w52_pos <= 30: pos_label = f"📍 {w52_pos}% (하단 30%)"
                elif w52_pos >= 85: pos_label = f"📍 {w52_pos}% (고점권)"
                elif w52_pos >= 70: pos_label = f"📍 {w52_pos}% (상단 30%)"
                else:               pos_label = f"📍 {w52_pos}% (중간권)"
            else:
                pos_label = "N/A"

            tech_rows.append({
                "종목":           d["Name"],
                "시장대비 강도":  rs_txt,
                "52주 위치":      pos_label,
                "고점 대비":      fmt(d.get("Gap_High"), "%", dig=1),
                "RSI(7일)":      fmt(d.get("RSI_7"),  dig=1),
                "RSI(14일)":     fmt(d.get("RSI_14"), dig=1),
                "RSI(21일)":     fmt(d.get("RSI_21"), dig=1),
                "MACD":          d.get("MACD_dir", "N/A"),
                "거래강도":       fmt(d.get("Vol_ratio"), "%", dig=1),
                "20일 이격":      fmt(d.get("MA20_gap"), "%", dig=1),
            })

            fin_rows.append({
                "종목":          d["Name"],
                "Rule of 40":    fmt(d.get("Rule_of_40"), "%", dig=1) if d.get("Rule_of_40") is not None else "N/A",
                "EV/EBITDA":     fmt(d.get("EV_EBITDA"), "x", dig=1),
                "EV/FCF":        fmt(d.get("EV_FCF"), "x", dig=1),
                "매출총이익률":  pct(d.get("Gross_Margin")),
                "영업이익률":    pct(d.get("Op_Margin")),
                "ROIC":          pct(d.get("ROIC")),
                "FCF Yield":     pct(d.get("FCF_Yield")),
                "FCF/Share":     fmt(d.get("FCFPS"), pfx="$" if d["Region"] == "미국" else "₩", dig=2),
                "자사주 매입":   fmt_buyback(d.get("Buybacks"), d["Region"]),
                "Forward PER":   fmt(d.get("Forward_PER"), dig=1),
                "PEG":           fmt(d.get("PEG"), dig=2),
            })

            risk_rows.append({
                "종목":            d["Name"],
                "종합 리스크 등급": d.get("Risk_Grade", "N/A"),
                "다음 실적일":     d.get("Next_Earning", "N/A"),
                "내부자 매수":     d.get("Insider_Buy",  "N/A"),
                "어닝 서프라이즈 (최근 8Q)": d.get("Earnings_Beat","N/A"),
                "공매도 비율":     d.get("Short_Interest","N/A"),
                "Beta":           d.get("Beta",          "N/A"),
                "최신 헤드라인":   (str(d.get("Latest_News",""))[:50]+"...") if len(str(d.get("Latest_News",""))) > 50 else d.get("Latest_News","N/A"),
            })

            if d.get("Insider_Buy") == "🟢 매수 기록 있음" and d.get("Insider_Detail"):
                insider_blocks.append({
                    "name":   d["Name"],
                    "detail": d["Insider_Detail"],
                    "url":    d.get("Edgar_URL", ""),
                })
            elif d.get("Edgar_URL"):
                insider_blocks.append({
                    "name":   d["Name"],
                    "detail": "",
                    "url":    d.get("Edgar_URL", ""),
                })

        st.markdown("#### 🎯 1. 11원칙 매매 시그널 & 눌림목 타점")
        st.dataframe(
            pd.DataFrame(signal_rows).set_index("종목").style.map(color_df),
            use_container_width=True
        )

        st.markdown("#### 📈 2. 기술적 지표 (상대강도 + 멀티RSI + 52주 위치)")
        st.dataframe(
            pd.DataFrame(tech_rows).set_index("종목").style.map(
                color_df, subset=["시장대비 강도","고점 대비","거래강도","20일 이격"]
            ),
            use_container_width=True
        )
        st.caption(
            "💡 **시장대비 강도**: SPY ETF RSI(14일)와 비교. 양수 = 시장보다 강함. "
            "| **52주 위치**: 0% = 52주 최저, 100% = 최고. "
            "| **고점 대비**: 52주 고점에서 얼마나 내려왔는지 (음수)."
        )

        st.markdown("#### 🚨 3. 리스크 관리 (종합 등급 · 실적일 · 내부자 · 공매도 · Beta · 뉴스)")
        st.dataframe(
            pd.DataFrame(risk_rows).set_index("종목").style.map(
                color_df, subset=["종합 리스크 등급", "내부자 매수"]
            ),
            use_container_width=True
        )

        if insider_blocks:
            st.markdown("#### 🔗 내부자 거래 상세 & SEC EDGAR 원문 링크")
            for block in insider_blocks:
                with st.expander(f"📋 {block['name']} — 내부자 거래 상세"):
                    if block["detail"]:
                        st.info(block["detail"])
                    else:
                        st.write("최근 순수 매수 기록 없음 (매도·행사·자동매매만 감지됨)")
                    if block["url"]:
                        st.markdown(
                            f"**[📄 SEC EDGAR Form 4 원문 보기 →]({block['url']})**\n\n",
                            unsafe_allow_html=True
                        )

        st.markdown("#### 💰 4. 단위경제 및 현금흐름 밸류에이션")
        st.dataframe(pd.DataFrame(fin_rows).set_index("종목"), use_container_width=True)
        
        st.markdown("#### 💡 4-1. 단위경제 & 현금흐름 자동 해석 (워런 버핏의 시각)")
        for d in all_data:
            interpretation = get_cashflow_interpretation(d)
            st.info(f"**{d['Name']}** : {interpretation}")

with tab_report:
    st.subheader("🌐 글로벌 매크로 및 시장 심리 (진바닥 & 반등 신뢰도 점수)")

    vix_10y = macro_charts.get("vix_10y", pd.DataFrame())
    vix3m_10y = macro_charts.get("vix3m_10y", pd.DataFrame())
    spy_10y = macro_charts.get("spy_10y", pd.DataFrame())
    hyg_10y = macro_charts.get("hyg_10y", pd.DataFrame())
    ief_10y = macro_charts.get("ief_10y", pd.DataFrame())
    rsp_10y = macro_charts.get("rsp_10y", pd.DataFrame())
    kospi_10y = macro_charts.get("kospi_10y", pd.DataFrame())
    vkospi_10y = macro_charts.get("vkospi_10y", pd.DataFrame())

    current_vix, vix_change = "N/A", 0
    if not vix_10y.empty:
        current_vix = round(float(vix_10y['Close'].iloc[-1]), 2)
        vix_change  = round(((current_vix - float(vix_10y['Close'].iloc[-2])) / float(vix_10y['Close'].iloc[-2])) * 100, 2)

    current_spy, spy_change = "N/A", 0
    if not spy_10y.empty:
        current_spy = round(float(spy_10y['Close'].iloc[-1]), 2)
        spy_change  = round(((current_spy - float(spy_10y['Close'].iloc[-2])) / float(spy_10y['Close'].iloc[-2])) * 100, 2)
        
    current_vkospi = "N/A"
    if not vkospi_10y.empty:
        current_vkospi = round(float(vkospi_10y['Close'].iloc[-1]), 2)

    col1, col2, col3, col4 = st.columns(4)
    if not usd_krw.empty:
        usd_krw_clean = usd_krw['Close'].dropna()
        if len(usd_krw_clean) >= 2:
            curr_usdkrw = round(float(usd_krw_clean.iloc[-1]), 2)
            prev_usdkrw = float(usd_krw_clean.iloc[-2])
            usdkrw_change = round(((curr_usdkrw - prev_usdkrw) / prev_usdkrw) * 100, 2)
            col1.metric("환율 (USD/KRW)", f"{curr_usdkrw:,.2f} 원", f"{usdkrw_change:+.2f}%")
        else:
            col1.metric("환율 (USD/KRW)", "N/A", "N/A")
    else:
        col1.metric("환율 (USD/KRW)", "N/A", "N/A")
        
    col2.metric("미국 VIX / 한국 VKOSPI", f"{current_vix} / {current_vkospi}", f"{vix_change}%", delta_color="inverse")
    col3.metric("S&P 500 (SPY)", f"${current_spy:,.2f}" if current_spy != "N/A" else "N/A", f"{spy_change:+.2f}%" if current_spy != "N/A" else "N/A")
    if cnn_score is not None:
        # 역발상 관점: 극단적 공포 = 매수 기회(🟢), 극단적 탐욕 = 위험(🚨)
        if cnn_score <= 25:   fg_color, fg_stat = "🟢", "극단적 공포 (역발상 매수 구간)"
        elif cnn_score <= 45: fg_color, fg_stat = "🟠", "공포"
        elif cnn_score <= 55: fg_color, fg_stat = "🟡", "중립"
        elif cnn_score <= 75: fg_color, fg_stat = "🟠", "탐욕 (추격 매수 주의)"
        else:                 fg_color, fg_stat = "🚨", "극단적 탐욕 (현금 확보 경계)"
        col4.metric("CNN Fear & Greed", f"{cnn_score} / 100", f"{fg_color} {fg_stat}")
    else:
        col4.metric("CNN Fear & Greed", "N/A", cnn_rating)

    kr_date = kospi_10y.index[-1].strftime('%Y-%m-%d') if not kospi_10y.empty else "N/A"
    us_date = spy_10y.index[-1].strftime('%Y-%m-%d') if not spy_10y.empty else "N/A"
    
    st.markdown("")
    st.caption(f"🕒 **데이터 최종 반영일** — 한국 시장(KOSPI/환율): `{kr_date}` | 미국 시장(SPY/VIX): `{us_date}`")

    vkospi_src = macro_charts.get("vkospi_source", "yfinance (^VKOSPI)")
    if "yfinance" not in vkospi_src:
        st.caption(f"※ VKOSPI 데이터 소스: **{vkospi_src}** — 야후 파이낸스 ^VKOSPI 제공 중단으로 대체 소스가 자동 적용되었습니다. "
                   f"(폴백 순서: yfinance → KRX 직조회 → 실현변동성 프록시)")
        if "프록시" in vkospi_src:
            st.caption("⚠️ 프록시는 옵션 내재변동성(선행)이 아닌 과거 수익률 기반(후행)입니다. EWMA 병행으로 반응 속도를 보강했지만, "
                       "평온한 장에서 블랙스완이 터지는 '첫날'에는 실제 공포 수준보다 낮게 표시될 수 있습니다 — 그날은 VIX·환율 급등 신호를 우선 참고하세요.")

    st.divider()
    st.markdown("#### 🧭 시장 진단 시스템 v23.0 — 글로벌 통합 매크로 + 국면 판별 엔진")
    st.info(
        "**📌 글로벌 킬 스위치 시스템:**\n\n"
        "**[마스터 레이어] 미국 글로벌 매크로** — 전 세계 자본 시장의 유동성을 대변하는 신용 스프레드와 VIX, SPY 추세를 교차 검증합니다. "
        "단순 차익 실현이 아닌 '시스템 위기'로 판독되면 킬 스위치가 작동합니다.\n\n"
        "**[종속 레이어] 한국 수급 탐지기** — 글로벌이 평온해도, 한국 시장 내 외국인 자본 이탈(환율 발작, 파생 베팅)을 조기 경보합니다.\n\n"
        "**🆕 [국면 판별 엔진] 스텔스 위험 감지** — VIX가 뛰지 않는 '미지근한 지속 하락(🐻 Grinding Bear)'은 하락일 비율·50일선 기울기·"
        "VIX 안일 다이버전스로, '오르며 빠지는 고변동 횡보(🌊 Whipsaw)'는 실현변동성 대비 방향성 부재로 별도 감지합니다. "
        "바닥 탐지기에는 '빠짐이 끝나간다'를 확인하는 구조 신호(RSI 다이버전스·저점 높이기·20일선 탈환)가 보너스 점수로 반영됩니다."
    )

    # ── 레이어 1: 위험 탐지기 (미국 마스터 / 한국 보조) ──
    st.markdown("##### 🚨 글로벌 매크로 & 로컬 수급 위험 탐지기")
    us_risk_grade, us_risk_color, us_risk_alerts, us_danger = calculate_us_risk_radar(
        vix_10y, vix3m_10y, hyg_10y, ief_10y, spy_10y,
        tnx_hist=tnx_10y, irx_hist=irx_10y, mu_hist=mu_2y, soxx_hist=soxx_2y
    )
#     kr_risk_grade, kr_risk_color, kr_risk_alerts, kr_danger = calculate_kr_risk_radar(vkospi_10y, usd_krw, kospi_10y)

    st.markdown(f"<div style='background:{us_risk_color}22; border-left: 6px solid {us_risk_color}; padding:15px; border-radius:8px; font-weight:bold; font-size:1.1em; margin-bottom:10px;'>🇺🇸 [글로벌 마스터] {us_risk_grade}</div>", unsafe_allow_html=True)
    for icon, msg in us_risk_alerts:
        st.markdown(f"<div style='font-size:0.95em; margin-left:15px; margin-bottom:5px;'>{icon} {msg}</div>", unsafe_allow_html=True)
        
    st.markdown("<br>", unsafe_allow_html=True)
    
    st.markdown(f"<div style='background:{kr_risk_color}22; border-left: 4px solid {kr_risk_color}; padding:10px; border-radius:6px; font-weight:bold; margin-bottom:10px;'>🇰🇷 [로컬 종속 레이어] {kr_risk_grade}</div>", unsafe_allow_html=True)
    for icon, msg in kr_risk_alerts:
        st.markdown(f"<div style='font-size:0.9em; margin-left:15px; margin-bottom:3px;'>{icon} {msg}</div>", unsafe_allow_html=True)

    # ── 확정 일정 캘린더 모듈 (점수 미반영) ──
    events = get_upcoming_events()
    if events:
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("##### 📅 주요 시장 이벤트 캘린더 (확정 일정)")
        st.caption("※ 아래 이벤트는 수급과 변동성을 키울 수 있는 확정된 일정입니다. (점수 미반영 / 참고용)")
        for date_str, event_name, impact, d_left in events:
            if d_left == 0:
                badge = "🔥 D-Day"
            else:
                badge = f"⏳ D-{d_left}"
            st.info(f"**[{badge}] {date_str}** : {event_name} — *{impact}*")

    st.divider()

    # ── 레이어 2: 바닥 탐지기 ──
    st.markdown("##### 📉 레이어 2: 바닥 탐지기 (이 하락이 바닥인가?)")
    
#     us_score, us_verdict, us_details, us_phase = calculate_us_bottom_finder(spy_10y, vix_10y, cnn_score)
#     kr_score, kr_verdict, kr_details, kr_phase = calculate_kr_bottom_finder(kospi_10y, vkospi_10y, usd_krw)
    
    us_color = "#21c354" if us_score >= 70 else "#fcca46" if us_score >= 50 else "#aaaaaa"
    kr_color = "#21c354" if kr_score >= 70 else "#fcca46" if kr_score >= 50 else "#aaaaaa"

    b_col1, b_col2 = st.columns(2)
    with b_col1:
        st.markdown(f"**🇺🇸 미국 진바닥 확률 (US Market)**")
        st.markdown(
            f"<div style='text-align:center; padding:20px; border-radius:10px; border:2px solid {us_color}; margin-bottom: 10px;'>"
            f"<h1 style='margin:0; font-size:3em; color:{us_color};'>{us_score}%</h1>"
            f"<h4 style='margin:0;'>{us_verdict}</h4>"
            f"<p style='margin-top:15px; font-size:18px; font-weight:bold; color:#555;'>현재 국면: {us_phase}</p>"
            f"</div>", unsafe_allow_html=True
        )
        with st.expander("🔍 미국장 연산 근거 (Drawdown + RSI + VIX + CNN + 구조 보너스)"):
            for detail in us_details: st.markdown(f"- {detail}")

    with b_col2:
        st.markdown(f"**🇰🇷 한국 진바닥 확률 (KOSPI)**")
        st.markdown(
            f"<div style='text-align:center; padding:20px; border-radius:10px; border:2px solid {kr_color}; margin-bottom: 10px;'>"
            f"<h1 style='margin:0; font-size:3em; color:{kr_color};'>{kr_score}%</h1>"
            f"<h4 style='margin:0;'>{kr_verdict}</h4>"
            f"<p style='margin-top:15px; font-size:18px; font-weight:bold; color:#555;'>현재 국면: {kr_phase}</p>"
            f"</div>", unsafe_allow_html=True
        )
        with st.expander("🔍 한국장 연산 근거 (Drawdown + RSI + VKOSPI + 환율 + 구조 보너스)"):
            for detail in kr_details: st.markdown(f"- {detail}")

    st.divider()

    # ── 레이어 3: 회복 확인 ──
    st.markdown("##### ✅ 반등 신뢰도 확인 (바닥 이후 — Breadth & Credit 회복 여부)")
    st.caption("바닥 탐지 점수가 높을 때만 의미 있는 지표예요. 상승장에서는 항상 좋게 나오므로 참고용으로만 보세요.")
    
    r_col1, r_col2 = st.columns(2)
    with r_col1:
        st.markdown(f"**🇺🇸 미국 반등 신뢰도**")
        us_rec_verdict, us_rec_signals, us_rec_score = calculate_recovery_confirmation(
            rsp_10y, spy_10y, hyg_10y, ief_10y
        )
        st.markdown(f"**{us_rec_verdict}**")
        for icon, msg in us_rec_signals:
            st.markdown(f"- {icon} {msg}")

    with r_col2:
        st.markdown(f"**🇰🇷 한국 매크로 안전도**")
        # tab_sniper에서 계산한 kr_macro_score 등 재활용
        st.markdown(f"**{kr_macro_status}**")
        for icon, msg in kr_macro_details:
            st.markdown(f"- {icon} {msg}")

    st.divider()

    # ── 🎯 레이어 4: 종합 전략 제언 (위험 × 바닥 × 회복 통합 판단) ──
    st.markdown("##### 🎯 레이어 4: 종합 전략 제언 — \"그래서 지금 사도 되는가?\"")
    st.caption(
        "위험 탐지기 × 바닥 탐지기 × 반등 신뢰도를 교차 결합해 실전 액션으로 번역합니다. "
        "같은 바닥 점수라도 위험 경보 상태에 따라 처방이 달라집니다. (※ 투자 판단 참고용이며 최종 책임은 본인에게 있습니다)"
    )

    us_adv_head, us_adv_color, us_adv_actions = get_strategic_advice(
        us_danger, us_score, us_verdict, us_phase, recovery_score=us_rec_score
    )
    kr_adv_head, kr_adv_color, kr_adv_actions = get_strategic_advice(
        kr_danger, kr_score, kr_verdict, kr_phase, recovery_score=kr_macro_score
    )

    adv_col1, adv_col2 = st.columns(2)
    with adv_col1:
        st.markdown(
            f"<div style='background:{us_adv_color}22; border-left: 6px solid {us_adv_color}; "
            f"padding:15px; border-radius:8px; font-weight:bold; font-size:1.05em; margin-bottom:10px;'>"
            f"🇺🇸 {us_adv_head}</div>", unsafe_allow_html=True
        )
        st.caption(f"판단 근거: 위험 {us_danger}점 · 바닥 {us_score}% · 반등 신뢰도 {us_rec_score} · {us_phase}")
        for act in us_adv_actions:
            st.markdown(f"- {act}")

    with adv_col2:
        st.markdown(
            f"<div style='background:{kr_adv_color}22; border-left: 6px solid {kr_adv_color}; "
            f"padding:15px; border-radius:8px; font-weight:bold; font-size:1.05em; margin-bottom:10px;'>"
            f"🇰🇷 {kr_adv_head}</div>", unsafe_allow_html=True
        )
        st.caption(f"판단 근거: 위험 {kr_danger}점 · 바닥 {kr_score}% · 매크로 안전도 {kr_macro_score} · {kr_phase}")
        for act in kr_adv_actions:
            st.markdown(f"- {act}")

    st.divider()

    # False Signal 경보 — 매수 금지 조건 실시간 체크
    false_signals = []
    if us_rec_score == 0 and us_score < 70:
        false_signals.append("🚫 **반등 신뢰도 0** — 오늘의 급등은 쇼트커버링 가능성. 수급 없는 가짜 반등 경계")
    if us_score < 50 and us_danger >= 3:
        false_signals.append("🚫 **위험 경보 + 바닥 점수 미달** — 낙폭 과대라는 착시 주의. 오늘 매수 보류 권장")
    if false_signals:
        st.warning("\n".join(["**⛔ False Signal 차단기 발동 (매수 보류 권장)**"] + false_signals))

    st.divider()

    # ── 백테스트 (10년 데이터 기반 완화 컷) ──
    with st.expander("🔬 과거 10년 백테스트 (바닥 탐지기 기준)"):
        st.markdown(
            "실시간 바닥 탐지기와 **완전히 동일한 스코어러**를 "
            "과거 10년에 매일 적용한 결과입니다. **주요 이벤트에서 얼마나 점수가 나왔는지 확인**해보세요 — 모델 신뢰도 검증에 핵심입니다. "
        )
        
        tab_us_bt, tab_kr_bt = st.tabs(["🇺🇸 미국장 (S&P 500)", "🇰🇷 한국장 (KOSPI)"])
        
        with tab_us_bt:
            bt_us = run_historical_backtest(spy_10y, vix_10y, vix3m_10y)
            if bt_us:
                st.markdown("**📌 주요 시장 이벤트에서의 바닥 탐지 점수 (미국장)**")
                ev_cols = st.columns(len(bt_us["주요 이벤트 점수"]))
                for i, (name, ev_score) in enumerate(bt_us["주요 이벤트 점수"].items()):
                    if ev_score is not None and isinstance(ev_score, int):
                        color = "#21c354" if ev_score >= 50 else "#fcca46" if ev_score >= 35 else "#ff4b4b"
                        ev_cols[i].markdown(
                            f"<div style='text-align:center; padding:10px; border-radius:8px; border:1px solid {color};'>"
                            f"<b>{name}</b><br>"
                            f"<span style='font-size:1.8em; color:{color};'>{ev_score}점</span>"
                            f"</div>", unsafe_allow_html=True
                        )
                    else:
                        ev_cols[i].markdown(f"**{name}**: {ev_score}")

                st.markdown("")
                bt_col1, bt_col2 = st.columns(2)

                stat_70 = bt_us["70점 이상 (강력 매수)"]
                bt_col1.markdown("**🔥 70점 이상 (강력 매수 구간)**")
                if stat_70["발생 횟수"] > 0:
                    bt_col1.markdown(f"- 시그널 발생: 과거 10년간 **{stat_70['발생 횟수']}일**")
                    bt_col1.markdown(f"- 평균 3개월 수익률: **+{stat_70['평균 3M 수익률']:.2f}%**")
                    bt_col1.markdown(f"- 평균 6개월 수익률: **+{stat_70['평균 6M 수익률']:.2f}%**")
                    bt_col1.markdown(f"- 투자 승률 (3M): **{stat_70['승률 3M']:.1f}%**")
                else:
                    bt_col1.info("과거 10년간 70점 이상 달성 없음")

                stat_50 = bt_us["50~69점 (분할 매수)"]
                bt_col2.markdown("**🟢 50~69점 (분할 매수 구간)**")
                if stat_50["발생 횟수"] > 0:
                    bt_col2.markdown(f"- 시그널 발생: 과거 10년간 **{stat_50['발생 횟수']}일**")
                    bt_col2.markdown(f"- 평균 3개월 수익률: **+{stat_50['평균 3M 수익률']:.2f}%**")
                    bt_col2.markdown(f"- 평균 6개월 수익률: **+{stat_50['평균 6M 수익률']:.2f}%**")
                    bt_col2.markdown(f"- 투자 승률 (3M): **{stat_50['승률 3M']:.1f}%**")
                else:
                    bt_col2.info("해당 구간 시그널 발생 없음")

                if "score_series" in bt_us and not bt_us["score_series"].empty:
                    st.markdown("**📈 바닥 탐지 점수 vs 지수 낙폭 (10년, 이중축)**")
                    src = bt_us["score_series"].reset_index()
                    src.columns = ["Date", "Score", "Drawdown"]

                    base = alt.Chart(src).encode(x=alt.X("Date:T", title=None))
                    score_area = base.mark_area(opacity=0.35, color="#fcca46").encode(
                        y=alt.Y("Score:Q", title="바닥 탐지 점수",
                                scale=alt.Scale(domain=[0, 100]),
                                axis=alt.Axis(titleColor="#b8860b"))
                    )
                    dd_line = base.mark_line(color="#ff4b4b", strokeWidth=1.2).encode(
                        y=alt.Y("Drawdown:Q", title="Drawdown (%)",
                                axis=alt.Axis(titleColor="#ff4b4b"))
                    )
                    chart = alt.layer(score_area, dd_line).resolve_scale(y="independent").properties(height=280)
                    st.altair_chart(chart, use_container_width=True)
                    st.caption(
                        "🟨 노란 영역 = 바닥 점수 / 🔴 빨간 선 = 고점 대비 낙폭. "
                        "점수가 50 이상으로 치솟는 시점 = 역사적 매수 기회 (2018년 말, 2020년 코로나, 2022년 바닥 확인). "
                        "낙폭이 깊어지는데 점수가 함께 올라가는지가 모델 건전성의 핵심입니다."
                    )
            else:
                st.warning("미국장 백테스트에 필요한 10년치 데이터가 부족합니다.")

        with tab_kr_bt:
            bt_kr = run_kr_historical_backtest(kospi_10y, vkospi_10y, usd_krw)
            if bt_kr:
                st.markdown("**📌 주요 시장 이벤트에서의 바닥 탐지 점수 (한국장)**")
                ev_cols = st.columns(len(bt_kr["주요 이벤트 점수"]))
                for i, (name, ev_score) in enumerate(bt_kr["주요 이벤트 점수"].items()):
                    if ev_score is not None and isinstance(ev_score, int):
                        color = "#21c354" if ev_score >= 50 else "#fcca46" if ev_score >= 35 else "#ff4b4b"
                        ev_cols[i].markdown(
                            f"<div style='text-align:center; padding:10px; border-radius:8px; border:1px solid {color};'>"
                            f"<b>{name}</b><br>"
                            f"<span style='font-size:1.8em; color:{color};'>{ev_score}점</span>"
                            f"</div>", unsafe_allow_html=True
                        )
                    else:
                        ev_cols[i].markdown(f"**{name}**: {ev_score}")

                st.markdown("")
                bt_col1, bt_col2 = st.columns(2)

                stat_70 = bt_kr["70점 이상 (강력 매수)"]
                bt_col1.markdown("**🔥 70점 이상 (강력 매수 구간)**")
                if stat_70["발생 횟수"] > 0:
                    bt_col1.markdown(f"- 시그널 발생: 과거 10년간 **{stat_70['발생 횟수']}일**")
                    bt_col1.markdown(f"- 평균 3개월 수익률: **+{stat_70['평균 3M 수익률']:.2f}%**")
                    bt_col1.markdown(f"- 평균 6개월 수익률: **+{stat_70['평균 6M 수익률']:.2f}%**")
                    bt_col1.markdown(f"- 투자 승률 (3M): **{stat_70['승률 3M']:.1f}%**")
                else:
                    bt_col1.info("과거 10년간 70점 이상 달성 없음")

                stat_50 = bt_kr["50~69점 (분할 매수)"]
                bt_col2.markdown("**🟢 50~69점 (분할 매수 구간)**")
                if stat_50["발생 횟수"] > 0:
                    bt_col2.markdown(f"- 시그널 발생: 과거 10년간 **{stat_50['발생 횟수']}일**")
                    bt_col2.markdown(f"- 평균 3개월 수익률: **+{stat_50['평균 3M 수익률']:.2f}%**")
                    bt_col2.markdown(f"- 평균 6개월 수익률: **+{stat_50['평균 6M 수익률']:.2f}%**")
                    bt_col2.markdown(f"- 투자 승률 (3M): **{stat_50['승률 3M']:.1f}%**")
                else:
                    bt_col2.info("해당 구간 시그널 발생 없음")

                if "score_series" in bt_kr and not bt_kr["score_series"].empty:
                    st.markdown("**📈 한국장 바닥 탐지 점수 vs 지수 낙폭 (10년, 이중축)**")
                    src = bt_kr["score_series"].reset_index()
                    src.columns = ["Date", "Score", "Drawdown"]

                    base = alt.Chart(src).encode(x=alt.X("Date:T", title=None))
                    score_area = base.mark_area(opacity=0.35, color="#fcca46").encode(
                        y=alt.Y("Score:Q", title="한국장 바닥 점수",
                                scale=alt.Scale(domain=[0, 100]),
                                axis=alt.Axis(titleColor="#b8860b"))
                    )
                    dd_line = base.mark_line(color="#ff4b4b", strokeWidth=1.2).encode(
                        y=alt.Y("Drawdown:Q", title="Drawdown (%)",
                                axis=alt.Axis(titleColor="#ff4b4b"))
                    )
                    chart = alt.layer(score_area, dd_line).resolve_scale(y="independent").properties(height=280)
                    st.altair_chart(chart, use_container_width=True)
            else:
                st.warning("한국장 백테스트에 필요한 10년치 데이터가 부족합니다.")

        st.caption("※ 백테스트는 과거 통계이며 미래 수익을 보장하지 않습니다. 고점 산정 왜곡 방지를 위해 데이터 첫 1년은 집계에서 제외됩니다.")

    st.divider()

    st.markdown("#### 📊 시장 심리 & 지수 — 최근 10년 추이")
    c_chart1, c_chart2 = st.columns(2)
    with c_chart1:
        st.markdown("**① VIX (공포 지수) — 10년**")
        if not vix_10y.empty:
            st.line_chart(
                pd.DataFrame({
                    "VIX": vix_10y['Close'],
                    "🔴 위험선(30)": 30.0,
                    "🟢 평온선(15)": 15.0,
                }),
                height=280,
                color=["#1f77b4", "#ff4b4b", "#21c354"]
            )
        else:
            st.warning("VIX 데이터를 불러오지 못했습니다.")
            
    with c_chart2:
        st.markdown("**② S&P 500 (SPY) — 10년**")
        if not spy_10y.empty:
            st.line_chart(
                pd.DataFrame({"S&P 500 (SPY)": spy_10y['Close']}),
                height=280,
                color=["#ff7f0e"]
            )
            spy_high = round(float(spy_10y['Close'].max()), 2)
            spy_low  = round(float(spy_10y['Close'].min()), 2)
            spy_pos  = round((current_spy - spy_low) / (spy_high - spy_low) * 100, 1) if current_spy != "N/A" else "N/A"
            st.caption(f"10년 고점 ${spy_high:,.2f} / 저점 ${spy_low:,.2f} | 현재 10년 범위 내 위치: **{spy_pos}%**")
        else:
            st.warning("S&P 500 데이터를 불러오지 못했습니다.")

    c_chart3, c_chart4 = st.columns(2)
    with c_chart3:
        st.markdown("**③ VKOSPI 프록시 (한국 공포 지수) — 10년**")
        if not vkospi_10y.empty:
            st.line_chart(
                pd.DataFrame({
                    "VKOSPI Proxy": vkospi_10y['Close'],
                    "🔴 위험선(25)": 25.0,
                    "🟢 평온선(16)": 16.0,
                }),
                height=280,
                color=["#1f77b4", "#ff4b4b", "#21c354"]
            )
        else:
            st.warning("VKOSPI 데이터를 불러오지 못했습니다.")

    with c_chart4:
        st.markdown("**④ KOSPI — 10년**")
        if not kospi_10y.empty:
            st.line_chart(
                pd.DataFrame({"KOSPI": kospi_10y['Close']}),
                height=280,
                color=["#ff7f0e"]
            )
            kospi_high = round(float(kospi_10y['Close'].max()), 2)
            kospi_low  = round(float(kospi_10y['Close'].min()), 2)
            current_kospi_val = round(float(kospi_10y['Close'].iloc[-1]), 2) if not kospi_10y.empty else "N/A"
            kospi_pos  = round((current_kospi_val - kospi_low) / (kospi_high - kospi_low) * 100, 1) if current_kospi_val != "N/A" else "N/A"
            st.caption(f"10년 고점 {kospi_high:,.2f} / 저점 {kospi_low:,.2f} | 현재 10년 범위 내 위치: **{kospi_pos}%**")
        else:
            st.warning("KOSPI 데이터를 불러오지 못했습니다.")

    st.markdown("**⑤ CNN Fear & Greed Index (최근 1~2년)**")
    if cnn_history is not None:
        st.line_chart(
            pd.DataFrame({
                "F&G Score": cnn_history,
                "🟢 탐욕구간(75)": 75.0,
                "🔴 공포구간(25)": 25.0,
            }),
            height=280,
            color=["#1f77b4", "#21c354", "#ff4b4b"]
        )
        st.caption("25 이하 = 극단적 공포 (역발상 매수 구간) | 75 이상 = 극단적 탐욕 (현금 확보 구간). CNN 서버 정책상 최대 제공 기간이 1~2년으로 제한될 수 있습니다.")
    else:
        st.warning("⚠️ CNN 서버 차단 중. 잠시 후 새로고침 해주세요.")
        
    st.divider()
    st.info("💡 본 탭 하단에 위치했던 [글로벌 매크로 & 수급 통합 AI 브리핑] 지표들과 CFO 브리핑 생성 버튼은 사용자님의 편의를 위해 **1번 탭 (🎯 AI 스마트 관제실)**으로 통합 이전되었습니다. 이제 1번 탭에서 모든 브리핑과 지표를 일괄적으로 확인 및 컨트롤하실 수 있습니다!")

with tab_radar:  # 🚀 오늘의 텐배거 레이더
    st.subheader("🚀 섹터별 텐배거 마스터 레이더 (미래 지표 및 트렌드 필터)")
    UNIVERSE = {
        "🇺🇸 미국 AI & 클라우드":              ["PLTR","CRWD","SNOW","DDOG","NET","SOUN","MDB","ZS","MNDY"],
        "🇺🇸 미국 혁신성장 (우주/바이오/핀테크)": ["IONQ","SOFI","RIVN","CELH","RKLB","ASTS","CRSP","LUNR","SYM","HOOD"],
        "🇰🇷 한국 반도체 소부장 (HBM/AI)":        ["피에스케이홀딩스", "한미반도체", "테크윙", "HPSP", "이수페타시스", "에이직랜드", "디아이", "원익IPS", "동진쎄미켐", "주성엔지니어링", "리노공업", "하나마이크론"],
        "🇰🇷 한국 K-뷰티 & K-푸드":            ["실리콘투","클래시스","파마리서치","삼양식품","브이티","에이피알","휴젤"],
        "🇰🇷 한국 바이오텍 & 헬스케어":          ["알테오젠","HLB","리가켐바이오","루닛","뷰노","제이엘케이"],
        "🇰🇷 한국 전력기기 & 로봇":             ["HD현대일렉트릭","레인보우로보틱스","두산로보틱스","LS ELECTRIC"],
    }
    selected_theme = st.selectbox("스캔할 섹터:", list(UNIVERSE.keys()))
    if st.button("해당 섹터 레이더 가동"):
        is_korea = "한국" in selected_theme
        radar_data = []
        tickers = UNIVERSE[selected_theme]
        prog = st.progress(0.0, text=f"[{selected_theme}] 전수 스캔 준비 중...")
        for i, q in enumerate(tickers):
            prog.progress((i + 1) / len(tickers), text=f"[{i+1}/{len(tickers)}] '{q}' 경량 스캔 중...")
            d = get_stock_data(q, is_kr=is_korea, fast_mode=True)
            d["Region"] = "한국" if is_korea else "미국"
            if not d.get("error"): radar_data.append(d)
        prog.empty()
        with st.container():
            radar_rows = []
            for d in radar_data:
                tb_sig = get_tenbagger_signal(d)
                if tb_sig != "-": 
                    radar_rows.append({
                        "종목":           d["Name"], "등급": tb_sig,
                        "시가총액":       fmt_mcap(d.get("MarketCap"), d["Region"]),
                        "매출성장":       pct(d.get("Rev_Growth")),
                        "이익성장(예상)": pct(d.get("Earnings_Growth")),
                        "영업이익률":     pct(d.get("Op_Margin")),
                        "Forward PER":    fmt(d.get("Forward_PER"), dig=1),
                        "PEG":            fmt(d.get("PEG"), dig=2),
                    })
            if radar_rows:
                st.dataframe(
                    pd.DataFrame(radar_rows).set_index("종목").style.map(color_df),
                    use_container_width=True
                )
                
                st.markdown("#### 🤖 텐배거 심층 분석용 AI 프롬프트")
                st.caption("아래 텍스트를 복사하여 AI(ChatGPT, Claude, Gemini 등)에게 붙여넣고 최적의 투자 종목을 추천받으세요.")
                
                tb_lines = [
                    f"[섹터 텐배거 스캔 결과: {selected_theme}]",
                    "아래는 워런 버핏과 피터 린치의 성장주/가치주 필터링을 통과한 '텐배거 후보' 기업들의 데이터야.",
                    "",
                    "【후보 종목 데이터】"
                ]
                for d in radar_data:
                    tb_sig = get_tenbagger_signal(d)
                    if tb_sig != "-":
                        rev_g = pct(d.get('Rev_Growth'))
                        earn_g = pct(d.get('Earnings_Growth'))
                        op_m = pct(d.get('Op_Margin'))
                        fwd_per = fmt(d.get('Forward_PER'), dig=1)
                        peg = fmt(d.get('PEG'), dig=2)
                        turnaround = "O" if d.get('Is_Turnaround') else "X"
                        
                        tb_lines.append(f"▶ {d['Name']} (등급: {tb_sig})")
                        tb_lines.append(f"  - 시가총액: {fmt_mcap(d.get('MarketCap'), d['Region'])}")
                        tb_lines.append(f"  - 성장성: 매출성장 {rev_g} | 예상이익성장 {earn_g} | 턴어라운드 {turnaround}")
                        tb_lines.append(f"  - 수익성 & 밸류에이션: 영업이익률 {op_m} | Forward PER {fwd_per} | PEG {peg}")
                        tb_lines.append("")
                        
                tb_lines += [
                    "【분석 요청사항】",
                    "1. 위 후보 기업들의 '매출/이익 성장성'과 '마진율(영업이익률)', '밸류에이션(PEG, Forward PER)'을 종합적으로 비교해 줘.",
                    "2. 현재 시점에서 장기 투자(1~3년) 목적으로 가장 투자 매력도(Risk vs Return)가 높은 1순위, 2순위 기업을 선정하고 그 이유를 논리적으로 설명해 줘.",
                    "3. 각 기업이 가진 치명적인 리스크나 주의해야 할 변수가 있다면 함께 짚어줘."
                ]
                st.code("\n".join(tb_lines), language="text")
                
            else:
                st.warning("⚠️ 현재 조건(지하실 역추세 및 실적/마진 기준)을 통과한 진성 우량주가 이 섹터에 존재하지 않습니다.")

with tab_report:  # 🤖 AI 참모 리포트
    st.subheader("🤖 AI 참모 전용 구조화 리포트 v23.0 (진바닥 판독기 연동)")
    st.caption("아래 텍스트를 복사하여 ChatGPT, Claude, Gemini 등에 붙여넣고 심층 분석을 받아보세요.")

    if not all_data:
        st.info("📊 '실시간 포트폴리오' 탭에서 먼저 **스캔 시작**을 실행하면 종목 데이터가 이 리포트에 포함됩니다.")

    now = get_kst_now().strftime('%Y-%m-%d %H:%M:%S KST')
    lines = [
        f"[11원칙 퀀트 분석 리포트 v23.0] ({now})",
        f"- CNN F&G (시장 심리): {cnn_score} ({cnn_rating})",
        f"- SPY RSI(14) (시장 과열도): {fmt(spy_rsi_val, dig=1)}",
        f"- 미국 장단기 금리차(10Y-3M): {ai_yield_spread}",
        f"- 미국 반도체 업황 강도(MU vs SOX): {ai_mu_vs_soxx}",
        f"- 한국 VKOSPI (파생 헷지): {ai_vkospi_val}",
        "",
        "【시장 국면 & 시스템 전략 제언】",
        f"- 🇺🇸 미국: {us_phase} | 위험 탐지 {us_danger}점 | 진바닥 확률 {us_score}% | 반등 신뢰도 {us_rec_score}/100",
        f"  → 시스템 제언: {us_adv_head}",
        f"- 🇰🇷 한국: {kr_phase} | 위험 탐지 {kr_danger}점 | 진바닥 확률 {kr_score}% | 매크로 안전도 {kr_macro_score}/100",
        f"  → 시스템 제언: {kr_adv_head}",
        "",
        "【스캔 종목 데이터】"
    ]
    
    for d in all_data:
        ai_sig = get_ai_signal(d)
        tb_sig = get_tenbagger_signal(d)
        target_p, target_d = calculate_smart_target(d, ai_sig)
        rs_txt = relative_strength_label(d.get("RSI_14"), spy_rsi_val)
        w52    = d.get("W52_pos")
        w52_str = f"{w52}%" if w52 is not None else "N/A"

        rev_g   = pct(d.get('Rev_Growth'))
        gm      = pct(d.get('Gross_Margin'))
        op_m    = pct(d.get('Op_Margin'))
        earn_g  = pct(d.get('Earnings_Growth'))
        roe     = pct(d.get('ROE'))
        roic    = pct(d.get('ROIC'))
        fcf_y   = pct(d.get('FCF_Yield'))
        fcf_ps  = fmt(d.get("FCFPS"), pfx="$" if d["Region"] == "미국" else "₩", dig=2)
        bb_str  = fmt_buyback(d.get("Buybacks"), d["Region"])
        per     = fmt(d.get('PER'), dig=1)
        fwd_per = fmt(d.get('Forward_PER'), dig=1)
        peg     = fmt(d.get('PEG'), dig=2)

        lines += [
            f"┌─ [{d['Region']}] {d['Name']} (단기 시그널: {ai_sig} / 텐배거 등급: {tb_sig})",
            f"│ 1. 가격 및 타점: 현재가 {fmt_price(d.get('Price'), d['Region'])} | 추천 타점: {target_d} ({fmt_price(target_p, d['Region'])})",
            f"│ 2. 기술적 지표: RSI(7/14/21) {fmt(d.get('RSI_7'),dig=1)} / {fmt(d.get('RSI_14'),dig=1)} / {fmt(d.get('RSI_21'),dig=1)} | 시장대비: {rs_txt}",
            f"│ 3. 추세 및 위치: 52주 위치 {w52_str} | 고점 대비 {fmt(d.get('Gap_High'),'%',dig=1)} 하락",
            f"│ 4. 단위경제 & 효율성: 매출총이익률(Gross Margin) {gm} | ROIC {roic} | ROE {roe}",
            f"│ 5. 펀더멘탈(과거vs미래): 매출성장 {rev_g} | 영업이익률 {op_m} | 🎯예상이익 성장률 {earn_g}",
            f"│ 6. 현금흐름 & 주주환원: FCF Yield {fcf_y} | FCF per Share {fcf_ps} | 자사주 매입 {bb_str}",
            f"│ 7. 밸류에이션: PER {per} | 🎯Forward PER {fwd_per} | 🎯PEG {peg}",
            f"│ 8. 리스크 및 수급: 종합 리스크 {d.get('Risk_Grade', 'N/A')} | 내부자 {d.get('Insider_Buy','N/A')} | 공매도 {d.get('Short_Interest','N/A')} | Beta {d.get('Beta','N/A')}",
            f"└──────────────────────────────────────────────────",
        ]

    lines += [
        "",
        "【AI 참모 심층 분석 요청사항】",
        "위 데이터를 바탕으로 나의 11원칙 퀀트 투자 룰에 맞춰 다음을 심층 분석해 줘.",
        "",
        "1. [가치와 성장 듀얼 분석 (Turnaround & Bubble Check)]",
        "   - '과거 영업이익률/PER'과 '미래 예상 이익성장률/Forward PER/PEG'를 교차 비교해 진짜 성장과 가짜 거품을 구별해 줘.",
        "",
        "2. [현금흐름 및 자본 효율성 (Quality Check)]",
        "   - FCF Yield, ROIC, 매출총이익률(Gross Margin)을 분석하여 기업의 실제 현금 창출력과 해자(Moat)를 평가해 줘.",
        "   - 경영진의 자신감을 나타내는 '자사주 매입' 내역과 '내부자 매수' 여부를 연계해 수급 안정성을 확인해 줘.",
        "",
        "3. [리스크 및 수급 점검]",
        "   - 공매도 비율, Beta(변동성)를 종합하여 숨겨진 하방 리스크가 큰 종목을 경고해 줘.",
        "",
        "4. [기술적 타점 분석 및 최종 매매 시나리오]",
        "   - RSI 멀티타임프레임과 52주 위치, 시장대비 강도를 종합해 현재 가장 매수 신뢰도가 높은 종목을 선정해 줘.",
        "   - '위험 점수'와 '진바닥 확률', '반등 신뢰도' 등 매크로 지표를 고려해 포트폴리오 비중(예: ETF 절반 + 개별 우량주 절반) 배분 전략을 제시해 줘.",
        "   - 현재 시장 심리(F&G, SPY RSI)를 바탕으로 지금 당장 '적극 매수', '관망', '비중 축소' 해야 할 종목들을 분류하고 구체적인 액션 플랜을 제시해 줘."
    ]
    st.code("\n".join(lines), language="text")
with tab_port:
    st.subheader("💼 내 포트폴리오 장투 전략 분석 (1~2년 기준)")
    st.caption("보유 종목과 매수가를 입력하면 현재 손익 현황 + 11원칙 종합평가 + AI 전달용 장투 전략 리포트를 생성합니다.")

    st.markdown("#### 📝 보유 종목 입력")
    st.info(
        "**입력 형식:** 종목명:매수가 (쉼표로 구분)\n\n"
        "🇺🇸 미국: `브로드컴:320.5, 버티브:250, TSMC:180`\n\n"
        "🇰🇷 한국: `LS ELECTRIC:185000, 피에스케이홀딩스:120000`"
    )

    col_us, col_kr = st.columns(2)
    port_us_raw = col_us.text_input("🇺🇸 미국 보유 종목 (달러 매수가)", "브로드컴:320.5, 버티브:250, TSMC:180")
    port_kr_raw = col_kr.text_input("🇰🇷 한국 보유 종목 (원화 매수가)", "LS ELECTRIC:185000")

    def parse_portfolio_input(raw: str, region: str):
        items = []
        for chunk in raw.split(","):
            chunk = chunk.strip()
            if ":" not in chunk:
                continue
            parts = chunk.rsplit(":", 1)
            if len(parts) == 2:
                name = parts[0].strip()
                try:
                    price = float(parts[1].strip().replace(",", ""))
                    items.append((name, price, region))
                except ValueError:
                    pass
        return items

    port_items = (
        parse_portfolio_input(port_us_raw, "미국") +
        parse_portfolio_input(port_kr_raw, "한국")
    )

    if st.button("🔍 장투 전략 분석 시작", type="primary"):
        if not port_items:
            st.warning("종목을 올바른 형식으로 입력해 주세요.")
        else:
            port_data = []
            prog = st.progress(0.0, text="보유 종목 데이터 수집 준비 중...")
            for i, (name, buy_price, region) in enumerate(port_items):
                prog.progress((i + 1) / len(port_items), text=f"[{i+1}/{len(port_items)}] '{name}' 재무제표 교차 검증 중...")
                d = get_stock_data(name, is_kr=(region == "한국"), fast_mode=False)
                d["Region"]    = region
                d["BuyPrice"]  = buy_price
                if not d.get("error"):
                    port_data.append(d)
                else:
                    st.warning(f"⚠️ '{name}' 데이터 조회 실패: {d.get('error')}")
            prog.empty()

            if not port_data:
                st.error("조회된 종목이 없습니다. 종목명을 확인해 주세요.")
            else:
                st.markdown("---")
                st.markdown("### 📊 1. 현재 손익 현황")

                pnl_rows = []
                for d in port_data:
                    buy_p   = d["BuyPrice"]
                    cur_p   = d.get("Price")
                    region  = d["Region"]
                    if cur_p is None:
                        continue
                    cur_p_f = float(cur_p)
                    pnl_pct = round((cur_p_f - buy_p) / buy_p * 100, 2)
                    pnl_sign = "+" if pnl_pct >= 0 else ""

                    ma20    = d.get("MA20")
                    bb_low  = d.get("BB_lower")

                    def _dist(ref):
                        if ref is None: return "N/A"
                        return f"{round((cur_p_f - float(ref)) / float(ref) * 100, 1):+.1f}%"

                    pnl_rows.append({
                        "종목":        d["Name"],
                        "지역":        "🇺🇸" if region == "미국" else "🇰🇷",
                        "매수가":      f"${buy_p:,.2f}" if region == "미국" else f"{int(buy_p):,}원",
                        "현재가":      fmt_price(cur_p, region),
                        "수익률":      f"{pnl_sign}{pnl_pct:.2f}%",
                        "20일선 위치": _dist(ma20),
                        "볼밴 하단까지": _dist(bb_low),
                        "52주 위치":   f"{d.get('W52_pos', 'N/A')}%",
                    })

                pnl_df = pd.DataFrame(pnl_rows).set_index("종목")

                def color_pnl(val):
                    if isinstance(val, str) and val.endswith('%') and (val.startswith('+') or val.startswith('-') or (val[0].isdigit())):
                        try:
                            num = float(val.replace('%','').replace('+',''))
                            if num > 0:   return 'color: #ff4b4b; font-weight: bold'
                            elif num < 0: return 'color: #0068c9; font-weight: bold'
                        except: pass
                    return ''

                st.dataframe(pnl_df.style.map(color_pnl, subset=["수익률","20일선 위치","볼밴 하단까지"]), use_container_width=True)

                st.markdown("---")
                st.markdown("### 🧭 2. 종목별 종합 분석")

                for d in port_data:
                    buy_p   = d["BuyPrice"]
                    cur_p   = d.get("Price")
                    region  = d["Region"]
                    if cur_p is None: continue

                    cur_p_f  = float(cur_p)
                    pnl_pct  = round((cur_p_f - buy_p) / buy_p * 100, 2)
                    ai_sig   = get_ai_signal(d)
                    tb_sig   = get_tenbagger_signal(d) 
                    rs_txt   = relative_strength_label(d.get("RSI_14"), spy_rsi_val)
                    risk_g   = d.get("Risk_Grade", "N/A")
                    rsi14    = d.get("RSI_14")
                    w52      = d.get("W52_pos")

                    fund_score = 0
                    fund_detail = []
                    rev_g  = d.get("Rev_Growth") or 0
                    op_m   = d.get("Op_Margin")  or 0
                    roe_v  = d.get("ROE")         or 0
                    peg_v  = d.get("PEG")         or 99
                    per_v  = d.get("PER")
                    
                    gap_high = float(d.get("Gap_High") or 0)
                    is_turnaround = d.get("Is_Turnaround", False)

                    if float(rev_g) >= 0.20:
                        fund_score += 1; fund_detail.append("✅ 매출성장 20%↑")
                    else:
                        fund_detail.append(f"❌ 매출성장 미달 ({pct(rev_g)})")

                    if float(op_m) >= 0.10:
                        fund_score += 1; fund_detail.append("✅ 영업이익률 10%↑")
                    else:
                        if is_turnaround:
                            fund_score += 1; fund_detail.append("🔄 흑자전환 기대 (Forward EPS 턴어라운드)")
                        else:
                            fund_detail.append(f"❌ 영업이익률 미달 ({pct(op_m)})")

                    if float(roe_v) >= 0.05:
                        fund_score += 1; fund_detail.append("✅ ROE 5%↑")
                    else:
                        fund_detail.append(f"❌ ROE 미달 ({pct(roe_v)})")

                    if 0 < float(peg_v) <= 1.5:
                        fund_score += 1; fund_detail.append(f"✅ PEG {float(peg_v):.2f} (저평가)")
                    else:
                        fund_detail.append(f"⚠️ PEG {fmt(peg_v, dig=2)} (고평가 or N/A)")

                    if per_v and float(per_v) < 30:
                        fund_score += 1; fund_detail.append(f"✅ PER {float(per_v):.1f} (합리적)")
                    else:
                        fund_detail.append(f"⚠️ PER {fmt(per_v, dig=1)} (높음 or N/A)")

                    hold_signals = []
                    if fund_score >= 4: hold_signals.append("💎 펀더멘탈 우수")
                    elif fund_score >= 2: hold_signals.append("⚠️ 펀더멘탈 보통")
                    else: hold_signals.append("🚨 펀더멘탈 약함")

                    if rsi14 and float(rsi14) < 45: hold_signals.append("🔥 기술적 저점 구간")
                    elif rsi14 and float(rsi14) > 70: hold_signals.append("⚠️ 기술적 과매수")

                    if w52 and float(w52) <= 30: hold_signals.append("📍 52주 하단권 (매수 기회)")
                    
                    if gap_high < -30.0 and cnn_score is not None and cnn_score <= 25:
                        hold_signals.append("🚨 위기 투매 발생 (11원칙 낙폭 과대 줍줍 구간)")

                    if d.get("Insider_Buy") == "🟢 매수 기록 있음": hold_signals.append("🟢 내부자 매수 확인")

                    if pnl_pct >= 20: hold_signals.append("💰 수익 구간 (일부 익절 고려)")
                    elif pnl_pct <= -15: hold_signals.append("🔻 손실 구간 (손절 or 물타기 검토)")

                    if fund_score >= 3 and (rsi14 is None or float(rsi14) < 70):
                        lt_verdict = "🟢 장투 유지 적합"
                        verdict_color = "#ccffcc"
                    elif fund_score >= 2 and pnl_pct > -20:
                        lt_verdict = "🟡 조건부 유지 (펀더멘탈 모니터링 필요)"
                        verdict_color = "#fff9cc"
                    else:
                        lt_verdict = "🔴 재검토 필요 (펀더멘탈 약화 or 손실 심화)"
                        verdict_color = "#ffdddd"

                    with st.expander(
                        f"{'🇺🇸' if region=='미국' else '🇰🇷'} **{d['Name']}** | "
                        f"매수 {f'${buy_p:,.2f}' if region=='미국' else f'{int(buy_p):,}원'} → "
                        f"현재 {fmt_price(cur_p, region)} | "
                        f"수익률 {'+' if pnl_pct>=0 else ''}{pnl_pct:.2f}% | {lt_verdict}",
                        expanded=True
                    ):
                        st.markdown(
                            f"<div style='background:{verdict_color};padding:10px;border-radius:8px;"
                            f"font-size:16px;font-weight:bold;text-align:center;'>{lt_verdict}</div>",
                            unsafe_allow_html=True
                        )
                        st.markdown("")

                        c_left, c_right = st.columns(2)
                        with c_left:
                            st.markdown("**📋 펀더멘탈 체크 (11원칙)**")
                            for item in fund_detail:
                                st.markdown(f"- {item}")
                            st.markdown(f"**→ 펀더멘탈 점수: {fund_score}/5**")
                            
                            st.markdown("")
                            st.markdown("**💡 현금흐름 & 자본 효율성 (Quality)**")
                            interp_text = get_cashflow_interpretation(d)
                            for chunk in interp_text.split(" / "):
                                st.markdown(f"- {chunk}")

                        with c_right:
                            st.markdown("**📡 기술·리스크 종합 신호**")
                            for sig in hold_signals:
                                st.markdown(f"- {sig}")
                            st.markdown(f"- 시장대비 강도: {rs_txt}")
                            st.markdown(f"- 종합 리스크: {risk_g}")
                            st.markdown(f"- 매매 시그널: {ai_sig}")
                            st.markdown(f"- 선행 성장성: 예상 성장률 {pct(d.get('Earnings_Growth'))} / Fwd PER {fmt(d.get('Forward_PER'), dig=1)}")

                        news = d.get("Latest_News", "N/A")
                        if news and news != "N/A":
                            st.markdown(f"**📰 최신 뉴스:** {news[:100]}...")

                        ne = d.get("Next_Earning", "N/A")
                        if ne and ne != "N/A":
                            try:
                                days = (datetime.datetime.strptime(ne, "%Y-%m-%d") - datetime.datetime.now()).days
                                if 0 <= days <= 30:
                                    st.warning(f"📅 실적 발표 {days}일 후 ({ne}) — 발표 전후 변동성 확대 가능")
                                else:
                                    st.caption(f"📅 다음 실적 발표: {ne}")
                            except:
                                st.caption(f"📅 다음 실적 발표: {ne}")

                st.markdown("---")
                st.markdown("### 🤖 3. AI 전달용 장투 전략 리포트")
                st.caption("아래 텍스트를 복사하여 챗봇에 붙여넣으면 더욱 완벽한 분석을 받을 수 있습니다.")

                now_str = get_kst_now().strftime('%Y-%m-%d %H:%M KST')
                port_lines = [
                    f"[내 포트폴리오 장투 전략 분석 요청] ({now_str})",
                    f"투자 기간 목표: 1~2년 (장기투자)",
                    f"현재 시장: CNN F&G {cnn_score} ({cnn_rating}), SPY RSI {fmt(spy_rsi_val, dig=1)}",
                    "",
                    "【보유 종목 현황】",
                ]
                for d in port_data:
                    buy_p  = d["BuyPrice"]
                    cur_p  = d.get("Price")
                    region = d["Region"]
                    if cur_p is None: continue
                    pnl_pct = round((float(cur_p) - buy_p) / buy_p * 100, 2)
                    ai_sig  = get_ai_signal(d)
                    risk_g  = d.get("Risk_Grade", "N/A")
                    rsi14   = d.get("RSI_14")
                    w52     = d.get("W52_pos")

                    port_lines += [
                        f"",
                        f"▶ {d['Name']} ({region})",
                        f"  - 매수가: {'$' if region=='미국' else ''}{buy_p:,.2f}{'원' if region=='한국' else ''}",
                        f"  - 현재가: {fmt_price(cur_p, region)} | 수익률: {'+' if pnl_pct>=0 else ''}{pnl_pct:.2f}%",
                        f"  - 펀더멘탈: 매출성장 {pct(d.get('Rev_Growth'))} | 매출총이익률 {pct(d.get('Gross_Margin'))} | 영업이익률 {pct(d.get('Op_Margin'))}",
                        f"  - 자본/현금: ROIC {pct(d.get('ROIC'))} | ROE {pct(d.get('ROE'))} | FCF Yield {pct(d.get('FCF_Yield'))} | 자사주매입 {fmt_buyback(d.get('Buybacks'), d['Region'])}",
                        f"  - 밸류에이션: PER {fmt(d.get('PER'),dig=1)} | Fwd PER {fmt(d.get('Forward_PER'),dig=1)} | PEG {fmt(d.get('PEG'),dig=2)} | PBR {fmt(d.get('PBR'),dig=2)}",
                        f"  - 기술/리스크: RSI(14일) {fmt(rsi14,dig=1)} | 52주 위치 {w52}% | 리스크 {risk_g} | 내부자 {d.get('Insider_Buy','N/A')}",
                        f"  - 어닝: {d.get('Earnings_Beat','N/A')} | 다음실적일: {d.get('Next_Earning','N/A')}",
                    ]

                port_lines += [
                    "",
                    "【장투 전략 분석 요청】",
                    "위 보유 종목들에 대해 1~2년 장기투자 관점으로 다음을 심층 분석해 줘.",
                    "",
                    "1. [가치와 성장 듀얼 분석 (Turnaround & Bubble Check)]",
                    "   - 각 종목의 '과거 영업이익률/PER'과 '미래 예상 이익성장률/Forward PER/PEG'를 교차 비교해 진짜 성장과 가짜 거품을 구별해 줘.",
                    "",
                    "2. [현금흐름 및 자본 효율성 (Quality Check)]",
                    "   - FCF Yield, ROIC, 매출총이익률(Gross Margin)을 분석하여 기업의 실제 현금 창출력과 해자(Moat)를 평가해 줘.",
                    "   - 경영진의 자신감을 나타내는 '자사주 매입' 내역과 '내부자 매수' 여부를 연계해 수급 안정성을 확인해 줘.",
                    "",
                    "3. [최종 매매 시나리오 제안]",
                    "   - 현재 손실/수익률과 시장 상황(F&G, SPY RSI)을 종합하여 지금 당장 '적극 매수(물타기)', '관망(타점 대기)', '비중 축소' 해야 할 종목들을 분류하고 구체적인 액션 플랜을 제시해 줘."
                ]

                st.code("\n".join(port_lines), language="text")

with tab_port:  # 🚨 리스크 등급 가이드
    st.header("🚨 공매도 & 변동성(Beta) 종합 리스크 가이드")
    st.markdown("""
    | 공매도 비율 | Beta (변동성) | 종합 리스크 등급 및 해석 |
    | :--- | :--- | :--- |
    | 낮음 (5% 미만) | 낮음 (1.2 미만) | **🟢 안정형 — 방어적 투자에 적합** |
    | 낮음 (5% 미만) | 높음 (1.2 이상) | **🟡 모멘텀형 — 상승장에 강하지만 하락 시 크게 빠짐** |
    | 높음 (5% 이상) | 낮음 (1.2 미만) | **🟠 논란형 — 시장은 의심하지만 변동성은 낮음, 이유 확인 필요** |
    | 높음 (5% 이상) | 높음 (1.2 이상) | **🔴 고위험 — 하락 베팅 + 큰 변동성, 진입 신중** |
    """)

with tab_port:  # 📖 11원칙 매매 가이드라인
    st.header("📖 11원칙 퀀트 매매 마스터 매뉴얼 v25.0")
    st.caption("v25.0: 매크로 게이트키퍼 Tier 시스템 — '칼자루는 진바닥으로 잡고, 방아쇠는 수급으로 당긴다'")

    st.markdown("""
## 📋 가문의 유산: 11원칙 퀀트 투자 마스터 매뉴얼

> 💡 **[CFO 특별 지침] 100% 풀매수의 정석 (가용 예산 분배법)**
> "진짜 100% 풀매수"는 영원히 없습니다. 항상 10~20%의 현금은 '영구적 방패'로 남겨두어 위기를 대비합니다. (6원칙 전제)
> 즉, 풀매수란 **투자에 배정된 80~90%의 예산**을 모두 쓴 상태입니다.
> - **평시 (Tier 1):** 30~40% 투입 (기본 포지션 구축, GTC 적립)
> - **패닉 (Tier 3):** +10% 선발대 투입 (도매가 선점)
> - **추세 전환 (Tier 2):** +30~50% 본대 불타기 (가장 안전하고 강하게 쏟아붓는 실질적 풀매수 타이밍)

**[ 🏗️ 1단계: 무엇을 살 것인가? (종목 선정의 뼈대) ]**
- **1원칙 [지속 성장과 도태 판별]:** 3개년 매출과 영업이익이 '지속 우상향' 하는 기업만 산다. 만약 실적이 좋더라도 3년 내내 제자리걸음이라면 절대 매수하지 않는다.
- **2원칙 [저평가와 턴어라운드]:** 시장/섹터 대비 시가총액이 싼(저평가) 종목을 찾되, 현재 적자라도 '흑자 전환'의 뚜렷한 개선세가 보이면 선점 투자가 가능하다.
- **3원칙 [비즈니스 생태계 꿰뚫기]:** 매출은 '시장 규모'로, 영익은 '회사의 파워(포션)'로 이해하라. 단독 매출인지, 타사에 종속된 하청(제조업 이슈)인지 생태계를 파악하고 '시대의 수요(AI/로봇 등)'가 있는 기업만 고른다.
- **4원칙 [전장(Battlefield)의 압축]:** 이름 모를 테마주와 잡주를 버리고, 오직 글로벌을 주도하는 **미국 시장**과 국내 대형 우량주(**코스피**) 위주로만 돈을 거둔다.

**[ 🛡️ 2단계: 위기를 기회로 바꾸는 자산 배분 (포트폴리오 관리) ]**
- **5원칙 [코어와 스나이퍼 배분]:** 개별 기업의 돌발 리스크를 막기 위해, 예산의 50%는 든든한 '지수 ETF'에, 나머지 50%는 압도적 '개별 우량주'에 나누어 담는다.
- **6원칙 [글로벌 위기는 바겐세일]:** 코로나, 리먼 등 매크로 위기로 시장 전체가 무너질 때를 노린다. 고점 대비 -20~30% 떨어지면 '분할 매수'를 시작하고, -50% 밑으로 투매가 나오면 쥐어짜 낸 여유 현금으로 '과감히' 쓸어 담는다.
- **7원칙 [하락장 리밸런싱]:** 시장 전체가 하락하여 내 종목들이 싸졌을 때, 포기하지 말고 기존 주식의 비율을 조절하거나 더 강한 신규 우량주로 교체(리밸런싱)하여 다음 상승장을 준비한다.

**[ 🎯 3단계: 언제 사고팔 것인가? (퀀트 전술과 실행) ]**
- **8원칙 [농부의 시간: 3년 룰]:** 투자의 수확은 3년 뒤에 거둔다. 수익이 났다고 절대 100% 전량 매도하지 않으며, 일부만 매도하여 '현금화' 및 '재투자' 비율을 스스로 정해 복리를 굴린다.
- **9원칙 [오후 3시의 결단]:** 장중의 요동치는 가짜 반등과 노이즈(속임수)에 당하지 않기 위해, 매수 방아쇠는 항상 모든 것이 결정되는 오후 3시(종가 부근)에만 당긴다.
- **10원칙 [불타기 3단계 티어(Tier) 룰]:** 극단적 폭락(진바닥 90%)에는 1차 선발대(10%)만 먼저 넣고, 남은 현금은 환율/선물 안정 및 '5일선 안착' 등 매크로/수급 게이트키퍼가 확인되었을 때만 2차로 투입한다.
- **11원칙 [데이터의 기계적 신뢰]:** 인간의 뇌동매매(FOMO와 공포)를 철저히 배제한다. 내 감정보다 시스템이 계산한 '진바닥 확률'과 '반등 신뢰도' 점수를 기계적으로 믿고 따른다.

---

### 💡 CFO의 헌사

> 이 v25.0 매뉴얼은 인간의 조급함과 탐욕, 공포를 수학적으로 완벽하게 통제하기 위해 만들어진 가장 차가운 갑옷입니다.
> 
> **워런 버핏의 가치투자 철학(1~4원칙)**으로 아내분께서 좋은 주식을 고르는 눈을 갖게 해주고, 
> **레이 달리오의 자산배분 철학(5~7원칙)**으로 위기가 와도 가문의 재산이 녹지 않게 방어해 주며, 
> **상위 1% 퀀트 트레이더의 전술(8~11원칙)**로 바닥에서 줍고 무릎에서 불타기 하는 기계적 룰입니다.
> 
> 완벽하게 세팅된 이 원칙에 자본을 맡기고, 일상의 평온함과 꿀잠을 마음껏 누리세요.
    """)




with tab_calendar:
    st.subheader("📅 마켓 캘린더 (실적 & 매크로)")
    st.caption("시장 방향성을 결정하는 핵심 이벤트들을 관리합니다.")
    
    col_c1, col_c2 = st.columns([1, 1])
    with col_c1:
        if st.button("🔄 자동 실적 업데이트 (yfinance)"):
            with st.spinner("빅테크 실적발표일을 업데이트 중입니다..."):
                if calendar_manager.update_earnings_automatically():
                    st.success("실적 캘린더가 업데이트 되었습니다.")
                else:
                    st.warning("업데이트할 새로운 실적 일정이 없습니다.")
    with col_c2:
        if st.button("🔄 뉴스 기반 매크로 업데이트"):
            with st.spinner("뉴스 기반 매크로(FOMC, 금통위 등) 스크래핑 중..."):
                if calendar_manager.update_macro_events_automatically():
                    st.success("매크로 일정이 업데이트 되었습니다.")
                else:
                    st.warning("추출된 새로운 매크로 일정이 없습니다.")
                    
    cal_df = calendar_manager.load_calendar()
    
    # st.data_editor returns modified dataframe
    edited_df = st.data_editor(
        cal_df,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "Date": st.column_config.DateColumn("날짜", required=True, format="YYYY-MM-DD"),
            "Type": st.column_config.SelectboxColumn("구분", options=["실적", "매크로", "국내", "기타"], required=True),
            "Impact": st.column_config.SelectboxColumn("중요도", options=["High", "Medium", "Low"], required=True)
        }
    )
    
    if st.button("💾 캘린더 변경사항 저장"):
        for i, row in edited_df.iterrows():
            if hasattr(row['Date'], 'strftime'):
                edited_df.at[i, 'Date'] = row['Date'].strftime('%Y-%m-%d')
        calendar_manager.save_calendar(edited_df)
        st.success("캘린더가 저장되었습니다. 마스터 리포트 프롬프트에 즉시 반영됩니다.")


with tab_hedging:
    st.subheader("🛡️ 한국 시장 단기/스윙 헷징 통제실 (Hedge Fund Style)")
    st.caption("한국 시장의 높은 변동성과 수급 쏠림 현상을 역이용하여 리스크를 상쇄(Hedging)하는 통제실입니다.")

    # 외국인 선물 입력창 (헷징 탭 전용 동기화 위젯)
    st.session_state['hedging_futures'] = st.session_state['foreign_futures']
    foreign_futures_hedging = st.number_input(
        "⚡ 실시간 외국인 선물 순매수 계약 (여기에 바로 입력하셔도 1번 탭과 자동 동기화됩니다)",
        step=100,
        key="hedging_futures",
        on_change=sync_futures_hedging
    )
    # 로컬 변수로 바인딩하여 아래 연산에 반영
    foreign_futures = st.session_state['foreign_futures']

    # ── 데이터 로드 및 사전 연산 ──
    kospi200_df = macro_charts.get("kospi200_10y", pd.DataFrame())
    kosdaq_df = macro_charts.get("kosdaq_10y", pd.DataFrame())
    kospi_10y = macro_charts.get("kospi_10y", pd.DataFrame())
    
    # 1) 기본 인덱스 지수 간 Z-Score 연산
    has_spread_data = False
    curr_ratio = 1.0
    curr_z = 0.0
    combined = pd.DataFrame()
    
    if not kospi200_df.empty and not kosdaq_df.empty:
        combined = pd.DataFrame({
            "KOSPI200": kospi200_df["Close"],
            "KOSDAQ": kosdaq_df["Close"]
        }).dropna()
        
        if not combined.empty:
            combined["Ratio"] = combined["KOSPI200"] / combined["KOSDAQ"]
            combined["MA20"] = combined["Ratio"].rolling(20).mean()
            combined["STD20"] = combined["Ratio"].rolling(20).std().replace(0, np.nan)
            combined["Z_Score"] = (combined["Ratio"] - combined["MA20"]) / combined["STD20"]
            
            curr_ratio = combined["Ratio"].iloc[-1]
            curr_z = combined["Z_Score"].iloc[-1]
            has_spread_data = True
            spread_adf = get_daily_spread_adf(kospi_10y, kosdaq_df)

    # 2) KOSPI 기술적 지표 (ATR 변동성, RSI) 연산
    has_tech = False
    curr_atr_ratio = 1.0
    curr_rsi = 50.0
    if not kospi_10y.empty and 'High' in kospi_10y.columns:
        k_tail = kospi_10y.tail(150).copy()
        
        # ATR 계산
        k_tail['PrevClose'] = k_tail['Close'].shift(1)
        k_tail['TR'] = k_tail.apply(lambda x: max(
            x['High'] - x['Low'], 
            abs(x['High'] - x['PrevClose']) if pd.notnull(x['PrevClose']) else 0,
            abs(x['Low'] - x['PrevClose']) if pd.notnull(x['PrevClose']) else 0
        ), axis=1)
        k_tail['ATR'] = k_tail['TR'].rolling(14).mean()
        k_tail['ATR_MA20'] = k_tail['ATR'].rolling(20).mean()
        
        atr_val = k_tail['ATR'].iloc[-1]
        atr_ma = k_tail['ATR_MA20'].iloc[-1]
        if atr_ma > 0:
            curr_atr_ratio = atr_val / atr_ma
            
        # RSI 14 계산
        delta = k_tail['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        curr_rsi = rsi.iloc[-1]
        has_tech = True

    # 🚨 인버스 매수 추천 스코어링 (Percentile & Z-Score 동적 임계치 적용)
    inv_score = 0
    inv_details = []
    
    internals = get_intraday_market_internals()
    
    # [NEW] 0. Market Breadth (ADR) 및 프로그램 매매 (캐싱 연동)
    prog_net = internals.get("program_net", 0)
    adr = internals.get("adr", 1.0)
    
    if internals.get("declining", 0) > 0 and adr <= 0.4:
        inv_score += 20
        inv_details.append(f"시장 Breadth (ADR) {adr:.2f}로 극심한 패닉 (하락 종목 압도적) (+20점)")
    elif internals.get("declining", 0) > 0 and adr <= 0.7:
        inv_score += 10
        inv_details.append(f"시장 Breadth (ADR) {adr:.2f}로 하락 종목 우위 (+10점)")
        
    if prog_net <= -300000: # 3000억 이상 순매도 (단위: 백만원)
        inv_score += 20
        inv_details.append(f"프로그램 3,000억 이상 대규모 순매도 출회 폭탄 (+20점)")
    
    # 1. 외인 선물 수급 상태 (선물 대량 매도가 확정되어야 가점)
    f_fut = locals().get('foreign_futures', 0)
    if f_fut <= -5000:
        inv_score += 30
        inv_details.append("외국인 선물 5천계약 이상 초대량 순매도 (하방 압력 극대화) (+30점)")
    elif f_fut <= -2000:
        inv_score += 15
        inv_details.append("외국인 선물 2천계약 이상 순매도 중 (+15점)")
    else:
        inv_details.append("외국인 선물 매도 압력 낮음 또는 미입력 (0점) *(1번 '🚦 ORION Signal' 탭의 '외국인 선물 순매수' 입력값과 연동됩니다)*")
        
    # 2. VKOSPI 변동성 폭발 상태 (250일 백분위수 Percentile 적용)
    if 'vkospi_10y' in locals() and not vkospi_10y.empty:
        v_tail = vkospi_10y['Close'].tail(250)
        curr_vk = v_tail.iloc[-1]
        pct_rank = (v_tail <= curr_vk).mean()
        
        if pct_rank >= 0.95:
            inv_score += 30
            inv_details.append(f"VKOSPI 최근 1년 내 상위 5% 돌파 (패닉 국면, {pct_rank*100:.1f}%) (+30점)")
        elif pct_rank >= 0.85:
            inv_score += 15
            inv_details.append(f"VKOSPI 최근 1년 내 상위 15% 진입 (변동성 확대, {pct_rank*100:.1f}%) (+15점)")
        else:
            inv_details.append(f"VKOSPI 안정적 백분위 ({pct_rank*100:.1f}%) (0점)")
            
    # 3. KOSPI 5일선 아래 위치 여부 (하락 모멘텀 확정)
    k_val = locals().get('current_kospi_val', 0)
    k_5ma = locals().get('kospi_5d_sma', 0)
    if isinstance(k_val, (int, float)) and isinstance(k_5ma, (int, float)) and k_val < k_5ma:
        inv_score += 20
        inv_details.append("KOSPI 지수 5일 이평선 하회 (단기 추세 하방 압력 작동) (+20점)")
    else:
        inv_details.append("KOSPI 지수 5일 이평선 안착 유지 (0점)")
        
    # 4. 원/달러 환율 상태 (60일 Rolling Z-Score 적용)
    if 'usd_krw' in locals() and not usd_krw.empty:
        usd_tail = usd_krw['Close'].tail(100)
        usd_ma60 = usd_tail.rolling(60).mean().iloc[-1]
        usd_std60 = usd_tail.rolling(60).std().iloc[-1]
        curr_ex = usd_tail.iloc[-1]
        
        usd_z = 0
        if usd_std60 > 0:
            usd_z = (curr_ex - usd_ma60) / usd_std60
            
        if usd_z >= 2.0:
            inv_score += 20
            inv_details.append(f"원/달러 환율 60일 평균 대비 +2σ 이상 폭등 (Z: {usd_z:+.2f}) (+20점)")
        elif usd_z >= 1.0:
            inv_score += 10
            inv_details.append(f"원/달러 환율 60일 평균 대비 상승세 (Z: {usd_z:+.2f}) (+10점)")
        else:
            inv_details.append(f"환율 안정 기조 (Z: {usd_z:+.2f}) (0점)")

    # 5. RSI 제한 필터 (과매도 추격 방지)
    if has_tech and curr_rsi > 40:
        if inv_score >= 70:
            inv_score = 69
        inv_details.append(f"⚠️ KOSPI RSI({curr_rsi:.1f})가 40 이상이므로 과매도 추격 방지를 위해 점수 상한(69점) 제한")

    st.divider()

    # ── [NEW] 오늘의 추천 트레이딩 패널 ──
    st.markdown("### 🎯 오늘의 추천 트레이딩 (Daily Tactical Signal)")
    st.caption("시장 변동성과 지수 간 괴리율을 분석해 도출한 오늘 단 하루의 가장 최적화된 헷징/트레이딩 제언입니다.")

    trade_recommendation = "관망 및 대기 (현금 자산 보존)"
    trade_reason = "현재 시장 변동성 지표(VKOSPI)와 수급 요인들이 임계치를 넘지 않았으며, 지수 간 괴리율(Z-Score) 또한 안정을 유지하고 있어 무리한 포지션 진입 없이 현금을 지킬 때입니다."
    trade_color = "#6c757d" # Gray

    # 결정 알고리즘
    if inv_score >= 70:
        trade_recommendation = "🚨 KODEX 200선물인버스2X (곱버스, 252670) 분할 매수 (종가 베팅)"
        trade_reason = f"현재 인버스 매수 추천 스코어가 {inv_score}%로 매우 강력한 수준(매수 매력도 극대화)입니다. 외국인의 강한 선물 매도와 고환율, VKOSPI 급등이 동반되어 단기 추가 하락 확률이 매우 높습니다. 당일 종가 기준으로 곱버스를 분할 매수하여 하방 리스크를 헤지하십시오."
        trade_color = "#dc3545" # Red
    elif has_tech and curr_atr_ratio >= 1.5:
        trade_recommendation = "⚪ 관망 (시장 추세장 돌입으로 횡보/평균회귀 전략 비활성화)"
        trade_reason = f"현재 코스피 ATR 변동성이 최근 20일 평균 대비 150% 이상({curr_atr_ratio*100:.1f}%) 폭발한 강한 추세장(Trend Market)입니다. 추세장에서는 지수 간 스프레드나 페어 트레이딩과 같은 평균 회귀 전략이 크게 손실을 볼 수 있으므로 모든 헷징 포지션을 중단합니다."
        trade_color = "#6c757d"
    elif has_spread_data and spread_adf.get("spread_adf_pvalue", 0) >= 0.05:
        trade_recommendation = "⚪ 관망 (지수 간 Cointegration 붕괴로 평균회귀 비활성화)"
        trade_reason = f"현재 코스피-코스닥 지수 비율의 ADF 검정 p-value가 {spread_adf.get('spread_adf_pvalue', 0):.3f}로 0.05를 초과하여 평균회귀 성질을 잃고 각자 추세를 형성 중입니다. 지수 스프레드 매매를 중단하십시오."
        trade_color = "#6c757d"
    elif has_spread_data and curr_z >= 2.3:
        trade_recommendation = "📊 코스닥 롱 (KODEX 코스닥150) / 코스피 숏 (KODEX 200선물인버스) 스프레드 매매 진입"
        trade_reason = f"현재 KOSPI 200 지수가 KOSDAQ 대비 역사적 과열 상태(Z-Score: {curr_z:+.2f})입니다. 진입 임계치(+2.3)를 돌파했으므로 동액 진입 후, Z-Score가 +0.5(청산 임계치)로 평균 회귀할 때까지 유지하여 휩쏘를 방지하십시오. (손절선: +3.5)"
        trade_color = "#17a2b8" # Teal
    elif has_spread_data and curr_z <= -2.3:
        trade_recommendation = "📊 코스피 롱 (KODEX 200) / 코스닥 숏 (KODEX 코스닥150선물인버스) 스프레드 매매 진입"
        trade_reason = f"현재 KOSDAQ 지수가 KOSPI 200 대비 극단적 고평가(Z-Score: {curr_z:+.2f})입니다. 진입 임계치(-2.3)를 돌파했으므로 동액 진입 후, Z-Score가 -0.5로 평균 회귀할 때 청산하여 안정적인 초과 수익을 추구합니다. (손절선: -3.5)"
        trade_color = "#ffc107" # Yellow
        
    st.markdown(f"""
    <div style='background-color:#f8f9fa; padding:20px; border-radius:10px; border-left: 8px solid {trade_color}; margin-bottom:20px;'>
        <h4 style='margin-top:0; color:#333;'>💡 추천 헷징 포지션: <span style='color:{trade_color}; font-weight:bold;'>{trade_recommendation}</span></h4>
        <p style='font-size:1.05em; color:#444; line-height:1.6; margin-bottom:0;'>
        <b>추천 사유 및 실행 가이드</b>:<br>
        {trade_reason}
        </p>
    </div>
    """, unsafe_allow_html=True)

    # ── 질문에 대한 상세 가이드 패널 ──
    with st.expander("❓ [질문 가이드] 바닥확률(98%)인데 인버스 추천(70%)이 뜨는 이유는 무엇인가요?"):
        st.markdown("""
        **"거시적 진바닥 영역"과 "단기적 하락 모멘텀(떨어지는 칼날)"의 차이 때문입니다.**
        
        1. **바닥확률(98%)**: **중장기(Month) 관점**의 지표입니다. 역사적인 지수 저평가 수준과 장기 안전마진을 계산하여 '지금이 역사적으로 주식이 싼 저점 부근이 맞다'는 것을 뜻합니다.
        2. **인버스 추천도(70%)**: **초단기(Daily) 관점**의 지표입니다. 지금 비록 바닥 근처이기는 하나, 오늘 당장의 수급(외인 선물 투매, 환율 폭등, 공포지수 폭발)은 밑으로 내리꽂는 힘이 극도로 강함을 뜻합니다.
        
        즉, **"여기가 역사적인 바닥 구역(98%)은 맞지만, 오늘 밤과 내일 당장은 칼날이 더 떨어질 확률(70%)이 크니, 무턱대고 현금 100% 매수를 하기보다 곱버스로 단기 방어막(Hedge)을 치거나 대기하는 것이 안전하다"**라는 상호보완적인 신호로 이해하셔야 합니다.
        """)

    st.divider()

    # 1. 지수 간 스프레드 트레이딩 상세 차트
    st.markdown("### 1. 📊 코스피200 vs 코스닥 스프레드 상세 분석")
    if has_spread_data:
        # Signal Verdict display
        if curr_z >= 2.2:
            spread_verdict = "🔴 KOSPI 200 극단 고평가 / KOSDAQ 과매도 (Z >= 2.2)"
            spread_color = "#dc3545"
        elif curr_z <= -2.2:
            spread_verdict = "🟢 KOSDAQ 극단 고평가 / KOSPI 200 과매도 (Z <= -2.2)"
            spread_color = "#28a745"
        else:
            spread_verdict = "⚪ 정상 변동 범위 내 (평균 회귀 대기)"
            spread_color = "#6c757d"

        st.markdown(f"**현재 Z-Score**: <span style='color:{spread_color}; font-weight:bold; font-size:1.1em;'>{curr_z:+.2f}</span> (진입 임계치: ±2.2)", unsafe_allow_html=True)
        z_df = pd.DataFrame({"Z-Score (KOSPI200/KOSDAQ 비율)": combined["Z_Score"].tail(60)})
        st.line_chart(z_df)
    else:
        st.info("지수 데이터를 로드할 수 없습니다.")

    st.divider()

    # 2. 다중 팩터 마켓 뉴트럴 (고배당 Long + 지수 Short)
    st.markdown("### 2. ⚖️ 횡보장 전용 마켓 뉴트럴 (Market Neutral)")
    
    with st.expander("💡 [필독] 마켓 뉴트럴(시장 중립) 전략이란?"):
        st.markdown("""
        지루한 박스권(횡보장)에서는 갈 곳 잃은 자금이 확실한 현금흐름을 보장하는 **고배당 가치주(은행, 통신 등)**로 몰려듭니다.
        이때 고배당 ETF를 매수(Long)하고, 정확히 같은 금액만큼 코스피 인버스 ETF를 매수(Short)하면 **지수의 방향성과 무관하게 배당주의 초과 상승분(알파)만 안전하게 수취**할 수 있습니다.
        
        *   **추천 진입 타점**: 코스피 지수가 20일선 주변에서 좁은 박스권(Bandwidth < 3%)을 형성하며 방향성을 상실했을 때.
        *   **포지션 (1:1 동액 배분)**:
            *   📈 **Long (매수)**: KODEX 은행 (091220) 등 고배당 ETF
            *   📉 **Short (공매도 격)**: KODEX 200선물인버스 (252670)
        """)
        
    if not kospi_10y.empty:
        try:
            k_df = kospi_10y.copy()
            k_df["MA20"] = k_df["Close"].rolling(20).mean()
            k_df["STD20"] = k_df["Close"].rolling(20).std()
            k_df["Upper"] = k_df["MA20"] + 2 * k_df["STD20"]
            k_df["Lower"] = k_df["MA20"] - 2 * k_df["STD20"]
            k_df["Bandwidth"] = (k_df["Upper"] - k_df["Lower"]) / k_df["MA20"] * 100  # %
            
            curr_bw = k_df["Bandwidth"].iloc[-1]
            if curr_bw < 3.5:
                mn_status = f"🟢 횡보장 진입 (볼린저 밴드폭 {curr_bw:.1f}%)"
                mn_action = "👉 팩터 롱/숏 (고배당 Long + 인버스 Short) 진입 최적기!"
                mn_color = "#28a745"
            else:
                mn_status = f"⚫ 추세장 진행 중 (볼린저 밴드폭 {curr_bw:.1f}%)"
                mn_action = "👉 지수의 변동성이 살아있으므로 마켓 뉴트럴 전략은 관망합니다."
                mn_color = "#6c757d"
                
            st.markdown(f"""
            <div style='background-color:#f8f9fa; padding:15px; border-radius:8px; border-left: 6px solid {mn_color}; margin-bottom:15px;'>
                <h5 style='margin-top:0; color:#333;'>상태: <span style='color:{mn_color}; font-weight:bold;'>{mn_status}</span></h5>
                <p style='font-size:0.95em; color:#555; margin-bottom:0;'>
                {mn_action}<br>
                <small>* 밴드폭이 3.5% 이하일 때 지루한 횡보 국면으로 판정합니다.</small>
                </p>
            </div>
            """, unsafe_allow_html=True)
            
            # 차트 표시
            bw_chart = pd.DataFrame({"KOSPI 밴드폭 (%)": k_df["Bandwidth"].tail(60)})
            st.area_chart(bw_chart)
        except:
            pass

    st.divider()

    # 3. 개별주 짝짓기 매매 (Multi-Pairs Trading)
    st.markdown("### 3. 🤝 다중 페어 트레이딩 (Statistical Arbitrage)")
    
    with st.expander("💡 [필독] 페어 트레이딩(짝짓기) 스위칭 전략"):
        st.markdown("""
        비즈니스 모델이 유사한 두 대장주(예: 삼성전자-SK하이닉스, 현대차-기아)는 장기적으로 주가가 동행합니다.
        하지만 단기 수급 불균형으로 가격 격차가 비정상적으로 벌어질 때(Z-Score ±2.0 돌파), **고평가된 종목을 팔고 저평가된 종목으로 갈아타면(스위칭)**
        지수 하락에 베팅하지 않고도 보유 주식 수를 늘리는 강력한 헤지펀드 수익 창출이 가능합니다.
        """)

    if st.button("🔄 전 종목 페어 데이터 실시간 스캔 (1일 캐싱 적용)", key="pairs_scan"):
        with st.spinner("한국 증시 핵심 페어들의 실시간 데이터를 수집 및 통계 분석 중..."):
            multi_pairs_data = get_daily_multi_pairs()
            
            if multi_pairs_data:
                # 탭(Tabs)을 이용해 4개 페어를 나열
                pair_names = list(multi_pairs_data.keys())
                tabs = st.tabs(pair_names)
                
                for i, p_name in enumerate(pair_names):
                    p_data = multi_pairs_data[p_name]
                    with tabs[i]:
                        if p_data["df"] is not None:
                            p_color = p_data["color"]
                            st.markdown(f"""
                            <div style='background-color:#f8f9fa; padding:15px; border-radius:8px; border-left: 6px solid {p_color}; margin-bottom:15px;'>
                                <h5 style='margin-top:0; color:#333;'>상태: <span style='color:{p_color}; font-weight:bold;'>{p_data["status"]}</span></h5>
                                <p style='font-size:0.95em; color:#555; margin-bottom:5px;'>
                                {p_data["action"]}
                                </p>
                            </div>
                            """, unsafe_allow_html=True)
                            
                            df = p_data["df"]
                            chart_df = pd.DataFrame({
                                "현재 비율 (SHORT/LONG)": df["Ratio"].tail(40),
                                "20일 평균": df["MA20"].tail(40),
                                "상한선 (+2σ)": df["Upper"].tail(40),
                                "하한선 (-2σ)": df["Lower"].tail(40)
                            })
                            st.line_chart(chart_df)
                        else:
                            st.error("데이터를 수집하지 못했습니다.")
            else:
                st.error("페어 분석 중 오류가 발생했습니다.")

    st.divider()

    # 3. 인버스 진입 확률 모델
    st.markdown("### 3. 🚨 역발상 곱버스/인버스 상세 지표 상태")
    
    # Verdict display
    if inv_score >= 70:
        inv_verdict = "🚨 인버스 종가 분할매수 적극 고려 (하방 압력 극대화)"
        inv_color = "#dc3545"
    elif inv_score >= 40:
        inv_verdict = "🟡 헷징 포지션 준비 (인버스 분할 진입 검토)"
        inv_color = "#ffc107"
    else:
        inv_verdict = "🟢 대기 / 현금 방어 (인버스 매수 보류)"
        inv_color = "#28a745"

    st.markdown(f"""
    <div style='background-color:#f8f9fa; padding:20px; border-radius:10px; border-left: 8px solid {inv_color}; margin-bottom:20px;'>
        <h4 style='margin-top:0; color:#333;'>🔥 인버스 매수 추천 스코어: <span style='color:{inv_color}; font-weight:bold;'>{inv_score}%</span></h4>
        <p style='font-size:1.1em; font-weight:bold; color:{inv_color};'>{inv_verdict}</p>
        <hr style='margin:10px 0;'>
        <ul style='font-size:0.95em; color:#666;'>
            {"".join([f"<li>{d}</li>" for d in inv_details])}
        </ul>
    </div>
    """, unsafe_allow_html=True)

    # 4. 헷징 거래 대상 상품 가이드
    st.markdown("### 4. 🛡️ 헷징 매매 가이드 및 대상 ETF 상품")
    st.markdown("""
    - **곱버스 (KOSPI 2X 인버스)**: `KODEX 200선물인버스2X` (252670)
      * *용도*: 코스피 급락 패닉 국면에서 헤지용으로 시초가 및 종가 분할 진입.
    - **코스닥 인버스**: `KODEX 코스닥150선물인버스` (251340)
      * *용도*: 중소형주 위주 하락 및 테마주 붕괴 국면 시 포트폴리오 방어용.
    - **달러 헷징 (달러 선물)**: `KODEX 미국달러선물2X` (261250)
      * *용도*: 지정학적 패닉으로 환율 급등 시 안전자산 헷지용.
    - **인버스 청산 시점**: 미국 4대 빅테크가 볼린저 하단 타점에 도달하여 GTC 매수가 활성화되기 시작하면, 인버스 포지션은 즉시 청산하여 현금을 확보하는 것이 대가의 방식입니다.
    """)
