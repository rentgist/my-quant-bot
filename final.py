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
from hedging import (
    HEDGE_HORIZONS,
    build_daily_hedge_features,
    build_inverse_validation_summary,
    build_plain_action_plan,
    calculate_beta_hedge_size,
    evaluate_hedge_state,
    optimize_hedge_parameters,
    run_hedge_backtest,
)
from defensive_overlay import (
    build_defensive_action_plan,
    current_defensive_state,
    evaluate_usd_diversifier,
    optimize_defensive_parameters,
)
from regime_playbook import (
    REGIME_POLICIES,
    build_holding_action,
    build_regime_action_plan,
    calculate_entry_strategy_scenarios,
    classify_market_regime,
    run_regime_backtest,
)
from data_loader import (
    get_real_cnn_fg,
    get_macro_charts, 
    load_macro_snapshot,
    save_macro_snapshot,
    get_sector_baseline, 
    get_stock_data,
    get_krx_mapping_status,
    get_upcoming_events,
    get_investor_flow,
    get_1m_investor_flow,
    get_us_flow_snapshot,
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
        calculate_us_orion_score,
        evaluate_us_entry_permission,
        calculate_us_flow_signal,
        get_us_trigger_display,
        get_us_strategic_advice,
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
if "account_total_assets" not in st.session_state:
    st.session_state["account_total_assets"] = 5000
if "account_kr_equity" not in st.session_state:
    st.session_state["account_kr_equity"] = 3500

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
    data = {
        "advancing": None,
        "declining": None,
        "program_net": None,
        "adr": None,
        "breadth_status": "unavailable",
        "program_status": "unavailable",
    }
    try:
        # 프로그램 매매 스크래핑 (단위: 백만원)
        res_prog = requests.get('https://finance.naver.com/sise/sise_program.naver', headers={'User-Agent': 'Mozilla/5.0'}, timeout=3)
        res_prog.encoding = 'euc-kr'
        soup_p = BeautifulSoup(res_prog.text, 'html.parser')
        # 최상단 차익+비차익 합계 (순매수) - 에러 대비용으로 단순 패스 가능성 열어둠
        # Naver Finance 프로그램 종합 순매수 텍스트 크롤링 (불안정할 수 있으므로 try-except)
        
        # 프로그램 수급은 DOM 파서가 구현되기 전까지 결측으로 유지한다.
        # 0은 실제 중립 수급으로 오인되므로 신호 점수에 포함하면 안 된다.
        
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
                    if nums:
                        data["advancing"] = nums[0]
                elif '하락' in text:
                    nums = [int(s) for s in text.split() if s.isdigit()]
                    if nums:
                        data["declining"] = nums[0]

        if (
            data["advancing"] is not None
            and data["declining"] is not None
            and data["declining"] > 0
        ):
            data["adr"] = data["advancing"] / data["declining"]
            data["breadth_status"] = "ok"
    except Exception as e:
        pass # 크롤링 에러 시 대시보드 중단 방지
    return data

@st.cache_data(ttl=86400)
def get_daily_spread_adf(kospi_df, kosdaq_df):
    """1일 캐싱: 로그가격 OLS 잔차에 대한 Engle-Granger 1단계 검정."""
    res = {
        "spread_adf_pvalue": None,
        "is_cointegrated": False,
        "status": "unavailable",
        "hedge_ratio": None,
        "residual_z": None,
        "observations": 0,
        "error": "",
    }
    if not HAS_STATSMODELS:
        res["status"] = "statsmodels_missing"
        res["error"] = "statsmodels 미설치"
        return res
    try:
        if not kospi_df.empty and not kosdaq_df.empty:
            prices = pd.concat(
                [
                    pd.to_numeric(kospi_df["Close"], errors="coerce").rename("KOSPI200"),
                    pd.to_numeric(kosdaq_df["Close"], errors="coerce").rename("KOSDAQ"),
                ],
                axis=1,
            ).dropna()
            prices = prices[(prices > 0).all(axis=1)].tail(504)
            if len(prices) < 120:
                res["status"] = "insufficient_data"
                res["error"] = "공적분 검정에 필요한 120거래일 미만"
                return res
            y = np.log(prices["KOSPI200"])
            x = sm.add_constant(np.log(prices["KOSDAQ"]))
            model = sm.OLS(y, x).fit()
            residual = model.resid
            adf_result = adfuller(residual, autolag="AIC")
            residual_std = residual.tail(60).std()
            residual_z = (
                (residual.iloc[-1] - residual.tail(60).mean()) / residual_std
                if residual_std > 0
                else 0.0
            )
            res.update(
                {
                    "spread_adf_pvalue": float(adf_result[1]),
                    "is_cointegrated": bool(adf_result[1] < 0.05),
                    "status": "ok",
                    "hedge_ratio": float(model.params.iloc[1]),
                    "residual_z": float(residual_z),
                    "observations": int(len(prices)),
                }
            )
        else:
            res["status"] = "insufficient_data"
            res["error"] = "지수 데이터 없음"
    except Exception as exc:
        res["status"] = "error"
        res["error"] = str(exc)
    return res


@st.cache_data(ttl=3600)
def get_hedge_optimization(
    kospi_hist,
    vkospi_hist,
    usdkrw_hist,
    inverse1x_hist,
    inverse2x_hist,
    horizon_key,
    transaction_cost_bps,
):
    """Cache chronological parameter selection for the hedge dashboard."""
    return optimize_hedge_parameters(
        kospi_hist=kospi_hist,
        vkospi_hist=vkospi_hist,
        usdkrw_hist=usdkrw_hist,
        inverse1x_hist=inverse1x_hist,
        inverse2x_hist=inverse2x_hist,
        horizon_key=horizon_key,
        transaction_cost_bps=transaction_cost_bps,
    )


@st.cache_data(ttl=3600)
def get_defensive_optimization(kospi_hist, transaction_cost_bps):
    """Cache long-only defensive allocation selection and holdout validation."""
    return optimize_defensive_parameters(
        kospi_hist,
        transaction_cost_bps=transaction_cost_bps,
    )


@st.cache_data(ttl=3600)
def get_regime_backtest(kospi_hist, transaction_cost_bps=15.0):
    """Cache the fixed, long-only regime playbook validation."""
    return run_regime_backtest(
        kospi_hist,
        transaction_cost_bps=transaction_cost_bps,
    )


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

# Render a useful shell before any market provider is contacted.  A cold start
# used to wait for 19 global symbols plus Korean indices before drawing a pixel.
if "macro_charts" not in st.session_state:
    previous_snapshot = load_macro_snapshot()
    if previous_snapshot:
        st.session_state["macro_charts"] = previous_snapshot
        st.session_state["macro_data_source"] = "마지막 정상 수집본"

controls_left, controls_right = st.columns([3, 1])
with controls_left:
    data_source = st.session_state.get("macro_data_source", "수집 전")
    if "macro_charts" in st.session_state:
        snapshot_time = st.session_state["macro_charts"].get("fetched_at", "시간 정보 없음")
        st.info(f"시장 데이터: {data_source} · 기준 시각 {snapshot_time}")
    else:
        st.info("아직 검증된 시장 데이터 스냅샷이 없습니다. 최신 데이터를 불러오면 분석 화면을 시작합니다.")
with controls_right:
    refresh_market_data = st.button("최신 데이터 불러오기", type="primary", use_container_width=True)

if refresh_market_data:
    # A button press is an explicit user request for provider traffic.  Clear
    # Streamlit's short cache so this action is genuinely a refresh.
    get_macro_charts.clear()
    with st.spinner("시장 데이터를 확인하고 있습니다. 일부 제공처가 지연되면 마지막 정상 데이터가 유지됩니다."):
        refreshed_macro_charts = get_macro_charts()
    st.session_state["macro_charts"] = refreshed_macro_charts
    st.session_state["macro_data_source"] = "이번 세션 최신 수집"
    if save_macro_snapshot(refreshed_macro_charts):
        st.success("최신 수집본을 저장했습니다.")
    else:
        st.warning("화면에는 최신 데이터를 적용했지만 로컬 스냅샷 저장에는 실패했습니다.")

if "macro_charts" not in st.session_state:
    st.caption("데이터가 없는 상태에서는 매수·매도 판단을 표시하지 않습니다.")
    st.stop()

macro_charts = st.session_state["macro_charts"]
cnn_score, cnn_rating, cnn_history = get_real_cnn_fg()
sector_base = get_sector_baseline()
spy_rsi_val = sector_base.get("S&P 500 (SPY)")
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

# 하나의 국면 판정을 헷징·포트폴리오 화면이 함께 사용한다.
# 신호는 종가 기준이며 실제 비중 조절은 다음 거래일에만 실행한다.
market_regime = classify_market_regime(
    kospi_10y,
    bottom_score=kr_score,
)

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
tab_orion_kr, tab_orion_us, tab_radar, tab_hedging, tab_port, tab_calendar = st.tabs(["🐯 ORION Signal(국장)", "🦅 ORION Signal(미장)", "🔍 종목 발굴 & 타이밍 (리포트)", "🧭 국면별 운용", "💼 포트폴리오 & 맞춤 가이드", "📅 마켓 캘린더"])

with tab_orion_kr:
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
    m_col1.metric("🦅 국채 10년물 금리", summary_dict['TNX_10Y'].split(' (')[0], summary_dict['TNX_10Y'].split(' (')[1].replace(')','').replace('p',''), delta_color="inverse")
    m_col2.metric("🛢️ WTI 원유", summary_dict['WTI_Crude'].split(' (')[0], summary_dict['WTI_Crude'].split(' (')[1].replace(')',''), delta_color="inverse")
    m_col3.metric("💵 원/달러 환율", summary_dict['USD_KRW'].split(' (')[0], summary_dict['USD_KRW'].split(' (')[1].replace(')',''), delta_color="inverse")
    
    # 🐯 코스피 실시간 가격 및 5일선 현황 표시
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
        
        fetched_at = macro_charts.get("fetched_at", "알 수 없음")
        k_col1.metric(f"🐯 KOSPI 현재가 (⏰ {fetched_at})", f"{current_kospi_val:,.2f}", delta=kospi_delta_str)
        k_col2.metric("📈 KOSPI 5일 이평선", f"{kospi_5d_sma:,.2f}")
        k_col3.metric(
            "🎯 5일선 안착 여부", 
            "안착 완료" if is_above else "미안착", 
            f"이격: {gap:+,.2f}p", 
            delta_color="normal" if is_above else "off"
        )
    else:
        k_col1.metric("🐯 KOSPI 현재가", "데이터 없음")
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
    try:
        from data_loader import get_market_news
        news_data = get_market_news("KR", limit=60)
    except Exception as e:
        st.error(f"뉴스 데이터 로드 실패: {e}")
                
    if True:
        try:
            if news_data:
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
            
        st.markdown("<br>", unsafe_allow_html=True)
        save_col1, save_col2 = st.columns([2, 1])
        with save_col1:
            st.info("💡 장중에는 체크를 풀고 자유롭게 테스트하세요. 장 마감 후 최종 확정 시에만 체크하세요.")
            save_regime = st.checkbox("✅ 오늘 장마감 결과로 확정 및 영구 저장 (GitHub 연동)", value=False)
        with save_col2:
            with st.expander("⚙️ 강제 오버라이드"):
                wdo = st.number_input("수동 경고일수 (-1: 자동)", min_value=-1, max_value=5, value=-1, step=1)
                override_val = wdo if wdo != -1 else None

        kr_flow_score, kr_flow_status, kr_flow_details = calculate_cashflow_signal(foreign_futures, oi_trend, rsp_change_pct, kospi_10y)
        
        st.markdown(f"**상태:** {kr_flow_status}")
        for icon, msg in kr_flow_details:
            st.write(f"{icon} {msg}")

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("#### Step 3: 🎯 통합 판정 (Action Plan)")

    kospi_above_ma20 = False
    if not kospi_10y.empty and len(kospi_10y) >= 20:
        try:
            kospi_close = float(kospi_10y["Close"].iloc[-1])
            kospi_ma20 = float(kospi_10y["Close"].rolling(20).mean().iloc[-1])
            kospi_above_ma20 = kospi_close >= kospi_ma20
        except (KeyError, TypeError, ValueError):
            kospi_above_ma20 = False

    regime, action, r_color = calculate_regime_classification(
        kr_macro_score,
        kr_flow_score,
        kospi_above_ma20,
        warning_days_override=override_val,
        save_state=save_regime,
    )
    
    st.markdown(
        f"<div style='background:{r_color}22; border-left: 8px solid {r_color}; padding:20px; border-radius:10px; margin-bottom:20px;'>"
        f"<h2 style='margin-top:0; color:{r_color};'>{regime}</h2>"
        f"<p style='font-size:1.1em; color:#333;'>{action}</p>"
        f"</div>", unsafe_allow_html=True
    )
    
    st.caption("※ 최종 주문 금액은 자금흐름 점수만으로 정하지 않고, '국면별 운용' 탭의 계좌 행동을 우선합니다.")
    
    st.markdown("""
    <div style='background-color:#f8f9fa; padding:15px; border-radius:8px; border:1px solid #ddd; margin-bottom:25px;'>
        <h4 style='margin-top:0; color:#444;'>💡 국면별 비중 조절 규칙</h4>
        <ul style='font-size:0.95em; color:#555;'>
            <li><b>폭락 당일</b>: 새 매수·기술적 손절·인버스 추격을 모두 멈추고 다음 종가를 기다립니다.</li>
            <li><b>바닥 확인 뒤</b>: 5일선·20일선·60일선 회복을 순서대로 확인하고, 한 번에 현금의 10%와 총자산 5%p 중 작은 금액만 투입합니다.</li>
            <li><b>완만한 상승·횡보</b>: 국면별 주식 허용범위를 벗어났을 때만 5%p씩 리밸런싱합니다. 전량매수·전량매도는 하지 않습니다.</li>
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
- 🦅 미국 장단기 금리차 (10Y-3M): {ai_yield_spread} (경기침체/유동성 선행지표)
- 🦅 미국 반도체 업황 강도 (MU vs SOXX 20일 수익률 격차): {ai_mu_vs_soxx} (DRAM 사이클 프록시)
- 🦅 미국 TNX 10Y 금리: {summary_dict.get('TNX_10Y', 'N/A') if 'summary_dict' in locals() else 'N/A'}
- 🦅 WTI 크루드 유가: {summary_dict.get('WTI_Crude', 'N/A') if 'summary_dict' in locals() else 'N/A'}
- 🦅 미국 동일가중 S&P500 (RSP) 전일 등락률: {rsp_val_str} (미국 시장 온기 확인용)
- 🐯 USD/KRW 환율: {summary_dict.get('USD_KRW', 'N/A') if 'summary_dict' in locals() else 'N/A'}
- 🐯 한국 VKOSPI 현재: {ai_vkospi_val} (한국 기관/외인 파생 하락 헷지 팽창도)
- 🐯 외국인 KOSPI 현물 순매수: {summary_dict.get('Foreigner', 'N/A') if 'summary_dict' in locals() else 'N/A'}
- 🐯 기관 KOSPI 현물 순매수: {summary_dict.get('Institutional', 'N/A') if 'summary_dict' in locals() else 'N/A'}
- 🐯 외국인 KOSPI 선물 순매수: {foreign_futures}계약 (방향성 선행지표)
- 🐯 KOSPI 현재가: {kospi_str}
- 🐯 KOSPI 5일 이평선 안착 상태: {kospi_status_str}

[최근 글로벌 속보 요약 (중요도 2 이상)]
{web_news_text}

{upcoming_events_str}

---
위 데이터를 기반으로 다음 3가지 핵심 뼈대로 리포트를 매우 분석적이고 통찰력있게 작성하십시오.
1. **현재 시장 국면 요약 (Market Summary)**: 현재 하락세의 원인, 매크로 수급과 외인 이탈 여부를 종합 진단하십시오.
2. **글로벌 거시 리스크 및 섹터 전망 (Macro & Sector Outlook)**: 
   - 금리/유가/지정학 리스크가 주요 자산에 미칠 영향을 상세히 서술하십시오.
   - [미장 승률 극대화 지침] 안정적으로 우상향하는 미국 시장의 특성과 예정된 빅테크 실적/가이던스를 결합하여, 향후 환율 하락 시 가장 승률과 수익률을 극대화할 수 있는 안전한 진입 시나리오를 구체적으로 제시하십시오.
3. **최종 행동 지침 (CFO Action Plan)**: 보유 중인 우량주 홀딩 여부와 국면별 주식 허용범위를 판단하되, 패닉 중 매도·매수를 동결하고 이후 한 번에 총자산 5%p 이내로만 조정하는 일정을 제시하십시오.
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
- 🦅 미국: {us_phase} | 위험도 {us_danger}점 | 금리차(10Y-3M) {ai_yield_spread}
- 🐯 한국: {kr_phase} | 위험도 {kr_danger}점 | VKOSPI {ai_vkospi_val}
- 🐯 KOSPI: {kospi_str} | 5일선 안착: {kospi_status_str}
- 🐯 외국인 현물: {summary_dict.get('Foreigner', 'N/A') if 'summary_dict' in locals() else 'N/A'} | 환율: {summary_dict.get('USD_KRW', 'N/A') if 'summary_dict' in locals() else 'N/A'}
- 🦅 반도체 업황(MU vs SOX): {ai_mu_vs_soxx} | RSP 등락: {rsp_val_str}"""

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


# --- US Orion Signal ---
with tab_orion_us:
    st.subheader("🦅 ORION Signal (미장)")
    st.caption("미국 증시 특화 매크로, 유동성, 심리 통합 스코어링 시스템")
    
    if "calculate_us_orion_score" in globals() and "get_us_strategic_advice" in globals():
        try:
            total_score, us_phase, components, triggers, metrics = calculate_us_orion_score(macro_charts)
            adv_head, adv_color, adv_actions = get_us_strategic_advice(us_phase, total_score, triggers)

            # ── 첫 화면에서 환경 → 시장 확인 → 주문 허가까지 한 번에 끝낸다. ──
            decision_flow_snapshot = get_us_flow_snapshot()
            decision_flow_dict = {
                ticker: float(item.get("flow_proxy", 0.0))
                for ticker, item in decision_flow_snapshot.get("records", {}).items()
            }
            decision_raw_flow_score, decision_flow_status, _ = calculate_us_flow_signal(
                decision_flow_dict.get("SPY", 0.0),
                decision_flow_dict.get("QQQ", 0.0),
                decision_flow_dict.get("SOXX", 0.0),
            )
            decision_flow_stale = decision_flow_snapshot.get("is_stale", True)
            decision_flow_score = 0 if decision_flow_stale else decision_raw_flow_score
            decision_score = max(0.0, min(100.0, total_score + decision_flow_score * 0.2))
            if us_phase == "DATA_ERROR":
                decision_phase = "DATA_ERROR"
            else:
                decision_phase = "CLEAR" if decision_score >= 65 else "CAUTION" if decision_score >= 40 else "ALERT"
            decision_entry, decision_checks, decision_reasons = evaluate_us_entry_permission(
                macro_charts,
                decision_phase,
                metrics,
                flow_score=decision_flow_score,
                flow_is_stale=decision_flow_stale,
                environment_score=decision_score,
            )
            us_entry_check_labels = {
                "data_quality": "필수 데이터 정상",
                "environment_floor_60": "환경점수 60점 이상",
                "environment_full_65": "10% 선발대 기준 65점 이상",
                "trend_confirmed": "SPY 20일선 상회",
                "breadth_confirmed": "RSP/SPY 최근 5일 개선",
                "price_volume_confirmed": "가격·거래량 상승 확인",
                "falling_knife_released": "낙하 칼날 안전장치 해제",
                "credit_stress_absent": "명확한 신용 스트레스 없음",
            }

            phase_view = {
                "CLEAR": ("🟢", "시장 환경 통과", "신규 매수를 검토할 수 있는 환경입니다."),
                "CAUTION": ("🟡", "시장 환경 주의", "상승 재료는 있지만 할인율·시장 폭 확인이 더 필요합니다."),
                "ALERT": ("🔴", "시장 환경 위험", "위험자산 신규 노출을 늘리지 않는 구간입니다."),
                "DATA_ERROR": ("⚫", "데이터 확인 필요", "필수 데이터가 정상화될 때까지 판단을 보류합니다."),
            }
            phase_icon, phase_label, phase_note = phase_view[us_phase]
            if decision_flow_stale:
                flow_icon, flow_label, flow_note = "⚫", "시장 확인 불가", "가격·거래량 자료가 오래되어 점수에서 제외했습니다."
            elif decision_flow_score > 0:
                flow_icon, flow_label, flow_note = "🟢", "가격·거래량 상승 확인", "SPY·QQQ가 상승했고 거래량이 방향을 뒷받침했습니다. 실제 순매수 자료는 아닙니다."
            elif decision_flow_score < 0:
                flow_icon, flow_label, flow_note = "🔴", "가격·거래량 하락 확인", "당일 가격과 거래량이 시장 환경을 지지하지 않습니다. 실제 순매도 자료는 아닙니다."
            else:
                flow_icon, flow_label, flow_note = "🟡", "시장 확인 중립", "당일 가격·거래량에서 뚜렷한 방향이 없습니다."

            entry_view = {
                "STARTER_GO_10": ("✅", "10% 선발대 허가", "환경점수 65점 이상과 세 확인조건을 모두 통과했습니다."),
                "STARTER_GO_5": ("🟢", "5% 선발대 허가", "핵심 안전장치와 확인조건 3개 중 2개 이상을 통과했습니다."),
                "ENTRY_WAIT": ("⏳", "진입 대기", "확인되지 않은 조건이 남아 있습니다."),
                "FALLING_KNIFE_VETO": ("⛔", "급락 중 진입 금지", "낙하 칼날 안전장치가 해제되지 않았습니다."),
                "CREDIT_STRESS_VETO": ("⛔", "신용 스트레스로 진입 금지", "하이일드 시장이 명확한 위험 신호를 보입니다."),
                "DATA_VETO": ("⛔", "데이터 오류로 진입 금지", "최신 데이터 확인 전에는 주문하지 않습니다."),
            }
            entry_icon, entry_label, entry_note = entry_view[decision_entry]

            st.markdown("### 🚦 오늘의 미장 의사결정")
            d_col1, d_col2, d_col3 = st.columns(3)
            with d_col1:
                st.markdown(f"#### Step 1　{phase_icon} {phase_label}")
                st.metric("ORION 기초 환경", f"{total_score:.1f} / 100", us_phase)
                st.caption(phase_note)
            with d_col2:
                st.markdown(f"#### Step 2　{flow_icon} {flow_label}")
                flow_value = "반영 중지" if decision_flow_stale else f"{decision_flow_score*0.2:+.1f}점"
                st.metric("환경점수 보정", flow_value)
                st.caption(flow_note)
            with d_col3:
                st.markdown(f"#### Step 3　{entry_icon} {entry_label}")
                st.metric("최종 주문 판정", decision_entry)
                st.caption(entry_note)

            if decision_entry == "STARTER_GO_10":
                st.success("미국 투자 예정금의 10% 선발대를 허용합니다. 당일 갭 상승 3% 초과 종목은 추격하지 않습니다.")
            elif decision_entry == "STARTER_GO_5":
                limit_text = " · ".join(decision_reasons) if decision_reasons else "소프트 확인조건 일부 미충족"
                st.info(f"미국 투자 예정금의 5% 선발대만 허용합니다. 제한 이유: {limit_text}")
            else:
                reason_text = " · ".join(decision_reasons) if decision_reasons else "추가 확인 필요"
                st.warning(f"현재 주문을 기다리는 이유: {reason_text}")

            st.markdown("#### 판단 근거 — 숫자가 무엇을 말하는가")
            reason_col1, reason_col2 = st.columns(2)
            liq_change = metrics.get("net_liquidity_4w_change")
            liq_icon = "🟢" if liq_change is not None and liq_change >= 0 else "🔴" if liq_change is not None else "⚫"
            liq_text = f"4주간 {liq_change:+.1f}B" if liq_change is not None else "자료 없음"
            reason_col1.write(f"{liq_icon} **연준 유동성:** {liq_text} — {'확대되어 위험자산에 우호적입니다.' if liq_icon == '🟢' else '축소되어 위험자산에 부담입니다.' if liq_icon == '🔴' else '판단할 수 없습니다.'}")

            tnx_val, tyx_val = metrics.get("tnx"), metrics.get("tyx")
            rate_ok = tnx_val is not None and tyx_val is not None and tnx_val <= 4.65 and tyx_val < 5.20
            rate_icon = "🟢" if rate_ok else "🔴" if tnx_val is not None and tyx_val is not None else "⚫"
            reason_col1.write(f"{rate_icon} **장기금리:** 10년 {tnx_val:.2f}% / 30년 {tyx_val:.2f}% — {'허용 범위입니다.' if rate_ok else '높은 금리가 기술주 적정가치에 부담을 주는 구간입니다.'}" if tnx_val is not None and tyx_val is not None else "⚫ **장기금리:** 자료 없음")

            hy_val, hy_delta = metrics.get("hy_spread"), metrics.get("hy_spread_5d_change")
            credit_ok = hy_val is not None and hy_val < 4.0 and (hy_delta is None or hy_delta <= 0.15)
            credit_icon = "🟢" if credit_ok else "🔴" if hy_val is not None else "⚫"
            reason_col2.write(f"{credit_icon} **신용시장:** HY {hy_val:.2f}% / 5일 {hy_delta:+.2f}%p — {'신용 경색 징후가 없습니다.' if credit_ok else '스프레드 확대를 경계합니다.'}" if hy_val is not None and hy_delta is not None else "⚫ **신용시장:** 자료 없음")

            breadth_gap = metrics.get("rsp_spy_20d_gap")
            breadth_5d = metrics.get("rsp_spy_5d_change")
            breadth_long_ok = breadth_gap is not None and breadth_gap >= 0
            breadth_short_ok = breadth_5d is not None and breadth_5d >= 0
            breadth_icon = "🟢" if breadth_long_ok and breadth_short_ok else "🟡" if breadth_long_ok else "🔴" if breadth_gap is not None else "⚫"
            if breadth_gap is not None and breadth_5d is not None:
                breadth_note = "구조와 단기 방향이 모두 개선 중입니다." if breadth_icon == "🟢" else "20일 구조는 양호하지만 최근 5일은 약해졌습니다." if breadth_icon == "🟡" else "대형주 편중이 이어지고 있습니다."
                reason_col2.write(f"{breadth_icon} **시장 폭:** 20일 {breadth_gap*100:+.1f}%p / 최근 5일 {breadth_5d*100:+.1f}% — {breadth_note}")
            else:
                reason_col2.write("⚫ **시장 폭:** 자료 없음")

            with st.expander("세부 점수와 전체 체크리스트 보기", expanded=False):
                score_table = pd.DataFrame({
                    "영역": ["유동성·금리", "신용·변동성", "시장 폭·추세", "보조 위험선호"],
                    "점수": [components['macro'], components['credit'], components['strength'], components['aux']],
                    "배점": [35, 35, 25, 5],
                })
                score_table["판독"] = score_table.apply(lambda row: f"{row['점수']:.1f} / {row['배점']}", axis=1)
                st.dataframe(score_table[["영역", "판독"]], hide_index=True, use_container_width=True)
                for key, passed in decision_checks.items():
                    st.write(f"{'✅' if passed else '❌'} {us_entry_check_labels.get(key, key)}")
                for trigger in dict.fromkeys(triggers):
                    detail_icon, detail_text = get_us_trigger_display(trigger)
                    st.write(f"{detail_icon} {detail_text}")

            st.caption("※ 가격·거래량 점수는 실제 ETF 설정·환매나 기관 순매수가 아닌 단기 시장 확인용 프록시입니다.")
            st.divider()
            st.markdown("### 🔎 상세 지표·뉴스·AI 해설")

            # 1. AI Strategic Advice Box
            st.markdown(
                f"<div style='background:{adv_color}22; border-left: 8px solid {adv_color}; padding:20px; border-radius:10px; margin-bottom:20px;'>"
                f"<h2 style='margin-top:0; color:{adv_color};'>{adv_head}</h2>"
                f"<p style='font-size:0.95em; color:#888; margin-bottom:10px;'>가격·거래량 확인 전 기초 환경 점수 {total_score:.1f}점 · {us_phase}</p>"
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
                u_col4.metric("연준 순유동성", f"${liq_val:.1f}B")
            else:
                u_col4.metric("연준 순유동성", "N/A")
                
            # 2.5 🦅 SPY 실시간 가격 및 5일선 현황 표시
            sk_col1, sk_col2, sk_col3 = st.columns(3)
            spy_10y = macro_charts.get("spy_10y", pd.DataFrame())
            if not spy_10y.empty and 'Close' in spy_10y:
                current_spy_val = round(float(spy_10y['Close'].iloc[-1]), 2)
                spy_5d_sma = round(float(spy_10y['Close'].rolling(5).mean().iloc[-1]), 2)
                spy_gap = current_spy_val - spy_5d_sma
                spy_is_above = current_spy_val >= spy_5d_sma
                
                # SPY 등락률 연산
                if len(spy_10y['Close']) >= 2:
                    prev_spy = float(spy_10y['Close'].iloc[-2])
                    spy_change_pts = current_spy_val - prev_spy
                    spy_change_pct = (spy_change_pts / prev_spy) * 100.0
                    spy_delta_str = f"{spy_change_pct:+.2f}% (${spy_change_pts:+.2f})"
                else:
                    spy_delta_str = "0.00% ($0.00)"
                
                fetched_at = macro_charts.get("fetched_at", "알 수 없음")
                sk_col1.metric(f"🦅 SPY 현재가 (⏰ {fetched_at})", f"${current_spy_val:,.2f}", delta=spy_delta_str)
                sk_col2.metric("📈 SPY 5일 이평선", f"${spy_5d_sma:,.2f}")
                sk_col3.metric(
                    "🎯 5일선 안착 여부", 
                    "안착 완료" if spy_is_above else "미안착", 
                    f"이격: ${spy_gap:+,.2f}", 
                    delta_color="normal" if spy_is_above else "off"
                )
            else:
                sk_col1.metric("🦅 SPY 현재가", "데이터 없음")
                sk_col2.metric("📈 SPY 5일 이평선", "데이터 없음")
                sk_col3.metric("🎯 5일선 안착 여부", "확인 불가")
                
            # 3. Score Details and BTC Caveat
            st.markdown("---")
            st.markdown("#### 📊 세부 스코어보드 및 보조 지표")
            score_col1, score_col2 = st.columns(2)
            with score_col1:
                st.progress(components['macro'] / 35.0, text=f"매크로 유동성 (35점 만점): {components['macro']:.1f}점")
                st.progress(components['credit'] / 35.0, text=f"신용 및 심리 (35점 만점): {components['credit']:.1f}점")
            with score_col2:
                st.progress(components['strength'] / 25.0, text=f"시장 폭·추세 (25점 만점): {components['strength']:.1f}점")
                st.progress(components['aux'] / 5.0, text=f"보조 위험선호 (5점 만점): {components['aux']:.1f}점")
                
            st.info("⚠️ **비트코인(BTC) 해석 주의**: 비트코인은 글로벌 유동성의 선행 지표 성격을 띠지만, 가상자산 시장 고유의 이슈(거래소 리스크 등)로 인해 매크로 흐름과 무관하게 가격이 왜곡될 수 있으므로 절대적인 지표로 맹신하지 마십시오.")

        except Exception as e:
            st.error(f"미국 시그널 로딩 중 오류: {e}")
    else:
        st.info("US Macro logic not loaded yet.")

    st.markdown("---")
    st.markdown("### 📰 실시간 미장 핵심 뉴스")
    from data_loader import get_market_news, get_us_flow_report
    
    us_news = get_market_news("US", limit=7)
    if us_news:
        for n in us_news:
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
        st.write("수집된 미장 뉴스가 없습니다.")
        
    st.markdown("---")
    st.markdown("### 📈 미국 주요 ETF 가격·거래량 프록시")
    st.caption("ETF 종가 등락과 거래량을 결합한 단기 시장 확인용 점수입니다. 실제 설정·환매나 기관 순매수 데이터는 아니며, 양수는 상승 방향 확인, 음수는 하락 방향 확인을 뜻합니다.")
    us_flow = get_us_flow_report()
    us_flow_snapshot = get_us_flow_snapshot()
    
    sf_col1, sf_col2, sf_col3 = st.columns(3)
    
    def parse_us_flow(md_text):
        res = {}
        if not md_text: return res
        for line in md_text.split('\n'):
            if '|' in line and '**' in line:
                parts = [p.strip() for p in line.split('|')]
                if len(parts) >= 6:
                    ticker = parts[1].replace('**', '').strip()
                    score_str = parts[5].replace('**', '').strip()
                    try:
                        res[ticker] = float(score_str)
                    except:
                        pass
        return res

    flow_dict = {
        ticker: float(item.get("flow_proxy", 0.0))
        for ticker, item in us_flow_snapshot.get("records", {}).items()
    }
    if not flow_dict:
        flow_dict = parse_us_flow(us_flow)
    
    def render_us_flow(col, label, ticker):
        score = flow_dict.get(ticker, 0.0)
        state = "상승 확인" if score > 0 else "하락 확인" if score < 0 else "중립"
        col.metric(f"{label}", f"스코어: {score:+.2f}", f"{state}", delta_color="normal" if score > 0 else "inverse" if score < 0 else "off")

    if flow_dict:
        render_us_flow(sf_col1, "🏢 SPY (S&P 500)", "SPY")
        render_us_flow(sf_col2, "🚀 QQQ (Nasdaq)", "QQQ")
        render_us_flow(sf_col3, "💻 SOXX (반도체)", "SOXX")
        flow_date = us_flow_snapshot.get("market_as_of") or "알 수 없음"
        if us_flow_snapshot.get("is_stale", True):
            st.error(f"⛔ 수급 프록시가 오래되었습니다(시장 기준일 {flow_date}). 최종 진입 점수와 주문 허가에 반영하지 않습니다.")
        else:
            st.caption(f"시장 기준일: {flow_date} · 실제 펀드플로우가 아닌 가격·거래량 프록시")
    else:
        sf_col1.metric("🏢 SPY 프록시", "데이터 없음", delta_color="off")
        sf_col2.metric("🚀 QQQ 프록시", "데이터 없음", delta_color="off")
        sf_col3.metric("💻 SOXX 프록시", "데이터 없음", delta_color="off")
        
    if us_flow:
        with st.expander("📊 가격·거래량 프록시 원본 데이터 확인"):
            st.markdown(us_flow)
    else:
        st.write("미장 수급 동향 리포트를 불러올 수 없습니다.")
        
    st.markdown("<br>", unsafe_allow_html=True)
    
    # 3. AI 브리핑 버튼 이식 (CFO & 스마트 컨트롤룸)
    us_summary_dict = {
        'TNX_10Y': f"{metrics.get('tnx', 0):.2f}%" if metrics.get('tnx') else "N/A",
        'DXY': f"{metrics.get('dxy', 0):.2f}" if metrics.get('dxy') else "N/A",
        'HY_Spread': f"{metrics.get('hy_spread', 0):.2f}%" if metrics.get('hy_spread') else "N/A",
        'Net_Liquidity': f"${metrics.get('net_liquidity', 0):.1f}B" if metrics.get('net_liquidity') else "N/A",
        'VIX': f"{metrics.get('vix', 0):.2f}" if metrics.get('vix') else "N/A",
        'SPY_Flow': flow_dict.get("SPY", "N/A"),
        'QQQ_Flow': flow_dict.get("QQQ", "N/A"),
        'SOXX_Flow': flow_dict.get("SOXX", "N/A")
    }

    if "us_cfo_report_cache" not in st.session_state:
        st.session_state["us_cfo_report_cache"] = ""
 
    if st.button("🔄 CFO AI 미장 브리핑 생성", key="us_cfo_report_btn"):
        with st.spinner("거시경제 CFO AI가 미장 흐름을 분석하고 있습니다..."):
            from signals import generate_us_economic_commentary
            st.session_state["us_cfo_report_cache"] = generate_us_economic_commentary(us_summary_dict, us_phase)
            
    if st.session_state["us_cfo_report_cache"]:
        ai_commentary = st.session_state["us_cfo_report_cache"]
        if "⚠️" in ai_commentary:
            st.error(ai_commentary)
        else:
            st.info(f"**[미장 CFO 통합 브리핑] {us_phase}**\n\n{ai_commentary}")
    else:
        st.info("👈 버튼을 눌러 CFO AI 미장 분석 브리핑을 생성하세요.")

    st.divider()
    st.markdown("### 🤖 실시간 AI 종합 브리핑 (미장)")
    
    if st.button("🔄 AI 미장 관제 리포트 생성 (뉴스 + 매크로 종합)", type="primary", key="us_ai_reporter_btn"):
        with st.spinner("Gemini 2.5 Flash가 미장 속보와 매크로 수치를 종합하여 리포트를 작성 중입니다..."):
            market_ctx = f"판정결과: {adv_head}\n종합점수: {total_score:.1f}점\n현재국면: {us_phase}"
            
            try:
                import sys
                import importlib
                import ai_reporter
                importlib.reload(ai_reporter)
                # We can reuse the smart control room report function, it relies on market_ctx
                from ai_reporter import generate_smart_control_room_report
                report = generate_smart_control_room_report(market_ctx, target_market="US")
                st.session_state["us_ai_report_cache"] = report
            except Exception as e:
                st.error(f"리포트 생성 모듈 로드 실패: {e}")

    if "us_ai_report_cache" in st.session_state:
        st.markdown("<div class='ai-report-container'>", unsafe_allow_html=True)
        st.markdown(st.session_state["us_ai_report_cache"])
        st.markdown("</div>", unsafe_allow_html=True)
    else:
        st.info("👈 상단의 버튼을 눌러 최신 미장 시황 리포트를 생성하세요.")

    st.divider()

    # ── [NEW] ORION 미국 매크로 & 자금흐름 통합 국면 판별기 ──
    st.markdown("### 🧮 ORION 상세 산식 재검산")
    st.caption("위의 3단계 결론을 구성하는 내부 점수입니다. 실제 주문 판정은 상단의 '오늘의 미장 의사결정'을 따릅니다.")
    
    uc_macro, uc_flow = st.columns(2)
    
    with uc_macro:
        st.markdown("#### Step 1: 📊 매크로 환경 우호도 (Macro Environment)")
        us_macro_status = "🟢 우호적" if components['macro'] + components['credit'] > 45 else "🟡 확인 필요" if components['macro'] + components['credit'] >= 30 else "🔴 부담"
        st.markdown(f"**상태:** {us_macro_status}")
        for trig in triggers:
            detail_icon, detail_text = get_us_trigger_display(trig)
            st.write(f"{detail_icon} {detail_text}")
            
    with uc_flow:
        st.markdown("#### Step 2: 📈 가격·거래량 확인")
        
        st.caption("실제 자금 유출입이 아니라 당일 등락률×거래량 비율로 계산한 자동 프록시입니다. 임의 수동 보정은 사용하지 않습니다.")
        raw_us_flow_score, us_flow_status, us_flow_details = calculate_us_flow_signal(
            flow_dict.get("SPY", 0.0),
            flow_dict.get("QQQ", 0.0),
            flow_dict.get("SOXX", 0.0),
        )
        us_flow_score = 0 if us_flow_snapshot.get("is_stale", True) else raw_us_flow_score
        if us_flow_snapshot.get("is_stale", True):
            us_flow_status = "⚫ 노후 데이터 — 점수 반영 중지"
        
        st.markdown(f"**상태:** {us_flow_status}")
        for icon, msg in us_flow_details:
            st.write(f"{icon} {msg}")

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("#### Step 3: 🎯 환경 점수 재계산과 주문 허가")

    # 미국 환경 점수에 가격·거래량 프록시를 제한적으로 반영한다.
    final_us_score = max(0.0, min(100.0, total_score + (us_flow_score * 0.2)))
    if us_phase == "DATA_ERROR":
        final_us_phase = "DATA_ERROR"
    else:
        final_us_phase = "CLEAR" if final_us_score >= 65 else "CAUTION" if final_us_score >= 40 else "ALERT"
    entry_state, entry_checks, entry_reasons = evaluate_us_entry_permission(
        macro_charts,
        final_us_phase,
        metrics,
        flow_score=us_flow_score,
        flow_is_stale=us_flow_snapshot.get("is_stale", True),
        environment_score=final_us_score,
    )

    if entry_state == "STARTER_GO_10":
        decision_head = "🟢 10% 선발대 주문 허가"
        decision_color = "#2E7D32"
        decision_actions = ["환경점수 65점 이상과 세 소프트 확인조건을 모두 통과했습니다. 예정금의 10%만 분할 진입합니다."]
    elif entry_state == "STARTER_GO_5":
        decision_head = "🟢 5% 선발대 주문 허가"
        decision_color = "#558B2F"
        decision_actions = ["핵심 안전장치는 통과했지만 일부 확인조건이 남았습니다. 예정금의 5%만 분할 진입합니다."]
    elif entry_state == "ENTRY_WAIT":
        decision_head = f"🟡 환경점수 {final_us_phase} · 주문은 대기 (ENTRY_WAIT)"
        decision_color = "#F9A825"
        decision_actions = ["환경점수는 검토 가능 구간이지만 주문 조건이 모두 확인되지 않았습니다. 신규 자금은 투입하지 않습니다."]
    else:
        decision_head = f"🔴 신규 주문 거부 ({entry_state})"
        decision_color = "#C62828"
        decision_actions = ["데이터·낙하 칼날·신용 안전장치가 정상화되기 전까지 신규 주문을 금지합니다."]
    
    st.markdown(
        f"<div style='background:{decision_color}22; border-left: 8px solid {decision_color}; padding:20px; border-radius:10px; margin-bottom:20px;'>"
        f"<h2 style='margin-top:0; color:{decision_color};'>{decision_head}</h2>"
        f"<p style='font-size:0.95em; color:#888; margin-bottom:10px;'>환경 스코어 {final_us_score:.1f}점 · {final_us_phase}</p>"
        f"<ul>" + "".join([f"<li style='font-size:1.05em; margin-bottom:5px;'>{a}</li>" for a in decision_actions]) + "</ul>"
        f"</div>", unsafe_allow_html=True
    )

    if entry_state == "STARTER_GO_10":
        st.success("✅ 10% 선발대 허가: 미국 투자 예정금의 10%만 분할 진입. 갭 상승 3% 초과 종목은 추격 금지.")
    elif entry_state == "STARTER_GO_5":
        st.info(f"🟢 5% 선발대 허가: 제한 이유 — {', '.join(entry_reasons) if entry_reasons else '일부 확인조건 미충족'}")
    elif entry_state in ("DATA_VETO", "FALLING_KNIFE_VETO", "CREDIT_STRESS_VETO"):
        st.error(f"⛔ 신규 진입 거부: {', '.join(entry_reasons)}")
    else:
        st.warning(f"⏳ 신규 진입 대기: {', '.join(entry_reasons)}")

    with st.expander("미장 진입 허가 체크리스트"):
        for key, passed in entry_checks.items():
            st.write(f"{'✅' if passed else '❌'} {us_entry_check_labels.get(key, key)}")
    
    st.markdown("##### 💼 이번 판정의 계좌 행동")
    if entry_state in ("STARTER_GO_5", "STARTER_GO_10"):
        allowed_pct = 10 if entry_state == "STARTER_GO_10" else 5
        st.success(f"**신규 투자 허용:** 미국 투자 예정금의 {allowed_pct}% · 나머지 현금 {100-allowed_pct}% 대기")
        st.markdown("**보유 종목:** 기존 핵심 포지션 유지. 종목별 갭 상승 3% 초과 시 그날은 주문하지 않습니다.")
        st.markdown("**다음 단계:** 환경점수와 세 확인조건을 다시 점검한 뒤에만 추가 분할을 검토합니다.")
    elif entry_state == "ENTRY_WAIT":
        st.warning("**신규 투자 허용:** 0% · 현재 예정금은 전액 대기")
        st.markdown("**보유 종목:** 시장 신호만으로 매도하지 않고 기존 비중을 유지합니다.")
        st.markdown(f"**재확인 조건:** {', '.join(entry_reasons)}")
    else:
        st.error("**신규 투자 허용:** 0% · 안전장치 해제 또는 데이터 정상화 전까지 주문 금지")
        st.markdown("**보유 종목:** 패닉성 전량매도는 하지 않으며, 별도 보유종목 원칙으로 판단합니다.")
    
    st.divider()
    st.markdown("### 📋 웹 버전 Gemini Pro 복사용 프롬프트 (미장 전용)")
    us_news_lines = [f"- [{n.get('sentiment', '중립')}/중요도:{n.get('importance', 0)}] {n.get('title_ko', '')} (대응: {n.get('action_point', '')})" for n in us_news[:40]] if us_news else ["수집된 뉴스가 없습니다."]
    us_flow_prompt_text = (
        f"시장 기준일 {us_flow_snapshot.get('market_as_of', 'N/A')} | "
        f"SPY {flow_dict.get('SPY', 0):+.2f} | QQQ {flow_dict.get('QQQ', 0):+.2f} | "
        f"RSP {flow_dict.get('RSP', 0):+.2f} | SOXX {flow_dict.get('SOXX', 0):+.2f}\n"
        "※ 실제 펀드플로우가 아닌 당일 가격·거래량 프록시"
    )
    us_web_prompt = f"""너는 월스트리트 최고 수준의 매크로 애널리스트다.
[ORION 미장 판정] 주문상태 {entry_state} | 환경점수 {final_us_score:.1f} | 환경국면 {final_us_phase} | 미충족 조건 {', '.join(entry_reasons) if entry_reasons else '없음'}
[핵심 지표] TNX {metrics.get('tnx')}% | DXY {metrics.get('dxy')} | HY스프레드 {metrics.get('hy_spread')}% | 순유동성 ${metrics.get('net_liquidity', 0):.1f}B
[최근 미국 뉴스]
{chr(10).join(us_news_lines)}
[미국 ETF 가격·거래량 확인 프록시]
{us_flow_prompt_text}
---
위 데이터를 바탕으로 미국 시장 국면 진단, 섹터별 전망, 이번 주 구체적 행동 지침(진입/관망/축소)을 작성하라."""
    st.code(us_web_prompt, language="markdown")
    
    st.divider()
    st.caption("👇 아래 3개 쓰레드용 글감은 AI(Claude, Gemini 등)에 붙여넣어 쓰레드 포스트를 자동 생성할 수 있습니다.")

    top_us_news_lines = []
    if us_news:
        top_us_news = [n for n in us_news if n.get("importance", 0) >= 3][:10]
        for n in top_us_news:
            t  = n.get("title_ko", n.get("title", ""))
            s  = n.get("sentiment", "중립")
            a  = n.get("action_point", "")
            top_us_news_lines.append(f"- [{s}] {t}\n  → 대응: {a}")
    top_us_news_text = "\n".join(top_us_news_lines) if top_us_news_lines else "주요 뉴스 없음"

    us_thread_indicators = f"""- ORION 미장 주문 신호: {decision_head} ({entry_state})
- 🦅 미국 환경 국면: {final_us_phase} | 스코어 {final_us_score:.1f}점
- 🦅 핵심 지표: TNX {metrics.get('tnx')}% | DXY {metrics.get('dxy')} | HY {metrics.get('hy_spread')}% | 순유동성 ${metrics.get('net_liquidity', 0):.1f}B
- 🦅 ETF 가격·거래량 프록시: SPY {flow_dict.get('SPY', 0):.2f} | QQQ {flow_dict.get('QQQ', 0):.2f} | SOXX {flow_dict.get('SOXX', 0):.2f}"""

    import calendar_manager
    upcoming_events_str = calendar_manager.get_upcoming_events_string()

    with st.expander("📰 글감 ① — 오늘의 미장 핵심 뉴스 1편 (복사해서 AI에 붙여넣기)", expanded=False):
        thread_prompt_us_news = f"""너는 'ORION 트레이더'라는 쓰레드(Threads) SNS 계정을 운영하는 개인 투자자야. 주로 미국 주식(미장)을 다뤄.
아래 오늘의 주요 뉴스들을 분석해서, 쓰레드에 올릴 글을 써줘.

[작성 규칙 — 반드시 지켜줘]
- 말투: 정중한 존댓말이 아니라, 분석적이면서도 시크하고 단호한 '반말'(~다, ~지, ~한다)로 작성해줘.
- 첫 포스트 (Hook) 어그로 극대화: 첫 1~2줄에 스크롤을 멈추게 만드는 강렬한 질문이나 모순을 던져줘.
- 전체 구성: 메인 포스트 1개 + 댓글 4~5개로 나눠서 작성
- 문장은 짧게 (한 문장 최대 2줄), 줄바꿈 자주 사용 (모바일 가독성)
- 마지막 댓글은 반드시 "내일/이번 주 미국장 주목할 것:" 으로 마무리

[오늘의 미국 주요 뉴스]
{top_us_news_text}

[오늘 미장 ORION 시스템 판정]
{us_thread_indicators}

위 뉴스 중 가장 임팩트가 큰 1~2개 뉴스를 골라서 주식 시장에 미칠 영향을 풀어써줘."""
        st.code(thread_prompt_us_news, language="markdown")

    with st.expander("📊 글감 ② — 오늘 미장 장세와 지표 분석 1편 (복사해서 AI에 붙여넣기)", expanded=False):
        thread_prompt_us_market = f"""너는 'ORION 트레이더'라는 쓰레드(Threads) SNS 계정을 운영하는 개인 투자자야. 미국 주식 시장을 주로 분석해.
오늘 미국 시장 지표와 수급 데이터를 분석해서 쓰레드에 올릴 글을 써줘.

[작성 규칙 — 반드시 지켜줘]
- 말투: 시크하고 단호한 '반말'(~다, ~지, ~한다).
- 첫 포스트 (Hook) 어그로 극대화. (예: "엔비디아 3% 빠졌는데 나스닥 수급 프록시는 오히려 강세? 뭐지?")
- 전체 구성: 메인 포스트 1개 + 댓글 4~5개로 나눠서 작성
- 데이터를 그냥 나열하지 말고, "이게 왜 중요한지" 의미 해석에 집중 (예: 하이일드 스프레드, 순유동성)
- 마지막 댓글은 "ORION 시스템 미장 신호:" 로 마무리

[오늘 ORION 시스템 미장 지표 데이터]
{us_thread_indicators}

위 데이터를 바탕으로, 오늘 미국 시장에서 가장 주목해야 할 지표 1~2개를 골라 의미를 풀어써줘."""
        st.code(thread_prompt_us_market, language="markdown")

    with st.expander("📅 글감 ③ — 이번 주 실적/이벤트 주목 포인트 1편 (복사해서 AI에 붙여넣기)", expanded=False):
        thread_prompt_us_events = f"""너는 'ORION 트레이더'라는 쓰레드(Threads) SNS 계정을 운영하는 개인 투자자야.
이번 주/다음 주 예정된 글로벌 매크로 이벤트와 실적 발표를 기반으로 쓰레드 글을 써줘.

[작성 규칙 — 반드시 지켜줘]
- 말투: 시크하고 단호한 '반말'(~다, ~지, ~한다).
- 첫 포스트 (Hook) 어그로 극대화.
- 전체 구성: 메인 포스트 1개 + 댓글 4~5개로 나눠서 작성
- 이벤트가 미장(S&P 500, 나스닥)에 미칠 영향 위주로 서술
- 마지막 댓글은 "이번 주 미장 관전 포인트:" 로 마무리

[이번 주~다음 주 주요 일정]
{upcoming_events_str}

[현재 미국 시장 맥락]
{us_thread_indicators}"""
        st.code(thread_prompt_us_events, language="markdown")

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
    us_input = c1.text_input("🦅 미국 주식", "TSMC, 브로드컴, 버티브")
    kr_input = c2.text_input("🐯 한국 주식", "LS ELECTRIC")
    krx_status = get_krx_mapping_status()
    if krx_status["available"]:
        st.caption(
            f"한국 주식은 KOSPI·KOSDAQ 전체 종목명 또는 6자리 코드로 검색할 수 있습니다 "
            f"(현재 {krx_status['stock_count']:,}종목). 신규 상장주·스팩·일부 소형주는 "
            "외부 재무정보가 부족해 가격·기술지표만 표시될 수 있습니다."
        )
    else:
        st.warning(
            "⚠️ KRX 전체 종목 목록을 불러오지 못해 비상 종목 목록으로 검색 중입니다. "
            "잠시 후 다시 검색하면 자동으로 복구를 시도합니다."
        )

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

with tab_radar: # Merged AI Report
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

    st.markdown(f"<div style='background:{us_risk_color}22; border-left: 6px solid {us_risk_color}; padding:15px; border-radius:8px; font-weight:bold; font-size:1.1em; margin-bottom:10px;'>🦅 [글로벌 마스터] {us_risk_grade}</div>", unsafe_allow_html=True)
    for icon, msg in us_risk_alerts:
        st.markdown(f"<div style='font-size:0.95em; margin-left:15px; margin-bottom:5px;'>{icon} {msg}</div>", unsafe_allow_html=True)
        
    st.markdown("<br>", unsafe_allow_html=True)
    
    st.markdown(f"<div style='background:{kr_risk_color}22; border-left: 4px solid {kr_risk_color}; padding:10px; border-radius:6px; font-weight:bold; margin-bottom:10px;'>🐯 [로컬 종속 레이어] {kr_risk_grade}</div>", unsafe_allow_html=True)
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
        st.markdown(f"**🦅 미국 진바닥 확률 (US Market)**")
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
        st.markdown(f"**🐯 한국 진바닥 확률 (KOSPI)**")
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
        st.markdown(f"**🦅 미국 반등 신뢰도**")
        us_rec_verdict, us_rec_signals, us_rec_score = calculate_recovery_confirmation(
            rsp_10y, spy_10y, hyg_10y, ief_10y
        )
        st.markdown(f"**{us_rec_verdict}**")
        for icon, msg in us_rec_signals:
            st.markdown(f"- {icon} {msg}")

    with r_col2:
        st.markdown(f"**🐯 한국 매크로 안전도**")
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
            f"🦅 {us_adv_head}</div>", unsafe_allow_html=True
        )
        st.caption(f"판단 근거: 위험 {us_danger}점 · 바닥 {us_score}% · 반등 신뢰도 {us_rec_score} · {us_phase}")
        for act in us_adv_actions:
            st.markdown(f"- {act}")

    with adv_col2:
        st.markdown(
            f"<div style='background:{kr_adv_color}22; border-left: 6px solid {kr_adv_color}; "
            f"padding:15px; border-radius:8px; font-weight:bold; font-size:1.05em; margin-bottom:10px;'>"
            f"🐯 {kr_adv_head}</div>", unsafe_allow_html=True
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
        
        tab_us_bt, tab_kr_bt = st.tabs(["🦅 미국장 (S&P 500)", "🐯 한국장 (KOSPI)"])
        
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
        "🦅 미국 AI & 클라우드":              ["PLTR","CRWD","SNOW","DDOG","NET","SOUN","MDB","ZS","MNDY"],
        "🦅 미국 혁신성장 (우주/바이오/핀테크)": ["IONQ","SOFI","RIVN","CELH","RKLB","ASTS","CRSP","LUNR","SYM","HOOD"],
        "🐯 한국 반도체 소부장 (HBM/AI)":        ["피에스케이홀딩스", "한미반도체", "테크윙", "HPSP", "이수페타시스", "에이직랜드", "디아이", "원익IPS", "동진쎄미켐", "주성엔지니어링", "리노공업", "하나마이크론"],
        "🐯 한국 K-뷰티 & K-푸드":            ["실리콘투","클래시스","파마리서치","삼양식품","브이티","에이피알","휴젤"],
        "🐯 한국 바이오텍 & 헬스케어":          ["알테오젠","HLB","리가켐바이오","루닛","뷰노","제이엘케이"],
        "🐯 한국 전력기기 & 로봇":             ["HD현대일렉트릭","레인보우로보틱스","두산로보틱스","LS ELECTRIC"],
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

with tab_radar: # Merged AI Report  # 🤖 AI 참모 리포트
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
        f"- 🦅 미국: {us_phase} | 위험 탐지 {us_danger}점 | 진바닥 확률 {us_score}% | 반등 신뢰도 {us_rec_score}/100",
        f"  → 시스템 제언: {us_adv_head}",
        f"- 🐯 한국: {kr_phase} | 위험 탐지 {kr_danger}점 | 진바닥 확률 {kr_score}% | 매크로 안전도 {kr_macro_score}/100",
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
    st.caption("보유 종목과 매수가를 입력하면 현재 손익뿐 아니라, 현재 국면에서 실제로 보유·부분축소할 시점도 함께 보여드립니다.")

    st.markdown("#### 📝 보유 종목 입력")
    st.info(
        "**입력 형식:** `종목명:매수가:현재평가액(만원)` (평가액은 생략 가능)\n\n"
        "🦅 미국: `브로드컴:320.5:800, 버티브:250:500`\n\n"
        "🐯 한국: `LS ELECTRIC:185000:1000, 피에스케이홀딩스:120000:700`\n\n"
        "현재평가액까지 쓰면 부분 매도 금액을 만원 단위로 계산합니다."
    )

    col_us, col_kr = st.columns(2)
    port_us_raw = col_us.text_input("🦅 미국 보유 종목", "브로드컴:320.5, 버티브:250, TSMC:180")
    port_kr_raw = col_kr.text_input("🐯 한국 보유 종목", "LS ELECTRIC:185000")

    def parse_portfolio_input(raw: str, region: str):
        items = []
        for chunk in raw.split(","):
            chunk = chunk.strip()
            if ":" not in chunk:
                continue
            parts = chunk.rsplit(":", 2)
            if len(parts) in (2, 3):
                name = parts[0].strip()
                try:
                    price = float(parts[1].strip().replace(",", ""))
                    holding_value = (
                        float(parts[2].strip().replace(",", ""))
                        if len(parts) == 3 and parts[2].strip()
                        else None
                    )
                    items.append((name, price, holding_value, region))
                except ValueError:
                    pass
        return items

    def portfolio_fundamental_score(stock):
        score = 0
        rev_g = float(stock.get("Rev_Growth") or 0)
        op_m = float(stock.get("Op_Margin") or 0)
        roe_v = float(stock.get("ROE") or 0)
        peg_v = float(stock.get("PEG") or 99)
        per_v = stock.get("PER")
        if rev_g >= 0.20:
            score += 1
        if op_m >= 0.10 or stock.get("Is_Turnaround", False):
            score += 1
        if roe_v >= 0.05:
            score += 1
        if 0 < peg_v <= 1.5:
            score += 1
        if per_v and float(per_v) < 30:
            score += 1
        return score

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
            for i, (name, buy_price, holding_value, region) in enumerate(port_items):
                prog.progress((i + 1) / len(port_items), text=f"[{i+1}/{len(port_items)}] '{name}' 재무제표 교차 검증 중...")
                d = get_stock_data(name, is_kr=(region == "한국"), fast_mode=False)
                d["Region"]    = region
                d["BuyPrice"]  = buy_price
                d["HoldingValue"] = holding_value
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
                        "지역":        "🦅" if region == "미국" else "🐯",
                        "매수가":      f"${buy_p:,.2f}" if region == "미국" else f"{int(buy_p):,}원",
                        "현재가":      fmt_price(cur_p, region),
                        "평가액":      f"{d['HoldingValue']:,.0f}만원" if d.get("HoldingValue") is not None else "미입력",
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
                st.markdown("### ✂️ 2. 지금 보유주식을 팔아야 하나요?")
                regime_label = f"{market_regime.get('icon', '⚪')} {market_regime.get('label', '판별 중')}"
                st.caption(
                    f"한국시장 종가 기준 국면: {regime_label}. "
                    "손실률만으로 팔지 않고 시장 패닉·종목 추세·펀더멘탈을 함께 확인합니다."
                )
                holding_action_rows = []
                for d in port_data:
                    buy_p = d.get("BuyPrice")
                    cur_p = d.get("Price")
                    if cur_p is None or buy_p in (None, 0):
                        continue
                    pnl_pct = (float(cur_p) - float(buy_p)) / float(buy_p) * 100
                    if d.get("Region") == "한국":
                        stock_action = build_holding_action(
                            d,
                            market_regime,
                            holding_value=d.get("HoldingValue"),
                            fundamental_score=portfolio_fundamental_score(d),
                            pnl_pct=pnl_pct,
                        )
                        amount_text = (
                            f"{stock_action['sell_value']:,.0f}만원"
                            if stock_action.get("sell_value")
                            else "0원"
                            if stock_action["sell_fraction"] == 0
                            else f"보유액의 {stock_action['sell_fraction'] * 100:.0f}%"
                        )
                        action_text = stock_action["label"]
                        reason_text = stock_action["trigger"]
                    else:
                        action_text = "미국 국면 별도 확인"
                        amount_text = "-"
                        reason_text = "이 화면의 국면 판정은 KOSPI 기준이므로 미국 보유주식에는 강제 적용하지 않습니다."
                    holding_action_rows.append(
                        {
                            "종목": d["Name"],
                            "오늘 행동": action_text,
                            "매도 금액": amount_text,
                            "판단 이유": reason_text,
                            "실행 시점": "종가 확인 후 다음 거래일",
                        }
                    )
                if holding_action_rows:
                    st.dataframe(
                        pd.DataFrame(holding_action_rows),
                        width="stretch",
                        hide_index=True,
                    )
                st.info(
                    "폭락 당일에는 기술적 매도를 동결합니다. 단, 회계 부정·유동성 위기·핵심 사업 훼손처럼 "
                    "기업 자체의 중대한 악재는 이 안전장치보다 우선해 별도 판단해야 합니다."
                )

                st.markdown("---")
                st.markdown("### 🧭 3. 종목별 종합 분석")

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
                        f"{'🦅' if region=='미국' else '🐯'} **{d['Name']}** | "
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

with tab_port:
    with st.expander("참고 · 보유종목 판단에 적용하는 11가지 원칙"):
        st.markdown(
            """
1. 매출·이익·현금흐름이 장기간 개선되는 기업을 우선합니다.
2. 지수와 여러 우량주로 나눠 단일 기업 위험을 줄입니다.
3. 시장 국면마다 주식 **허용범위**를 두되, 즉시 맞춰야 할 목표로 쓰지 않습니다.
4. 폭락 당일에는 기술적 손절과 신규 인버스 추격을 모두 동결합니다.
5. 바닥 뒤에는 5일선·20일선·60일선 회복을 확인하며 세 번에 나눠 매수합니다.
6. 보유주식 매도는 시장 하락만으로 결정하지 않습니다.
7. 펀더멘탈 약화와 60일선 이탈이 함께 확인될 때만 10~25% 부분 축소합니다.
8. 상승장 과열과 횡보장 상단에서는 전량매도가 아니라 10%만 원래 비중으로 되돌립니다.
9. 모든 신호는 종가로 확인하고 실제 주문은 다음 거래일에 분할합니다.
10. 계좌 비중은 한 번에 총자산 5%p 이상 바꾸지 않습니다.
11. 백테스트 결과는 미래 승률이 아니라, 규칙을 계속 쓸 자격이 있는지 확인하는 자료로만 사용합니다.
            """
        )
        st.caption(
            "공매도 비율과 Beta는 종목 위험을 설명하는 보조지표일 뿐, 단독 매도 신호로 사용하지 않습니다."
        )




# --- Custom Portfolio Advice ---
with tab_port:
    st.divider()
    st.subheader("🤖 AI 참모의 맞춤형 코어 전략 가이드")
    
    try:
        from portfolio_manager import parse_portfolio_log
        holdings = parse_portfolio_log()
        us_holdings = holdings.get('us', [])
        
        from ai_reporter import get_custom_portfolio_advice
        if "calculate_us_orion_score" in globals():
            total_score, us_phase, _, _, _ = calculate_us_orion_score(macro_charts)
        else:
            us_phase = "CAUTION"
            total_score = 50.0
            
        advice = get_custom_portfolio_advice(us_holdings, us_phase, total_score)
        
        st.markdown(f"<div style='background:#f1f8ff; padding:20px; border-radius:10px; border-left:5px solid #0366d6;'>{advice}</div>", unsafe_allow_html=True)
    except Exception as e:
        st.error(f"맞춤형 가이드 로딩 중 오류 발생: {e}")


with tab_calendar:
    st.subheader("📅 마켓 캘린더 (실적 · 거시 · 연준)")
    st.caption("발표일 자체보다, 발표 직후 금리·시장 폭·ORION 진입 판단이 어떻게 바뀌는지를 함께 봅니다.")
    st.info("**읽는 순서:** 물가·금리 → 경기·고용 → 연준 → 실적/반도체. High 이벤트 전후에는 갭 상승 추격보다 실제 수치와 10년물 금리 반응을 먼저 확인하세요.")

    col_c1, col_c2, col_c3 = st.columns([1, 1, 1])
    with col_c1:
        if st.button("🔄 자동 실적 업데이트 (yfinance)"):
            with st.spinner("빅테크 실적발표일을 업데이트 중입니다..."):
                if calendar_manager.update_earnings_automatically():
                    st.success("실적 캘린더가 업데이트 되었습니다.")
                else:
                    st.warning("업데이트할 새로운 실적 일정이 없습니다.")
    with col_c2:
        if st.button("📌 확정 핵심 거시 일정 반영"):
            event_count = calendar_manager.sync_core_macro_events()
            st.success(f"공식 발표일 기준 핵심 거시·연준 일정 {event_count}건을 반영했습니다.")
            st.rerun()
    with col_c3:
        if st.button("🔄 뉴스 기반 매크로 업데이트"):
            with st.spinner("뉴스 기반 매크로(FOMC, 금통위 등) 스크래핑 중..."):
                if calendar_manager.update_macro_events_automatically():
                    st.success("매크로 일정이 업데이트 되었습니다.")
                else:
                    st.warning("추출된 새로운 매크로 일정이 없습니다.")
                    
    cal_df = calendar_manager.load_calendar()

    if not cal_df.empty:
        today_calendar = pd.Timestamp.now().date()
        upcoming_calendar = cal_df[cal_df["Date"] >= today_calendar].sort_values("Date")
        if not upcoming_calendar.empty:
            next_event = upcoming_calendar.iloc[0]
            high_count = int((upcoming_calendar["Impact"] == "High").sum())
            st.markdown(
                f"**다음 주요 일정:** {next_event['Date'].strftime('%m/%d')} · {next_event['Event']}  "
                f"&nbsp;&nbsp;|&nbsp;&nbsp; 향후 High 중요도 일정 **{high_count}건**"
            )
        with st.expander("🧭 ORION 캘린더 해석 가이드", expanded=False):
            st.markdown("""
            - **물가·금리:** CPI·PPI·PCE가 예상보다 높으면 장기금리 상승과 기술주 할인율 부담을 우선 점검합니다.
            - **경기·고용:** 소매판매·고용은 경기 지속성을 봅니다. 물가 상승과 경기 둔화가 함께 나오면 가장 보수적으로 대응합니다.
            - **연준:** FOMC·의사록·잭슨홀은 정책 경로를 바꿀 수 있습니다. 발표 전에는 비중 확대보다 기존 신호의 유지 여부를 확인합니다.
            - **실적·반도체:** 좋은 실적도 금리 급등 국면에서는 주가 반응이 제한될 수 있으므로, SOXX·RSP/SPY와 함께 해석합니다.
            """)
    
    # st.data_editor returns modified dataframe
    edited_df = st.data_editor(
        cal_df,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "Date": st.column_config.DateColumn("날짜", required=True, format="YYYY-MM-DD"),
            "Type": st.column_config.SelectboxColumn("구분", options=["실적", "물가·금리", "경기·고용", "연준", "국내", "반도체", "기타"], required=True),
            "Impact": st.column_config.SelectboxColumn("중요도", options=["High", "Medium", "Low"], required=True)
        }
    )
    
    if st.button("💾 캘린더 변경사항 저장"):
        for i, row in edited_df.iterrows():
            if hasattr(row['Date'], 'strftime'):
                edited_df.at[i, 'Date'] = row['Date'].strftime('%Y-%m-%d')
        calendar_manager.save_calendar(edited_df)
        st.success("캘린더가 저장되었습니다. 마스터 리포트 프롬프트에 즉시 반영됩니다.")

    st.markdown("---")
    st.subheader("🧮 바닥 일괄매수 · 혼합형 · 추세확인 비교")
    st.caption(
        "모든 시장 경로의 최종 가격을 동일하게 고정해 매수 시점만 비교합니다. "
        "표의 수익률과 최대손실은 개별 종목이 아니라 총자산 기준 %p입니다."
    )

    scenario_col1, scenario_col2, scenario_col3, scenario_col4 = st.columns(4)
    scenario_current = scenario_col1.number_input(
        "현재 가격 (정규화)", min_value=1.0, value=100.0, step=1.0,
        key="entry_scenario_current",
    )
    scenario_terminal = scenario_col2.number_input(
        "동일한 최종 가격", min_value=1.0, value=130.0, step=5.0,
        key="entry_scenario_terminal",
    )
    scenario_allocation = scenario_col3.number_input(
        "목표 투자비중 (%)", min_value=5.0, max_value=100.0,
        value=50.0, step=5.0, key="entry_scenario_allocation",
    )
    scenario_confirmation = scenario_col4.number_input(
        "저점 대비 추세확인 반등률 (%)", min_value=0.0, max_value=100.0,
        value=20.0, step=5.0, key="entry_scenario_confirmation",
    )

    low_col1, low_col2, low_col3 = st.columns(3)
    scenario_low_1 = low_col1.number_input(
        "시나리오 1 저점", min_value=1.0, value=100.0, step=5.0,
        key="entry_scenario_low_1",
    )
    scenario_low_2 = low_col2.number_input(
        "시나리오 2 저점", min_value=1.0, value=85.0, step=5.0,
        key="entry_scenario_low_2",
    )
    scenario_low_3 = low_col3.number_input(
        "시나리오 3 저점", min_value=1.0, value=70.0, step=5.0,
        key="entry_scenario_low_3",
    )

    try:
        scenario_table = calculate_entry_strategy_scenarios(
            current_price=scenario_current,
            terminal_price=scenario_terminal,
            target_allocation_pct=scenario_allocation,
            confirmation_rebound_pct=scenario_confirmation,
            scenario_lows=(scenario_low_1, scenario_low_2, scenario_low_3),
            hybrid_tranche_pct=min(10.0, scenario_allocation / 3),
            hybrid_entry_prices=(
                scenario_current,
                scenario_current * 0.90,
                scenario_current * 0.80,
            ),
        )
        display_scenario_table = scenario_table.copy()
        numeric_columns = [
            column
            for column in display_scenario_table.columns
            if column != "시장 경로"
        ]
        display_scenario_table[numeric_columns] = display_scenario_table[numeric_columns].round(1)
        st.dataframe(
            display_scenario_table,
            use_container_width=True,
            hide_index=True,
            column_config={
                "가정 저점": st.column_config.NumberColumn(format="%.1f"),
                "추세 확인 가격": st.column_config.NumberColumn(format="%.1f"),
                "일괄투자 수익률": st.column_config.NumberColumn(format="%+.1f%%p"),
                "혼합형 수익률": st.column_config.NumberColumn(format="%+.1f%%p"),
                "추세확인 수익률": st.column_config.NumberColumn(format="%+.1f%%p"),
                "일괄투자 최대손실": st.column_config.NumberColumn(format="%+.1f%%p"),
                "혼합형 최대손실": st.column_config.NumberColumn(format="%+.1f%%p"),
            },
        )
        st.info(
            "ORION 본체는 20일선과 수급을 기다리는 추세확인형입니다. "
            "혼합형은 본체 신호를 바꾸지 않고 별도 가치축적 예산만 소액으로 집행합니다."
        )
    except ValueError as exc:
        st.warning(str(exc))

    st.markdown("---")
    st.subheader("🧭 미국 투자 루틴: 시간 분할 + 추세 눌림목")
    st.caption(
        "ORION 신호는 이번 주문 금액이 아니라 최대 누적 진입 단계를 뜻합니다. "
        "아래 표는 미국 투자 예정금 2,000만 원을 예시로 든 운영 원칙이며, 실제 금액은 본인의 자산·환율 노출에 맞춰 조정합니다."
    )

    us_routine_table = pd.DataFrame(
        [
            {"단계": "1", "조건": "STARTER_GO_5", "누적 투자액": "5% = 100만 원", "이번 주문": "100만 원"},
            {"단계": "2", "조건": "이후 STARTER_GO_10", "누적 투자액": "10% = 200만 원", "이번 주문": "이미 5%면 추가 100만 원"},
            {"단계": "3", "조건": "추세 유지 + 20일선 눌림 후 재안착", "누적 투자액": "20% = 400만 원", "이번 주문": "추가 200만 원"},
            {"단계": "4", "조건": "다음 분할 조건 충족", "누적 투자액": "30~40%", "이번 주문": "사전에 정한 금액만 추가"},
        ]
    )
    st.dataframe(us_routine_table, use_container_width=True, hide_index=True)
    st.info(
        "**누적 원칙:** 10% 신호가 나와도 10%를 새로 매수하는 것이 아닙니다. "
        "이미 5%를 투자했다면 누적 10%가 되도록 5%만 추가합니다."
    )

    with st.expander("📌 강한 장에서의 실행 원칙", expanded=False):
        st.markdown("""
        - **코어 시간 분할:** ORION에 하드 거부가 없을 때, 정한 날짜에 작은 금액을 꾸준히 분할합니다.
        - **전술 추가:** SPY가 상승 중인 20일선 부근까지 눌렸다가 종가 기준으로 다시 안착하면 누적 비중을 한 단계 올립니다.
        - **추격 금지:** 전일 대비 갭 상승이 3%를 초과하거나 20일선에서 지나치게 멀어진 날에는 신규 매수를 기다립니다.
        - **경고 시 대응:** 20일선을 하루 이탈했다고 기존 보유분을 자동 매도하지 않습니다. 신규 매수만 멈추고, 낙하 칼날·신용 스트레스가 확인될 때만 방어 단계를 검토합니다.
        - **종목별 비중:** 코어 ETF 또는 질 좋은 핵심주는 먼저 사용하고, 반도체·AI 고변동 종목은 더 작은 분할로 접근합니다.
        """)


with tab_hedging:
    st.subheader("🧭 시장 국면별 자산 운용판")
    st.caption("인버스 추천 화면이 아닙니다. 현재 국면에 맞춰 주식·현금·보유종목을 어떻게 운용할지 먼저 보여드립니다.")

    defensive_action_panel = st.container()
    defensive_performance_panel = st.container()

    st.markdown("### 3. 내 계좌 금액")
    account_col1, account_col2 = st.columns(2)
    total_asset = account_col1.number_input(
        "총 투자자산 (만원)",
        min_value=0,
        step=100,
        key="account_total_assets",
    )
    equity_amount = account_col2.number_input(
        "그중 국내 주식 금액 (만원)",
        min_value=0,
        step=100,
        key="account_kr_equity",
    )
    equity_weight_pct = (
        min(float(equity_amount) / float(total_asset) * 100, 100)
        if total_asset > 0
        else 0.0
    )
    if equity_amount > total_asset and total_asset > 0:
        st.warning("국내 주식 금액이 총 투자자산보다 큽니다. 계산에서는 총 투자자산까지만 반영합니다.")

    st.markdown("---")
    st.markdown("### 선택 기능 · 인버스 단기전략")
    st.caption(
        "아래는 기본 운용안과 분리된 보조 기능입니다. 새 인버스는 별도 백테스트가 통과한 경우에만 검토하며, "
        "2배 상품은 최대 3거래일로 제한합니다."
    )
    horizon_col, position_col, days_col, holding_amount_col = st.columns(4)
    horizon_labels = {
        "tactical": "오늘~3일만 방어",
        "short": "약 1~2주 방어",
        "defensive": "약 1~3개월 위험 줄이기",
    }
    horizon_key = horizon_col.selectbox(
        "얼마나 방어할까요?",
        options=list(HEDGE_HORIZONS.keys()),
        format_func=lambda key: horizon_labels[key],
        help="2배 인버스는 하루 수익률을 -2배로 따라가므로 오늘~3일 구간에서만 검토합니다.",
    )
    position_labels = {
        "none": "아니요, 없습니다",
        "inverse1x": "네, 1배 인버스",
        "inverse2x": "네, 2배 인버스",
    }
    position_status = position_col.selectbox(
        "지금 인버스가 있나요?",
        options=list(position_labels.keys()),
        format_func=lambda key: position_labels[key],
    )
    holding_days = days_col.number_input(
        "며칠째 보유 중인가요?",
        min_value=0,
        max_value=120,
        value=0,
        step=1,
        disabled=position_status == "none",
    )
    current_hedge_amount = holding_amount_col.number_input(
        "현재 보유금액 (만원)",
        min_value=0,
        value=0,
        step=50,
        disabled=position_status == "none",
    )

    st.markdown("#### 인버스 보유자용 추가 확인")
    quick_action_panel = st.container()
    simple_performance_panel = st.container()

    hedge_policy = HEDGE_HORIZONS[horizon_key]
    vkospi_source = macro_charts.get("vkospi_source", "없음")
    hedge_data_quality = (
        "unavailable"
        if vkospi_10y.empty
        else "proxy"
        if "프록시" in vkospi_source
        else "live"
    )

    default_coverage = {"tactical": 20, "short": 25, "defensive": 30}[horizon_key]
    with st.expander("선택 입력 · 잘 모르겠으면 기본값 그대로 두세요"):
        advanced_col1, advanced_col2, advanced_col3 = st.columns(3)
        portfolio_beta = advanced_col1.number_input(
            "시장 민감도",
            value=1.0,
            min_value=0.0,
            max_value=3.0,
            step=0.1,
            help="잘 모르겠으면 1.0을 사용하세요. 1.0은 KOSPI200과 비슷하게 움직인다는 뜻입니다.",
        )
        target_coverage_pct = advanced_col2.number_input(
            "줄이고 싶은 하락 위험 (%)",
            value=default_coverage,
            min_value=0,
            max_value=100,
            step=5,
        )
        transaction_cost_bps = advanced_col3.number_input(
            "왕복 비용 가정 (0.01% 단위)",
            value=30.0,
            min_value=0.0,
            max_value=200.0,
            step=10.0,
            help="기본 30은 매수 0.15% + 매도 0.15%를 뜻합니다.",
        ) / 2

        st.session_state["hedging_futures"] = st.session_state["foreign_futures"]
        foreign_futures_hedging = st.number_input(
            "오늘 외국인 선물 순매수 계약",
            step=100,
            key="hedging_futures",
            on_change=sync_futures_hedging,
            help="모르면 0을 그대로 두고 아래 확인란을 체크하지 마세요.",
        )
        futures_confirmed = st.checkbox(
            "이 숫자가 오늘 최신값임을 직접 확인했습니다",
            value=False,
        )

    with st.expander("선택한 방어 방식의 기준 보기"):
        st.markdown(
            f"- 사용 수단: **{hedge_policy.product}**\n"
            f"- 기본 최대 보유: **{hedge_policy.max_days}거래일**\n"
            f"- 최대 투입 한도: **총자산의 {hedge_policy.max_allocation * 100:.0f}%**\n"
            f"- 변동성 데이터: `{vkospi_source}`"
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
    spread_adf = {
        "spread_adf_pvalue": None,
        "is_cointegrated": False,
        "status": "unavailable",
        "hedge_ratio": None,
        "residual_z": None,
        "observations": 0,
        "error": "검정 전",
    }
    
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
            spread_adf = get_daily_spread_adf(kospi200_df, kosdaq_df)
            if spread_adf.get("status") == "ok":
                hedge_ratio = spread_adf.get("hedge_ratio", 1.0)
                combined["Residual"] = (
                    np.log(combined["KOSPI200"])
                    - hedge_ratio * np.log(combined["KOSDAQ"])
                )
                residual_mean = combined["Residual"].rolling(60).mean()
                residual_std = combined["Residual"].rolling(60).std().replace(0, np.nan)
                combined["Residual_Z"] = (
                    combined["Residual"] - residual_mean
                ) / residual_std
                curr_z = spread_adf.get("residual_z", curr_z)

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

    # ════════════════════════════════════════════
    # 🟡 변동성 레짐 정밀 분류기 v2.0 (Strategy B)
    # ════════════════════════════════════════════
    vol_regime = "⚪ 판별 불가"
    vol_color  = "#6c757d"
    vol_action = ""
    vol_details = []

    if has_tech and not vkospi_10y.empty:
        daily_rets = kospi_10y['Close'].pct_change().dropna()
        hv20 = float(daily_rets.tail(20).std() * (252**0.5) * 100)
        hv_series = daily_rets.rolling(20).std() * (252**0.5) * 100
        hv_pct = float((hv_series.dropna() <= hv20).mean())

        vk = vkospi_10y['Close']
        vk_ma5  = float(vk.rolling(5).mean().iloc[-1])
        vk_ma20 = float(vk.rolling(20).mean().iloc[-1])
        vk_momentum_falling = vk_ma5 < vk_ma20

        net_20d = float((kospi_10y['Close'].iloc[-1] / kospi_10y['Close'].iloc[-21] - 1) * 100)
        directional_ratio = abs(net_20d) / hv20 if hv20 > 0 else 0

        if hv_pct >= 0.90 and not vk_momentum_falling:
            vol_regime = "🔴 패닉 변동성 (Panic Volatility)"
            vol_color  = "#dc3545"
            vol_action = "신규 곱버스 추격 금지. 기존 헷지 축소 조건과 현금 방어를 점검합니다."
            vol_details = [
                f"실현변동성(HV20): {hv20:.1f}% — 역사적 상위 {(1-hv_pct)*100:.0f}%",
                f"VKOSPI 모멘텀: 5일 평균 {vk_ma5:.1f} > 20일 평균 {vk_ma20:.1f} — 공포 확장 중",
                "👉 이 값은 선물 만기구조(콘탱고/백워데이션)가 아니며, 단순 모멘텀으로만 해석합니다."
            ]
        elif hv_pct >= 0.75 and curr_atr_ratio >= 1.3:
            vol_regime = "🟠 추세 변동성 (Trending — 칼날 구간)"
            vol_color  = "#fd7e14"
            vol_action = "현금을 유지하고 주식 비중은 주간 한도 안에서만 조정합니다. 신규 레버리지는 금지합니다."
            vol_details = [
                f"실현변동성(HV20): {hv20:.1f}% — 확장 국면 (역사적 {hv_pct*100:.0f}% 백분위)",
                f"ATR 비율: {curr_atr_ratio:.2f}x — 강한 방향성 동반",
                f"방향성 비율(|순변화|/HV20): {directional_ratio:.2f} — 추세 확인"
            ]
        elif hv_pct >= 0.60 and directional_ratio < 0.3:
            vol_regime = "🌊 휩쏘 변동성 (Whipsaw — 오르락내리락)"
            vol_color  = "#6f42c1"
            vol_action = "신규 방향성 레버리지 금지. 현금 비중과 베타 노출만 재조정합니다."
            vol_details = [
                f"실현변동성(HV20): {hv20:.1f}% — 높음 (상위 {(1-hv_pct)*100:.0f}%)",
                f"방향성 비율: {directional_ratio:.2f} — 0.3 미만 (방향 없는 노이즈)",
                "👉 옵션·델타 데이터가 없으므로 Gamma Scalping 또는 시장중립이라고 표기하지 않습니다."
            ]
        elif hv_pct >= 0.75:
            vol_regime = "🟡 고변동성 반등/감속 (High-Vol Reversal)"
            vol_color  = "#e0a800"
            vol_action = "신규 레버리지 추격은 금지합니다. 기존 헷지는 과매도·수급 반전을 확인하며 분할 축소하고 현금을 유지합니다."
            vol_details = [
                f"실현변동성(HV20): {hv20:.1f}% — 역사적 {hv_pct*100:.0f}% 백분위",
                f"VKOSPI 모멘텀: 5일 평균 {vk_ma5:.1f} < 20일 평균 {vk_ma20:.1f} — 공포 모멘텀 감속",
                f"방향성 비율: {directional_ratio:.2f} — 고변동성은 남아 있어 정상 회복으로 보지 않음",
            ]
        elif hv_pct <= 0.30 and vk_momentum_falling:
            vol_regime = "😴 과도한 평온 (Quiet — 폭발 직전 주의)"
            vol_color  = "#17a2b8"
            vol_action = "변동성 압축 관찰. 방향 확인 전 레버리지 상품 진입은 보류합니다."
            vol_details = [
                f"실현변동성(HV20): {hv20:.1f}% — 역사적 하위 {hv_pct*100:.0f}% (극단 저변동성)",
                f"VKOSPI 모멘텀: 5일 평균 {vk_ma5:.1f} < 20일 평균 {vk_ma20:.1f}",
                "👉 낮은 변동성이 향후 폭발을 보장하지는 않습니다. 추세 확인 후 대응합니다."
            ]
        else:
            vol_regime = "🟢 정상 회복 변동성 (Normal Recovery)"
            vol_color  = "#28a745"
            vol_action = "인버스는 정리하고, 회복 단계에 맞춰 현금을 분할 투입합니다."
            vol_details = [
                f"실현변동성(HV20): {hv20:.1f}% — 정상 범위 ({hv_pct*100:.0f}% 백분위)",
                f"방향성 비율: {directional_ratio:.2f} — 안정적 회복 추세",
                "👉 ORION Signal 탭의 Tier 시스템에 따라 분할 매수 재개."
            ]

    # 🚨 인버스 매수 추천 스코어링
    inv_score = 0
    inv_details = []

    internals = get_intraday_market_internals()
    prog_net = internals.get("program_net")
    adr = internals.get("adr")

    if adr is not None and adr <= 0.4:
        inv_score += 20
        inv_details.append(f"시장 Breadth (ADR) {adr:.2f}로 극심한 패닉 (+20점)")
    elif adr is not None and adr <= 0.7:
        inv_score += 10
        inv_details.append(f"시장 Breadth (ADR) {adr:.2f}로 하락 종목 우위 (+10점)")
    else:
        inv_details.append("시장 Breadth 데이터 없음/중립 (점수 제외)")

    if prog_net is not None and prog_net <= -300000:
        inv_score += 20
        inv_details.append(f"프로그램 3,000억 이상 대규모 순매도 출회 (+20점)")
    else:
        inv_details.append("프로그램 순매매 데이터 미구현 (점수 제외)")
    
    f_fut = locals().get('foreign_futures', 0)
    f_fut_signal = f_fut if futures_confirmed else None
    if f_fut_signal is not None and f_fut_signal <= -5000:
        inv_score += 30
        inv_details.append("외국인 선물 5천계약 이상 초대량 순매도 (+30점)")
    elif f_fut_signal is not None and f_fut_signal <= -2000:
        inv_score += 15
        inv_details.append("외국인 선물 2천계약 이상 순매도 중 (+15점)")
    elif f_fut_signal is None:
        inv_details.append("외국인 선물 수급 미확인 (점수 제외)")
    else:
        inv_details.append("외국인 선물 매도 압력 낮음 (0점)")
        
    if 'vkospi_10y' in locals() and not vkospi_10y.empty:
        v_tail = vkospi_10y['Close'].tail(250)
        curr_vk = v_tail.iloc[-1]
        pct_rank = (v_tail <= curr_vk).mean()
        if pct_rank >= 0.95:
            inv_score += 30
            inv_details.append(f"VKOSPI 최근 1년 내 상위 5% 돌파 (+30점)")
        elif pct_rank >= 0.85:
            inv_score += 15
            inv_details.append(f"VKOSPI 최근 1년 내 상위 15% 진입 (+15점)")
            
    k_val = locals().get('current_kospi_val', 0)
    k_5ma = locals().get('kospi_5d_sma', 0)
    if isinstance(k_val, (int, float)) and isinstance(k_5ma, (int, float)) and k_val < k_5ma:
        inv_score += 20
        inv_details.append("KOSPI 지수 5일 이평선 하회 (+20점)")
        
    if 'usd_krw' in locals() and not usd_krw.empty:
        usd_tail = usd_krw['Close'].tail(100)
        usd_ma60 = usd_tail.rolling(60).mean().iloc[-1]
        usd_std60 = usd_tail.rolling(60).std().iloc[-1]
        curr_ex = usd_tail.iloc[-1]
        usd_z = (curr_ex - usd_ma60) / usd_std60 if usd_std60 > 0 else 0
        if usd_z >= 2.0:
            inv_score += 20
            inv_details.append(f"원/달러 환율 60일 평균 대비 +2σ 폭등 (Z: {usd_z:+.2f}) (+20점)")
        elif usd_z >= 1.0:
            inv_score += 10
            inv_details.append(f"원/달러 환율 60일 평균 대비 상승 (Z: {usd_z:+.2f}) (+10점)")

    if has_tech and curr_rsi > 40:
        if inv_score >= 70:
            inv_score = 69
        inv_details.append(f"⚠️ KOSPI RSI({curr_rsi:.1f})가 40 이상이므로 점수 상한(69점) 제한")

    inv_score = min(inv_score, 100)

    # ════════════════════════════════════════════
    # 🔴 인버스 동적 EXIT 알고리즘 (Strategy A)
    # ════════════════════════════════════════════
    exit_score = 0
    exit_details = []
    exit_signals = []

    if has_tech:
        if curr_rsi < 25:
            exit_score += 40
            exit_details.append(f"🚨 KOSPI RSI {curr_rsi:.1f} — 극단적 과매도. 인버스 익절 후 현금 전환 강력 권고 (+40)")
            exit_signals.append("🟢 RSI 과매도 임계 돌파")
        elif curr_rsi < 32:
            exit_score += 20
            exit_details.append(f"⚠️ KOSPI RSI {curr_rsi:.1f} — 과매도 구간 진입. 인버스 분할 익절 시작 (+20)")

    if f_fut_signal is not None and f_fut_signal >= 0:
        exit_score += 25
        exit_details.append(f"외국인 선물 순매도 해소 → 하방 압력 소멸. 인버스 청산 신호 (+25)")
        exit_signals.append("🟢 외인 선물 전환")
    elif f_fut_signal is not None and f_fut_signal >= -500:
        exit_score += 10
        exit_details.append(f"외국인 선물 매도 규모 급감 ({f_fut}계약) (+10)")
    elif f_fut_signal is None:
        exit_details.append("외국인 선물 수급 미확인 (청산 점수 제외)")

    if not vkospi_10y.empty:
        v_tail = vkospi_10y['Close'].tail(250)
        curr_vk = v_tail.iloc[-1]
        vk_5d_high = v_tail.tail(5).max()
        if curr_vk < vk_5d_high * 0.92:
            exit_score += 25
            exit_details.append(f"VKOSPI 5일 고점({vk_5d_high:.1f}) 대비 {curr_vk:.1f}로 공포 피크아웃. 인버스 청산 신호 (+25)")
            exit_signals.append("🟢 VKOSPI 피크아웃")

    if 'usd_krw' in locals() and not usd_krw.empty:
        ex_tail = usd_krw['Close'].dropna().tail(10)
        if len(ex_tail) >= 5:
            ex_5d_slope = (float(ex_tail.iloc[-1]) - float(ex_tail.iloc[-5])) / float(ex_tail.iloc[-5]) * 100
            if ex_5d_slope < -0.5:
                exit_score += 10
                exit_details.append(f"원/달러 환율 5일 하락 전환 ({ex_5d_slope:+.2f}%) — 외인 위험회피 완화 (+10)")

    us_score = locals().get('us_score', 0)
    if us_score >= 70:
        exit_score += 15
        exit_details.append(f"미국 진바닥 확률 {us_score}% — 글로벌 동반 반등 가능성. 곱버스 청산 고려 (+15)")

    exit_score = min(exit_score, 100)

    # 라이브 점수와 백테스트 점수를 같은 공식으로 맞춘다.
    # 수동 입력 수급은 점수 최적화에 섞지 않고, 안전 차단 조건으로만 사용한다.
    historical_signal_features = build_daily_hedge_features(
        kospi_10y,
        vkospi_10y,
        usd_krw,
    )
    if not historical_signal_features.empty:
        latest_signal = historical_signal_features.iloc[-1]
        inv_score = int(round(float(latest_signal["EntryScore"])))
        exit_score = int(round(float(latest_signal["ExitScore"])))
        curr_rsi = float(latest_signal["RSI"])
        inv_details = [
            f"최근 5일 KOSPI 변화: {latest_signal['RET5']:+.1f}%",
            f"KOSPI가 5일 평균보다 {'낮음' if latest_signal['KOSPI'] < latest_signal['MA5'] else '높음'}",
            f"최근 1년 변동성 위치: 상위 {(1-latest_signal['VK_RANK252'])*100:.0f}%",
            f"원/달러 위험 수준: {latest_signal['USDKRW_Z60']:+.1f}",
        ]
        exit_details = [
            f"KOSPI 과매도 정도(RSI): {curr_rsi:.1f}",
            f"공포지수 5일 고점 대비 변화: {(latest_signal['VKOSPI'] / latest_signal['VK_5D_HIGH'] - 1) * 100:+.1f}%",
            f"원/달러 최근 5일 변화: {latest_signal['USDKRW_RET5']:+.1f}%",
        ]

    inverse1x_10y = macro_charts.get("inverse1x_10y", pd.DataFrame())
    inverse2x_10y = macro_charts.get("inverse2x_10y", pd.DataFrame())
    hedge_optimization = get_hedge_optimization(
        kospi_10y,
        vkospi_10y,
        usd_krw,
        inverse1x_10y,
        inverse2x_10y,
        horizon_key,
        transaction_cost_bps,
    )
    optimized_parameters = hedge_optimization.get("best_parameters", {})
    optimized_entry_threshold = float(
        optimized_parameters.get("entry_threshold", hedge_policy.entry_threshold)
    )
    optimized_exit_threshold = float(
        optimized_parameters.get("exit_threshold", 35)
    )
    optimized_max_days = int(
        optimized_parameters.get("max_holding_days", hedge_policy.max_days)
    )
    validation_passed = bool(
        hedge_optimization.get("status") == "ok"
        and hedge_optimization.get("passed", False)
    )
    inverse_validation = build_inverse_validation_summary(hedge_optimization)

    optimized_full_exit_threshold = min(optimized_exit_threshold + 25, 70)
    if exit_score >= optimized_full_exit_threshold:
        exit_verdict = "🚨 인버스 즉시 청산 (익절) 강력 권고"
        exit_color = "#28a745"
    elif exit_score >= optimized_exit_threshold:
        exit_verdict = "⚠️ 인버스 분할 익절 시작 (50% 청산 후 대기)"
        exit_color = "#ffc107"
    else:
        exit_verdict = "⚫ 인버스 홀딩 유지 (청산 조건 미충족)"
        exit_color = "#6c757d"

    hedge_decision = evaluate_hedge_state(
        horizon_key=horizon_key,
        position_status=position_status,
        entry_score=inv_score,
        exit_score=exit_score,
        rsi=curr_rsi if has_tech else None,
        foreign_futures=f_fut_signal,
        holding_days=int(holding_days),
        data_quality=hedge_data_quality,
        entry_threshold=optimized_entry_threshold,
        exit_threshold=optimized_exit_threshold,
        max_holding_days=optimized_max_days,
        validation_passed=validation_passed,
    )

    hedge_size = calculate_beta_hedge_size(
        total_assets=total_asset,
        equity_weight=equity_weight_pct / 100,
        portfolio_beta=portfolio_beta,
        target_coverage=target_coverage_pct / 100,
        horizon_key=horizon_key,
    )
    plain_action = build_plain_action_plan(
        decision=hedge_decision,
        position_status=position_status,
        holding_amount=current_hedge_amount,
        recommended_allocation=hedge_size["recommended_allocation"],
        policy_cap=hedge_size["policy_cap"],
        entry_score=inv_score,
        entry_threshold=optimized_entry_threshold,
        exit_score=exit_score,
        exit_threshold=optimized_exit_threshold,
    )

    defensive_optimization = get_defensive_optimization(
        kospi_10y,
        transaction_cost_bps,
    )
    defensive_parameters = defensive_optimization.get(
        "best_parameters",
        {
            "target_volatility": 0.12,
            "trend_days": 200,
            "defensive_cap": 0.55,
            "rebalance_days": 5,
            "minimum_equity": 0.20,
            "max_rebalance_step": 0.10,
        },
    )
    defensive_state = current_defensive_state(
        kospi_10y,
        defensive_parameters,
    )
    defensive_validation_passed = bool(
        defensive_optimization.get("status") == "ok"
        and defensive_optimization.get("passed", False)
    )
    defensive_action = build_defensive_action_plan(
        total_assets=total_asset,
        current_equity_amount=equity_amount,
        state=defensive_state,
        validation_passed=defensive_validation_passed,
    )
    usd_diversifier = evaluate_usd_diversifier(kospi_10y, usd_krw)
    regime_action = build_regime_action_plan(
        total_assets=total_asset,
        current_equity_amount=equity_amount,
        regime=market_regime,
    )
    regime_backtest = get_regime_backtest(kospi_10y, transaction_cost_bps)
    regime_color = market_regime.get("color", "#475569")
    defensive_color = regime_color
    target_equity_value = defensive_action["target_equity_amount"]
    target_cash_value = defensive_action["target_cash_amount"]

    with defensive_action_panel:
        st.markdown("### 1. 지금 시장과 오늘 할 일")
        st.markdown(
            f"""
            <div style="background:#ffffff; border:2px solid {regime_color}; border-radius:14px;
                        padding:22px; margin:8px 0 14px 0;">
                <div style="font-size:0.95rem; color:#64748b; margin-bottom:6px;">
                    {market_regime.get('icon', '⚪')} 현재 국면 · {market_regime.get('label', '판별 중')}
                </div>
                <div style="font-size:1.55rem; line-height:1.35; font-weight:800; color:{regime_color};">
                    {regime_action['title']}
                </div>
                <div style="margin-top:12px; color:#334155;">
                    {regime_action['reason']}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        lower_band, upper_band = regime_action["equity_band"]
        safe_cols = st.columns(4)
        safe_cols[0].metric("현재 주식", f"{regime_action['current_equity_amount']:,.0f}만원")
        safe_cols[1].metric("현재 현금", f"{regime_action['current_cash_amount']:,.0f}만원")
        safe_cols[2].metric("주식 허용범위", f"{lower_band * 100:.0f}~{upper_band * 100:.0f}%")
        safe_cols[3].metric(
            "오늘 주문",
            "0원" if regime_action["amount"] <= 0 else f"{regime_action['amount']:,.0f}만원 {regime_action['side']}",
        )
        st.markdown(
            "\n".join(
                f"{idx}. {step}"
                for idx, step in enumerate(regime_action["steps"], start=1)
            )
        )
        if market_regime.get("status") == "ok":
            indicators = market_regime.get("indicators", {})
            st.caption(
                f"종가 기준 {market_regime['as_of']} · 국면 신뢰도 {market_regime['confidence']}% · "
                f"RSI {indicators.get('rsi', 0):.1f} · "
                f"20일 실현변동성 {indicators.get('realized_volatility', 0) * 100:.1f}% · "
                f"다음 판단 {regime_action['next_check']}"
            )
        st.info(
            "이 범위는 오늘 당장 맞춰야 할 목표가 아닙니다. 특히 패닉 안전장치가 켜진 날은 "
            "범위를 벗어나도 매도하지 않고, 패닉 해제 후 최대 5%p씩만 조정합니다. "
            "인버스는 아래 선택 기능에서만 별도로 다룹니다."
        )

    with defensive_performance_panel:
        st.markdown("### 2. 국면이 바뀌면 수익을 내는 방법도 바뀝니다")
        regime_rows = []
        for code in ("CRASH", "BOTTOM_RECOVERY", "UPTREND", "SIDEWAYS"):
            policy = REGIME_POLICIES[code]
            lower, upper = policy["equity_band"]
            regime_rows.append(
                {
                    "시장 국면": f"{policy['icon']} {policy['label']}",
                    "주식 범위": f"{lower * 100:.0f}~{upper * 100:.0f}%",
                    "수익을 노리는 방법": policy["earning_method"],
                    "실행 원칙": policy["core_strategy"],
                    "하지 않는 것": policy["avoid"],
                }
            )
        st.dataframe(pd.DataFrame(regime_rows), width="stretch", hide_index=True)
        st.caption(
            "기본 전략은 주식·현금·저위험 단기자금만 사용합니다. "
            "옵션 매도, 변동성 ETN, 레버리지, 공매도, 마켓뉴트럴은 기본 화면에서 제외했습니다."
        )

        with st.expander("과거 데이터에서 이 고정 규칙을 확인한 결과"):
            if regime_backtest.get("status") == "ok":
                metrics = regime_backtest["holdout_metrics"]
                validation_cols = st.columns(4)
                validation_cols[0].metric(
                    "최근 구간 전략수익",
                    f"{metrics['strategy_total_return']:+.1f}%",
                    delta=f"KOSPI {metrics['benchmark_total_return']:+.1f}%",
                )
                validation_cols[1].metric(
                    "전략 최대낙폭",
                    f"{metrics['strategy_mdd']:.1f}%",
                    delta=f"KOSPI {metrics['benchmark_mdd']:.1f}%",
                )
                validation_cols[2].metric(
                    "전략 변동성",
                    f"{metrics['strategy_volatility']:.1f}%",
                    delta=f"KOSPI {metrics['benchmark_volatility']:.1f}%",
                )
                validation_cols[3].metric(
                    "하락일 민감도",
                    f"{metrics['downside_capture']:.0f}%",
                    help="KOSPI 하락일 손실을 몇 % 따라갔는지 보여줍니다. 낮을수록 방어적입니다.",
                )
                st.caption(
                    f"{regime_backtest['holdout_start']} 이후 최근 30% 구간입니다. "
                    "국면별 40~90% 범위, 5거래일 확인, 회당 5%p 조정, 편도 비용을 적용했습니다. "
                    "수익률이 KOSPI보다 낮으면 방어로 줄인 손실보다 포기한 상승 수익이 컸다는 뜻입니다."
                )
                st.line_chart(regime_backtest["equity_curve"], height=300)
            else:
                st.warning(regime_backtest.get("message", "검증 데이터가 부족합니다."))

        with st.expander("전문가용 · 예전 20% 목표 모델은 왜 기본값에서 뺐나요?"):
            st.markdown(
                "예전 값은 `목표변동성 ÷ 현재변동성`으로 계산한 스트레스 모델의 이론적 목표였습니다. "
                "위험을 줄이는 데는 유용하지만, 장기 투자자에게 현금 80%를 즉시 요구하면 반등 수익을 크게 놓칠 수 있습니다. "
                "지금은 이 계산을 주문으로 쓰지 않고 참고 검증으로만 남깁니다."
            )
            if defensive_optimization.get("status") == "ok":
                old_metrics = defensive_optimization["holdout_metrics"]
                st.caption(
                    f"이전 모델 참고: 최근 수익 {old_metrics['strategy_total_return']:+.1f}% "
                    f"(KOSPI {old_metrics['benchmark_total_return']:+.1f}%), "
                    f"최대낙폭 {old_metrics['strategy_mdd']:.1f}%."
                )
            else:
                st.caption("이전 모델 검증 데이터가 부족합니다.")

    action_color = {
        "ENTER_PARTIAL": "#d97706",
        "REDUCE_BETA": "#d97706",
        "REDUCE": "#d97706",
        "BLOCK_VALIDATION": "#b91c1c",
        "BLOCK_DATA": "#b91c1c",
        "BLOCK_PROXY_2X": "#b91c1c",
        "EXIT": "#dc2626",
        "EXIT_TIME": "#dc2626",
        "EXIT_2X_HORIZON": "#dc2626",
        "HOLD": "#2563eb",
    }.get(hedge_decision.action, "#475569")
    with quick_action_panel:
        validation_color = (
            "#15803d" if inverse_validation["usable"] else "#b91c1c"
        )
        validation_background = (
            "#f0fdf4" if inverse_validation["usable"] else "#fef2f2"
        )
        st.markdown("#### 인버스 전략 사용 여부")
        st.markdown(
            f"""
            <div style="background:{validation_background}; border:2px solid {validation_color}; border-radius:14px;
                        padding:20px; margin:8px 0 16px 0;">
                <div style="font-size:0.9rem; color:#64748b; margin-bottom:5px;">백테스트 최종 판정</div>
                <div style="font-size:1.45rem; line-height:1.35; font-weight:800; color:{validation_color};">
                    {inverse_validation['headline']}
                </div>
                <div style="margin-top:10px; color:#334155;">
                    {inverse_validation['reason']}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if not inverse_validation["usable"]:
            st.info(
                f"현재 하락방어 {inv_score:.0f}점은 **시장이 많이 흔들리고 있다는 뜻**일 뿐입니다. "
                "**인버스 매수 확률이나 매수 허가가 아닙니다.**"
            )

        st.markdown("#### 그래서 오늘 할 일")
        st.markdown(
            f"""
            <div style="background:#ffffff; border:2px solid {action_color}; border-radius:14px;
                        padding:22px; margin:8px 0 14px 0;">
                <div style="font-size:0.9rem; color:#64748b; margin-bottom:6px;">오늘의 결론</div>
                <div style="font-size:1.55rem; line-height:1.35; font-weight:800; color:{action_color};">
                    {plain_action['title']}
                </div>
                <div style="margin-top:14px; font-size:1.05rem; color:#0f172a;">
                    <b>{plain_action['amount_label']}:</b> {plain_action['amount_value']}
                    &nbsp;·&nbsp; <b>다시 확인:</b> {plain_action['next_check']}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        action_cols = st.columns(3)
        action_cols[0].metric(
            plain_action["amount_label"],
            plain_action["amount_value"],
        )
        action_cols[1].metric(
            "사용 수단",
            "현금·주식 축소"
            if hedge_decision.action == "REDUCE_BETA"
            else "현금 유지"
            if position_status == "none" and not hedge_decision.allow_new_entry
            else hedge_decision.product.split(" (")[0],
        )
        if position_status == "none" and not hedge_decision.allow_new_entry:
            action_cols[2].metric("다시 확인", plain_action["next_check"])
        else:
            action_cols[2].metric(
                "최대 보유",
                f"{hedge_decision.max_holding_days}거래일",
            )
        st.markdown(
            "\n".join(
                f"{idx}. {step}"
                for idx, step in enumerate(plain_action["steps"], start=1)
            )
        )
        with st.expander("75점 같은 시장 점수는 무슨 뜻인가요?"):
            st.markdown(
                f"- **현재 하락방어 {inv_score:.0f}점:** 시장 하락·변동성·환율 위험의 강도\n"
                f"- **진입 참고선 {optimized_entry_threshold:.0f}점:** 검증을 통과한 전략에서만 확인하는 2차 조건\n"
                f"- **현재 줄이기 {exit_score:.0f}점:** 이미 인버스를 가진 사람의 축소·청산 참고값\n\n"
                "**판단 순서:** 백테스트 사용 가능 → 오늘 시장 조건 통과 → 분할 주문. "
                "첫 단계가 탈락하면 시장 점수가 높아도 주문은 0원입니다."
            )

    with simple_performance_panel:
        st.markdown("#### 왜 사용하거나 중지하나요?")
        if hedge_optimization.get("status") == "ok":
            holdout_metrics = hedge_optimization["holdout_metrics"]
            signal_count = int(holdout_metrics["trades"])
            reliability = (
                "보통"
                if signal_count >= 20
                else "낮음"
                if signal_count >= 10
                else "매우 낮음"
            )
            if inverse_validation["usable"]:
                st.success(
                    "✅ 사용 가능: 최근 별도 검증에서 평균수익·손익비·계좌 낙폭 개선을 모두 통과했습니다."
                )
            else:
                st.error(
                    f"⛔ 사용 중지: {inverse_validation['reason']} 오늘 신규 주문은 0원입니다."
                )

            performance_cols = st.columns(3)
            performance_cols[0].metric(
                "거래당 평균 결과",
                f"{holdout_metrics['avg_trade_return']:+.2f}%",
                help="비용을 반영한 한 번의 인버스 거래 평균입니다. 0% 이하면 전략을 사용하지 않습니다.",
            )
            performance_cols[1].metric(
                "수익으로 끝난 거래",
                f"{holdout_metrics['win_rate']:.1f}%",
                help="비용을 차감한 뒤 플러스였던 거래 비율입니다. 이것만으로 매수를 결정하지 않습니다.",
            )
            performance_cols[2].metric(
                "검증한 거래",
                f"{signal_count}회",
            )
            st.caption(f"표본 신뢰도: {reliability}")
            with st.expander("판정 기준과 나머지 숫자 보기"):
                for check in inverse_validation["checks"]:
                    icon = "✅" if check["passed"] else "❌"
                    st.markdown(
                        f"- {icon} **{check['label']} {check['value']}** — {check['rule']}"
                    )
                st.markdown(
                    f"- 가장 나빴던 한 번: **{holdout_metrics['worst_trade_return']:.2f}%**\n"
                    f"- 적용 기준: 하락방어 {optimized_entry_threshold:.0f}점 · "
                    f"줄이기 {optimized_exit_threshold:.0f}점 · 최대 {optimized_max_days}거래일\n"
                    f"- 검증 방식: 과거 앞 70%에서 기준을 선택하고 최근 30%"
                    f"({hedge_optimization['holdout_start']} 이후)는 따로 확인"
                )
        else:
            st.error(
                "⛔ 사용 중지: 과거 검증 자료가 부족합니다. 오늘 인버스 신규 주문은 0원입니다."
            )

    # 아래의 과거 스프레드·마켓뉴트럴·볼린저 연구 화면은 사용자 행동판에서
    # 완전히 퇴역시켰습니다. 헷징 탭은 여기까지가 실제 사용 화면입니다.
    st.stop()

    # 사전 계산: 볼린저 밴드 폭 (Strategy E용)
    bw = 100.0
    curr_k = 0.0
    curr_lower1 = 0.0
    curr_lower2 = 0.0
    curr_upper1 = 0.0
    curr_upper2 = 0.0
    curr_ma20 = 0.0
    ma20_s = None
    upper2 = None
    lower2 = None
    if not kospi_10y.empty:
        try:
            k = kospi_10y['Close'].tail(60)
            ma20_s = k.rolling(20).mean()
            std20_s = k.rolling(20).std()
            upper2 = ma20_s + 2 * std20_s
            lower2 = ma20_s - 2 * std20_s
            upper1 = ma20_s + 1 * std20_s
            lower1 = ma20_s - 1 * std20_s
            
            curr_k = float(k.iloc[-1])
            curr_upper2 = float(upper2.iloc[-1])
            curr_lower2 = float(lower2.iloc[-1])
            curr_upper1 = float(upper1.iloc[-1])
            curr_lower1 = float(lower1.iloc[-1])
            curr_ma20   = float(ma20_s.iloc[-1])
            bw = (curr_upper2 - curr_lower2) / curr_ma20 * 100
        except: pass

    # ════════════════════════════════════════════
    # 🗺️ 저위험 방어수단 통합 매트릭스
    # ════════════════════════════════════════════
    matrix_data = {
        "전략": [
            "① 현금·단기자금 완충",
            "② 변동성 맞춤 주식비중",
            "③ 장기추세 필터",
            "④ 단계별 재진입",
            "⑤ 원/달러 소규모 분산",
        ],
        "상태": [
            "🟢 기본",
            "🟢 검증 통과" if defensive_validation_passed else "🟡 주문 보류",
            "🟢 정상 추세" if defensive_state.get("above_trend") else "🟠 방어 추세",
            f"{defensive_state.get('reentry_stage', 0)}/4 단계",
            "🟡 5% 이내 후보" if usd_diversifier.get("eligible") else "⚪ 제외",
        ],
        "역할과 한도": [
            f"목표 {target_cash_value:,.0f}만원 / 바닥 매수용 예비자금",
            "목표변동성에 맞추되 주간 총자산 10%p 이내 조정",
            f"{defensive_state.get('trend_days', 200)}일선 아래에서는 주식 상한 축소",
            defensive_state.get("reentry_label", "데이터 확인 필요"),
            usd_diversifier.get("message", "분산효과 확인 필요"),
        ]
    }
    with st.expander("전문가용 · 기본 방어조합의 구성"):
        st.dataframe(
            pd.DataFrame(matrix_data).set_index("전략"),
            width="stretch",
        )
        st.info(
            "기본 전략에서 제외: 옵션·콜라(만기·프리미엄), 변동성 ETN(경로·롤 비용), "
            "레버리지/곱버스(일간 재설정), 페어·마켓뉴트럴(상관·모형 붕괴)."
        )

    # ════════════════════════════════════════════
    # 📊 변동성 레짐 정밀 분류기 UI (Strategy B)
    # ════════════════════════════════════════════
    with st.expander("전문가용 · 시장 상태를 판단한 근거"):
        st.markdown(f"""
        <div style='background-color:#f8f9fa; padding:20px; border-radius:10px; border-left: 8px solid {vol_color}; margin-bottom:20px;'>
            <h4 style='margin-top:0; color:#333;'>상태: <span style='color:{vol_color}; font-weight:bold;'>{vol_regime}</span></h4>
            <p style='font-size:1.05em; color:#444; line-height:1.6; margin-bottom:10px;'>
            <b>대응 액션</b>: {vol_action}
            </p>
            <ul style='font-size:0.95em; color:#666;'>
                {"".join([f"<li>{d}</li>" for d in vol_details])}
            </ul>
        </div>
        """, unsafe_allow_html=True)

    # ── 오늘의 추천 트레이딩 패널 ──
    trade_recommendation = defensive_action["title"]
    trade_reason = (
        f"{defensive_action['reason']} "
        f"현재 위험이 이어질 때의 방어 목표는 국내 주식 {target_equity_value:,.0f}만원, "
        f"현금 {target_cash_value:,.0f}만원입니다. "
        "복잡한 숏·옵션 전략은 오늘 실행 대상이 아닙니다."
    )
    trade_color = defensive_color
        
    with st.expander("전문가용 · 오늘 결론의 상세 계산"):
        st.markdown(f"""
        <div style='background-color:#f8f9fa; padding:20px; border-radius:10px; border-left: 8px solid {trade_color}; margin-bottom:20px;'>
            <h4 style='margin-top:0; color:#333;'>추천 헷징 포지션: <span style='color:{trade_color}; font-weight:bold;'>{trade_recommendation}</span></h4>
            <p style='font-size:1.05em; color:#444; line-height:1.6; margin-bottom:0;'>
            <b>계산 근거</b>:<br>
            {trade_reason}
            </p>
        </div>
        """, unsafe_allow_html=True)

    # ════════════════════════════════════════════
    # 🧮 베타 기반 포지션 사이저
    # ════════════════════════════════════════════
    with st.expander("내 계좌 기준 금액 계산 자세히 보기"):
        size_metrics = st.columns(4)
        size_metrics[0].metric(
            "시장에 노출된 금액",
            f"{hedge_size['beta_exposure']:,.0f}만원",
        )
        size_metrics[1].metric(
            "줄이고 싶은 위험",
            f"{hedge_size['target_notional']:,.0f}만원",
        )
        size_metrics[2].metric(
            "실제 사용 상한",
            f"{hedge_size['recommended_allocation']:,.0f}만원",
        )
        size_metrics[3].metric(
            "예상 방어 비율",
            f"{hedge_size['achieved_coverage'] * 100:.1f}%",
        )

        if hedge_size["raw_allocation"] > hedge_size["policy_cap"]:
            st.warning(
                f"목표를 그대로 맞추려면 {hedge_size['raw_allocation']:,.0f}만원이 필요하지만 "
                f"안전 한도는 {hedge_size['policy_cap']:,.0f}만원입니다. "
                "부족한 부분은 인버스를 늘리지 말고 국내 주식 금액을 줄여 보완합니다."
            )
        else:
            st.info(
                f"현재 계좌 입력값으로 계산한 최대 방어 예산은 "
                f"**{hedge_size['recommended_allocation']:,.0f}만원**입니다."
            )

    # ════════════════════════════════════════════
    # 🧪 실제 ETF 기반 헷지 백테스트
    # ════════════════════════════════════════════
    hedge_backtests = {}
    comparison_rows = []
    for policy_key, policy in HEDGE_HORIZONS.items():
        result = run_hedge_backtest(
            kospi_hist=kospi_10y,
            vkospi_hist=vkospi_10y,
            usdkrw_hist=usd_krw,
            inverse1x_hist=inverse1x_10y,
            inverse2x_hist=inverse2x_10y,
            horizon_key=policy_key,
            transaction_cost_bps=transaction_cost_bps,
        )
        hedge_backtests[policy_key] = result
        if result.get("status") == "ok":
            metrics = result["metrics"]
            comparison_rows.append(
                {
                    "기간 정책": policy.label,
                    "사용 상품": policy.product,
                    "거래 수": metrics["trades"],
                    "승률": f"{metrics['win_rate']:.1f}%",
                    "평균 거래": f"{metrics['avg_trade_return']:+.2f}%",
                    "평균 보유": f"{metrics['avg_holding_days']:.1f}일",
                    "무헷지 MDD": f"{metrics['unhedged_mdd']:.1f}%",
                    "헷지 MDD": f"{metrics['hedged_mdd']:.1f}%",
                    "MDD 개선": f"{metrics['mdd_improvement']:+.1f}%p",
                }
            )

    with st.expander("고급 분석 · 전체 기간 백테스트 표와 차트"):
        st.caption(
            "당일 종가 신호를 다음 거래일 시가에 실행하고, 실제 252670·114800 가격과 "
            f"왕복 {transaction_cost_bps * 2:.2f}bp 비용을 반영했습니다."
        )
        if comparison_rows:
            st.dataframe(
                pd.DataFrame(comparison_rows),
                width="stretch",
                hide_index=True,
            )
            valid_candidates = [
                (policy_key, result)
                for policy_key, result in hedge_backtests.items()
                if result.get("status") == "ok"
                and result["metrics"]["avg_trade_return"] > 0
                and result["metrics"]["profit_factor"] > 1
                and result["metrics"]["mdd_improvement"] > 0
            ]
            if valid_candidates:
                best_key, best_result = max(
                    valid_candidates,
                    key=lambda item: item[1]["metrics"]["mdd_improvement"],
                )
                best_metrics = best_result["metrics"]
                st.success(
                    f"전체 기간 참고 결과: {HEDGE_HORIZONS[best_key].label} · "
                    f"평균 {best_metrics['avg_trade_return']:+.2f}% · "
                    f"수익/손실 비율 {best_metrics['profit_factor']:.2f} · "
                    f"최대 낙폭 개선 {best_metrics['mdd_improvement']:+.1f}%p"
                )
            selected_backtest = hedge_backtests.get(horizon_key, {})
            if selected_backtest.get("status") == "ok":
                selected_curve = selected_backtest["equity_curve"][["무헷지", "헷지 적용"]]
                st.line_chart(selected_curve, height=300)
        else:
            messages = sorted({
                result.get("message", "백테스트 데이터 부족")
                for result in hedge_backtests.values()
            })
            st.warning(" / ".join(messages))

        st.markdown(
            "**용어:** 승률은 돈을 번 거래 비율, 평균 거래는 한 번 실행했을 때의 평균 결과, "
            "최대 낙폭은 평가금액이 고점에서 가장 크게 줄었던 폭입니다."
        )

    # 🚨 인버스 진입 및 청산 통합 UI (Strategy A 연동)
    with st.expander("고급 분석 · 점수 계산 내역"):
        col_in, col_out = st.columns(2)
        with col_in:
            inv_verdict = hedge_decision.headline
            inv_color = {
                "high": "#dc3545",
                "medium": "#ffc107",
                "low": "#28a745",
            }.get(hedge_decision.urgency, "#6c757d")

            st.markdown(f"""
            <div style='background-color:#f8f9fa; padding:15px; border-radius:10px; border-left: 6px solid {inv_color}; height:100%;'>
                <h5 style='margin-top:0;'>하락방어 신호: <span style='color:{inv_color};'>{inv_score}/{optimized_entry_threshold:.0f}점</span></h5>
                <p style='font-weight:bold; color:{inv_color};'>{inv_verdict}</p>
                <p style='font-size:0.9em; color:#555;'>{hedge_decision.reason}</p>
                <ul style='font-size:0.9em; color:#666;'>
                    {"".join([f"<li>{d}</li>" for d in inv_details])}
                </ul>
            </div>
            """, unsafe_allow_html=True)

        with col_out:
            if position_status == "none":
                exit_display_verdict = "보유 인버스가 없어 지금은 확인만 합니다"
                exit_display_color = "#6c757d"
            else:
                exit_display_verdict = exit_verdict
                exit_display_color = exit_color
            st.markdown(f"""
            <div style='background-color:#f8f9fa; padding:15px; border-radius:10px; border-left: 6px solid {exit_display_color}; height:100%;'>
                <h5 style='margin-top:0;'>줄이기 신호: <span style='color:{exit_display_color};'>{exit_score}/{optimized_exit_threshold:.0f}점</span></h5>
                <p style='font-weight:bold; color:{exit_display_color};'>{exit_display_verdict}</p>
                <ul style='font-size:0.9em; color:#666;'>
                    {"".join([f"<li>{d}</li>" for d in exit_details])}
                </ul>
            </div>
            """, unsafe_allow_html=True)

    st.divider()
    st.markdown("### 실행 대상에서 뺀 고위험 연구 기록")
    st.warning(
        "아래 지표는 연구 기록만 남기며 매수·매도 추천을 만들지 않습니다. "
        "상관관계 붕괴, 공매도 실행, 잦은 매매 위험 때문에 기본 행동판에서는 제외했습니다."
    )

    st.markdown("#### 제외 ① 코스피200·코스닥 스프레드")
    if has_spread_data:
        if spread_adf.get("status") != "ok":
            spread_verdict = "⚪ 공적분 검정 불가 — 전략 비활성"
            spread_color = "#6c757d"
        elif not spread_adf.get("is_cointegrated", False):
            spread_verdict = "⚪ 공적분 관계 없음 — 평균회귀 전략 비활성"
            spread_color = "#6c757d"
        elif curr_z >= 2.2:
            spread_verdict = "🔴 KOSPI 200 극단 고평가 / KOSDAQ 과매도 (Z >= 2.2)"
            spread_color = "#dc3545"
        elif curr_z <= -2.2:
            spread_verdict = "🟢 KOSDAQ 극단 고평가 / KOSPI 200 과매도 (Z <= -2.2)"
            spread_color = "#28a745"
        else:
            spread_verdict = "⚪ 정상 변동 범위 내 (평균 회귀 대기)"
            spread_color = "#6c757d"
        spread_status_text = (
            f"ADF p={spread_adf['spread_adf_pvalue']:.3f}, "
            f"헤지비율 β={spread_adf['hedge_ratio']:.3f}"
            if spread_adf.get("status") == "ok"
            else f"검정 불가: {spread_adf.get('status')} ({spread_adf.get('error', '')})"
        )
        st.markdown(
            f"**현재 잔차 Z-Score**: <span style='color:{spread_color}; font-weight:bold; font-size:1.1em;'>{curr_z:+.2f}</span> "
            f"(진입 임계치: ±2.2) · {spread_status_text}",
            unsafe_allow_html=True,
        )
        st.markdown(f"**연구 상태:** {spread_verdict} · **실행: 제외**")
        if spread_adf.get("status") == "ok":
            z_column = "Residual_Z" if "Residual_Z" in combined.columns else "Z_Score"
            z_df = pd.DataFrame({"공적분 잔차 Z-Score": combined[z_column].tail(60)})
            st.line_chart(z_df)
    else:
        st.info("지수 데이터를 로드할 수 없습니다.")

    st.divider()
    
    st.markdown("#### 제외 ② 마켓뉴트럴")
    with st.expander("💡 [필독] 마켓 뉴트럴(시장 중립) 전략이란?"):
        st.markdown(
            "고배당 ETF(Long)와 인버스(Short)를 단순 1:1로 섞는다고 시장중립이 되지는 않습니다. "
            "두 자산의 rolling beta와 실제 헤지비율을 계산해 순베타가 0에 가까운지 검증해야 합니다."
        )
    
    if not kospi_10y.empty:
        mn_status = f"⛔ 기본 전략 제외 (볼린저 밴드폭 {bw:.1f}%)"
        mn_action = "실제 순베타·차입비용·공매도 가능 여부를 검증하지 않았으므로 실행하지 않습니다."
        mn_color = "#6c757d"
            
        st.markdown(f"""
        <div style='background-color:#f8f9fa; padding:15px; border-radius:8px; border-left: 6px solid {mn_color}; margin-bottom:15px;'>
            <h5 style='margin-top:0; color:#333;'>상태: <span style='color:{mn_color}; font-weight:bold;'>{mn_status}</span></h5>
            <p style='font-size:0.95em; color:#555; margin-bottom:0;'>
            {mn_action}
            </p>
        </div>
        """, unsafe_allow_html=True)
        
        try:
            k_df = kospi_10y.copy()
            k_df["MA20"] = k_df["Close"].rolling(20).mean()
            k_df["STD20"] = k_df["Close"].rolling(20).std()
            k_df["Bandwidth"] = (k_df["MA20"] + 2*k_df["STD20"] - (k_df["MA20"] - 2*k_df["STD20"])) / k_df["MA20"] * 100
            bw_chart = pd.DataFrame({"KOSPI 밴드폭 (%)": k_df["Bandwidth"].tail(60)})
            st.area_chart(bw_chart)
        except:
            pass

    st.divider()

    # ════════════════════════════════════════════
    # 📈 변동성 수확 연구 기록
    # ════════════════════════════════════════════
    st.markdown("#### 제외 ③ 볼린저 단기매매")
    st.caption("밴드 접촉만으로는 바닥을 확인할 수 없어 기본 행동판의 분할 재진입 조건으로 사용하지 않습니다.")

    with st.expander("💡 [필독] 볼린저 밴드 리밸런싱 전략이란?"):
        st.markdown("""
        **제외 이유**:
        - 밴드 하단을 따라 계속 하락하는 추세장에서 저점 매수가 반복될 수 있습니다.
        - 밴드 상단 전량 매도는 장기 상승 수익을 잘라낼 수 있습니다.
        - 화면에는 연구용 위치만 표시하고 주문 문구는 만들지 않습니다.
        """)

    if not kospi_10y.empty and ma20_s is not None:
        band_pos = (curr_k - curr_lower2) / (curr_upper2 - curr_lower2) * 100 if (curr_upper2 - curr_lower2) > 0 else 50

        bb_cols = st.columns(4)
        bb_cols[0].metric("KOSPI 현재", f"{curr_k:,.1f}")
        bb_cols[1].metric("볼밴 상단(+2σ)", f"{curr_upper2:,.1f}", f"{(curr_k/curr_upper2-1)*100:+.1f}%")
        bb_cols[2].metric("볼밴 중심(MA20)", f"{curr_ma20:,.1f}", f"{(curr_k/curr_ma20-1)*100:+.1f}%")
        bb_cols[3].metric("볼밴 하단(-2σ)", f"{curr_lower2:,.1f}", f"{(curr_k/curr_lower2-1)*100:+.1f}%")

        if curr_atr_ratio >= 1.5:
            bb_signal = "⛔ 추세장 감지 — 볼린저 리밸런싱 전략 비활성화"
            bb_color = "#6c757d"
            bb_action = "ATR 변동성이 과도하여 평균 회귀 가정이 무효입니다."
        elif curr_k <= curr_lower2:
            bb_signal = f"⚪ 볼밴 하단 터치 (밴드 내 위치: {band_pos:.0f}%) — 연구 기록"
            bb_color = "#6c757d"
            bb_action = "이 신호만으로 매수하지 않습니다. 위의 4단계 회복 조건을 따릅니다."
        elif curr_k <= curr_lower1:
            bb_signal = f"⚪ 볼밴 -1σ 접근 (밴드 내 위치: {band_pos:.0f}%) — 연구 기록"
            bb_color = "#6c757d"
            bb_action = "별도 주문을 만들지 않습니다."
        elif curr_k >= curr_upper2:
            bb_signal = f"⚪ 볼밴 상단 터치 (밴드 내 위치: {band_pos:.0f}%) — 연구 기록"
            bb_color = "#6c757d"
            bb_action = "전량매도나 인버스 진입 근거로 사용하지 않습니다."
        elif curr_k >= curr_upper1:
            bb_signal = f"⚪ 볼밴 +1σ 접근 (밴드 내 위치: {band_pos:.0f}%) — 연구 기록"
            bb_color = "#6c757d"
            bb_action = "별도 주문을 만들지 않습니다."
        else:
            bb_signal = f"⚪ 밴드 중립 구간 (밴드 내 위치: {band_pos:.0f}%) — 대기"
            bb_color = "#6c757d"
            bb_action = "밴드 상·하단까지 여유 있음. 신호 대기."

        st.markdown(f"""
        <div style='background:#f8f9fa; padding:15px; border-radius:8px; border-left:6px solid {bb_color}; margin:10px 0;'>
            <b style='color:{bb_color}; font-size:1.1em;'>{bb_signal}</b><br>
            <span style='color:#444; font-size:0.95em;'>👉 {bb_action}</span>
        </div>
        """, unsafe_allow_html=True)

        chart_data = pd.DataFrame({
            "KOSPI": kospi_10y['Close'].tail(60),
            "MA20(중심)": ma20_s,
            "+2σ 상단": upper2,
            "-2σ 하단": lower2,
        }).dropna()
        st.line_chart(chart_data, height=250)

    st.divider()

    st.markdown("#### 제외 ④ 다중 페어 트레이딩")
    with st.expander("💡 [필독] 페어 트레이딩(짝짓기) 스위칭 전략"):
        st.markdown(
            "고평가 자산을 팔고 저평가 자산을 사는 방식이지만, "
            "개인 계좌에서는 공매도·차입비용·상관 붕괴를 통제하기 어려워 기본 전략에서 제외합니다."
        )

    st.caption("공매도·헤지비율·상관 붕괴 위험 때문에 스캐너와 주문 신호를 비활성화했습니다.")

    st.divider()
    
    st.markdown("#### 기본 전략에서 제외한 상품")
    st.markdown("""
    - **2배 인버스·달러 2배 상품:** 일간 재설정과 휩쏘 손실 때문에 기본 조합에서 제외
    - **옵션·변동성 ETN:** 만기, 프리미엄 전액 손실, 롤 비용 때문에 제외
    - **페어·마켓뉴트럴:** 공매도 실행과 상관관계 붕괴 위험 때문에 제외
    - **원/달러 분산:** 최근 상관과 추세가 확인될 때만 총자산 5% 이내의 후보로 표시
    """)




