import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import datetime
import FinanceDataReader as fdr
import requests

st.set_page_config(page_title="11원칙 퀀트 대시보드 v17.13", page_icon="🧭", layout="wide")

# ─────────────────────────────────────────
# 한글 이름 → 티커 매핑
# ─────────────────────────────────────────
US_NAME_MAP = {
    "애플": "AAPL", "마이크로소프트": "MSFT", "엔비디아": "NVDA", "구글": "GOOGL", "알파벳": "GOOGL",
    "아마존": "AMZN", "메타": "META", "테슬라": "TSLA", "브로드컴": "AVGO", "이튼": "ETN",
    "버티브": "VRT", "스타벅스": "SBUX", "넷플릭스": "NFLX", "팔란티어": "PLTR",
    "일라이릴리": "LLY", "코카콜라": "KO", "AMD": "AMD", "퀄컴": "QCOM", "인텔": "INTC", "TSMC": "TSM",
    "아이온큐": "IONQ", "소파이": "SOFI", "크라우드스트라이크": "CRWD", "스노우플레이크": "SNOW",
    "암": "ARM", "ARM": "ARM", "슈퍼마이크로": "SMCI", "슈마컴": "SMCI",
    "웨스턴디지털": "WDC", "샌디스크": "SNDK"
}

@st.cache_data(ttl=86400)
def get_krx_mapping():
    try:
        df = fdr.StockListing('KRX')
        mapping = {}
        for _, row in df.iterrows():
            market_suffix = ".KS" if row['Market'] == 'KOSPI' else ".KQ"
            mapping[str(row['Name']).upper()] = {
                "raw_code": row['Code'],
                "yf_code": row['Code'] + market_suffix
            }
        return mapping
    except:
        return {}

KRX_DICT = get_krx_mapping()

def get_kst_now():
    kst = datetime.timezone(datetime.timedelta(hours=9))
    return datetime.datetime.now(kst)

# ─────────────────────────────────────────
# CNN F&G
# ─────────────────────────────────────────
@st.cache_data(ttl=1800)
def get_real_cnn_fg():
    try:
        url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
            "Referer": "https://edition.cnn.com/",
            "Origin": "https://edition.cnn.com"
        }
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code != 200:
            return None, "API 차단됨", None
        data = response.json()
        current_score = round(data['fear_and_greed']['score'])
        rating = data['fear_and_greed']['rating'].title()
        hist_data = data['fear_and_greed_historical']['data']
        df_fg = pd.DataFrame(hist_data)
        df_fg['Date'] = pd.to_datetime(df_fg['x'], unit='ms')
        df_fg.set_index('Date', inplace=True)
        return current_score, rating, df_fg['y']
    except:
        return None, "데이터 수집 오류", None

# ─────────────────────────────────────────
# RSI
# ─────────────────────────────────────────
def calc_rsi(close, period=14):
    if len(close) < period + 1:
        return None
    delta = close.diff()
    gain  = delta.clip(lower=0)
    loss  = -delta.clip(upper=0)
    avg_g = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_l = loss.ewm(com=period - 1, min_periods=period).mean()
    rs    = avg_g / avg_l
    return round(float((100 - 100 / (1 + rs)).iloc[-1]), 2)

def calc_macd(close):
    if len(close) < 35:
        return None, "N/A"
    macd = close.ewm(span=12, adjust=False).mean() - close.ewm(span=26, adjust=False).mean()
    hist = macd - macd.ewm(span=9, adjust=False).mean()
    return round(float(macd.iloc[-1]), 2), "🟢상승" if hist.iloc[-1] > 0 else "🔴하락"

# ─────────────────────────────────────────
# 섹터 ETF 기준선
# ─────────────────────────────────────────
@st.cache_data(ttl=1800)
def get_sector_baseline():
    benchmarks = {"S&P 500 (SPY)": "SPY", "반도체 (SOXX)": "SOXX", "유틸리티 (XLU)": "XLU"}
    res = {}
    for name, ticker in benchmarks.items():
        try:
            hist = yf.Ticker(ticker).history(period="3mo")['Close']
            res[name] = calc_rsi(hist, 14)
        except:
            res[name] = None
    return res

# ─────────────────────────────────────────
# 시장대비 강도 — ETF RSI 기반, 절댓값 레벨 보정
# ─────────────────────────────────────────
def relative_strength_label(my_rsi, spy_rsi):
    if my_rsi is None or spy_rsi is None:
        return "N/A"
    gap = my_rsi - spy_rsi
    if my_rsi > 65 and spy_rsi > 65:
        return f"🔵 동반 과매수 (시장 전체 과열, 차이 {gap:+.0f})"
    if my_rsi < 35 and spy_rsi < 35:
        return f"🟠 동반 과매도 (시장 전체 하락, 차이 {gap:+.0f})"
    if gap >= 10:  return f"💪 강한 주도주 (SPY 대비 +{gap:.0f})"
    if gap >= 5:   return f"📈 주도주 (SPY 대비 +{gap:.0f})"
    if gap <= -10: return f"📉 강한 소외주 (SPY 대비 {gap:.0f})"
    if gap <= -5:  return f"⚠️ 소외주 (SPY 대비 {gap:.0f})"
    return f"⚖️ 시장 동기화 (차이 {gap:+.0f})"

# ─────────────────────────────────────────
# 공매도 및 종합 리스크 등급 해석 로직
# ─────────────────────────────────────────
def short_interest_label(short_val):
    if short_val is None:
        return "N/A"
    s_pct = short_val * 100
    if s_pct >= 20:   tag = "🔴 매우 높음"
    elif s_pct >= 10: tag = "🟠 높음"
    elif s_pct >= 5:  tag = "🟡 보통"
    else:             tag = "✅ 낮음"
    return f"{s_pct:.1f}% ({tag})"

def get_comprehensive_risk_grade(short_val, beta_val):
    if short_val is None or beta_val is None:
        return "N/A"
    s_pct = short_val * 100
    is_high_short = s_pct >= 5.0 # 공매도 5% 이상이면 높음으로 간주
    is_high_beta = beta_val >= 1.2 # 베타 1.2 이상이면 높음으로 간주
    
    if not is_high_short and not is_high_beta:
        return "🟢 안정형 — 방어적 투자에 적합"
    elif not is_high_short and is_high_beta:
        return "🟡 모멘텀형 — 상승장에 강하지만 하락 시 크게 빠짐"
    elif is_high_short and not is_high_beta:
        return "🟠 논란형 — 시장은 의심하지만 변동성은 낮음, 이유 확인 필요"
    else:
        return "🔴 고위험 — 하락 베팅 + 큰 변동성, 진입 신중"

# ─────────────────────────────────────────
# ★ 내부자 거래 — 직급 파싱 + SEC EDGAR 링크 생성
# ─────────────────────────────────────────
TITLE_MAP = {
    "ceo": "CEO (최고경영자)", "chief executive": "CEO (최고경영자)",
    "president": "President (대표)", "cfo": "CFO (최고재무책임자)",
    "chief financial": "CFO (최고재무책임자)", "coo": "COO (최고운영책임자)",
    "chief operating": "COO (최고운영책임자)", "cto": "CTO (최고기술책임자)",
    "chief technology": "CTO (최고기술책임자)", "cso": "CSO (최고전략책임자)",
    "chief strategy": "CSO (최고전략책임자)", "cmo": "CMO (최고마케팅책임자)",
    "chief marketing": "CMO (최고마케팅책임자)", "cpo": "CPO (최고상품책임자)",
    "chief product": "CPO (최고상품책임자)", "executive vice president": "EVP (수석부사장)",
    "evp": "EVP (수석부사장)", "senior vice president": "SVP (선임부사장)",
    "svp": "SVP (선임부사장)", "vice president": "VP (부사장)",
    "general counsel": "GC (법무총괄)", "director": "이사 (Director)",
    "chairman": "이사회 의장 (Chairman)", "board": "이사회 멤버",
    "10%": "10% 이상 주요주주", "beneficial": "수익적 소유자",
}

def normalize_title(raw_title: str) -> str:
    if not raw_title: return "직함 미상"
    lower = raw_title.lower().strip()
    for key, label in TITLE_MAP.items():
        if key in lower: return label
    return raw_title.strip()

def get_edgar_link(ticker: str) -> str:
    return (f"https://www.sec.gov/cgi-bin/browse-edgar"
            f"?action=getcompany&company={ticker}&type=4"
            f"&dateb=&owner=include&count=10&search_text=")

def parse_insider(tk, ticker_str: str):
    edgar_url = get_edgar_link(ticker_str)
    status    = "내역 없음"
    detail    = ""
    try:
        insider_trans = tk.insider_transactions
        if insider_trans is None or insider_trans.empty:
            return "내역 없음", "", edgar_url

        for idx, row in insider_trans.head(30).iterrows():
            row_dict = {k.lower(): v for k, v in row.to_dict().items()}
            row_str  = str(row_dict)

            is_buy = ("buy" in row_str.lower() or "purchase" in row_str.lower())
            is_sell_or_exercise = ("sale" in row_str.lower() or "sell" in row_str.lower() or 
                                   "exercise" in row_str.lower() or "tax" in row_str.lower())

            if is_buy and not is_sell_or_exercise:
                name = (row_dict.get('insider') or row_dict.get('name') or 
                        row_dict.get('filer') or "이름 미상")
                raw_title = (row_dict.get('title') or row_dict.get('relationship') or 
                             row_dict.get('position') or row_dict.get('role') or "")
                title = normalize_title(str(raw_title))
                shares = (row_dict.get('shares') or row_dict.get('qty') or 
                          row_dict.get('quantity') or "미상")
                value = (row_dict.get('value') or row_dict.get('transaction value') or None)

                date_str = (idx.strftime('%Y-%m-%d') if hasattr(idx, 'strftime') else str(idx)[:10])
                status = "🟢 매수 기록 있음"
                value_str = f" / 거래금액 ${value:,.0f}" if value and isinstance(value, (int, float)) else ""
                detail = (f"[{date_str}] {name} — {title}\n        순수 매수 {shares}주{value_str}")
                break 

        if status == "내역 없음":
            try:
                first = insider_trans.iloc[0]
                row_dict = {k.lower(): v for k, v in first.to_dict().items()}
                trans_type = (row_dict.get('transaction') or row_dict.get('text') or "거래 기록 있음 (매수 아님)")
                status = f"⚪ {str(trans_type)[:30]}"
            except:
                status = "내역 없음"

    except Exception as e:
        status = f"조회 불가 ({str(e)[:30]})"

    return status, detail, edgar_url

# ─────────────────────────────────────────
# 시그널 로직
# ─────────────────────────────────────────
def get_ai_signal(d):
    rsi  = d.get('RSI_14')
    cp   = d.get('Price')
    ma20 = d.get('MA20')
    vol  = d.get('Vol_ratio')
    macd = d.get('MACD_dir') or ""
    roe  = d.get('ROE')
    op_m = d.get('Op_Margin')

    if rsi is None or cp is None or ma20 is None:
        return "⚪ 데이터 부족 (판단 보류)"

    rsi_f    = float(rsi)
    cp_f     = float(cp)
    ma20_f   = float(ma20)
    vol_f    = float(vol) if vol is not None else 100.0
    ma20_gap = (cp_f - ma20_f) / ma20_f * 100

    roe_f  = float(roe)  if roe  is not None else None
    op_m_f = float(op_m) if op_m is not None else None
    if roe_f is not None and op_m_f is not None:
        if roe_f < 0 and op_m_f < 0:
            return "⚫ 경고 (적자 기업)"

    if rsi_f >= 75 and ma20_gap > 15:
        return "🔵 과매수 (익절/관망)"
    if 60 <= rsi_f < 75 and cp_f > ma20_f and "상승" in macd and vol_f > 120:
        return "🚀 추세 탑승 (불타기)"
    if 45 <= rsi_f < 60 and cp_f >= ma20_f:
        return "🟢 얕은 눌림목 (분할매수)"
    if rsi_f < 45:
        return "🔥 바닥 줍줍 (적극매수)"
    return "🟡 방향성 탐색 (관망)"

def calculate_smart_target(d, ai_sig):
    cp       = d.get('Price')
    ma5      = d.get('MA5', cp)
    ma20     = d.get('MA20', cp)
    bb_upper = d.get('BB_upper', cp)
    bb_lower = d.get('BB_lower', cp)
    if "추세 탑승"  in ai_sig: return max(ma5, cp * 0.98), "5일선 지지"
    elif "눌림목"   in ai_sig: return ma20,     "20일선 스윙"
    elif "바닥 줍줍" in ai_sig: return bb_lower, "볼린저 하단"
    elif "과매수"   in ai_sig: return bb_upper,  "볼린저 상단"
    else: return "-", "홀딩(Wait)"

def get_tenbagger_signal(d):
    mcap   = float(d.get('MarketCap') or 0)
    region = d.get('Region')
    rev_g  = float(d.get('Rev_Growth') or 0)
    op_m   = float(d.get('Op_Margin')  or 0)
    peg    = float(d.get('PEG')        or 99)
    if region == "미국" and mcap >= 50_000_000_000:   return "🐘 대형주 (제외)"
    if region == "한국" and mcap >= 5_000_000_000_000: return "🐘 대형주 (제외)"
    points = sum([rev_g >= 0.20, op_m >= 0.10, 0 < peg <= 1.5])
    return "🚀 텐배거(1순위)" if points >= 3 else ("🌱 폭발적 성장" if points == 2 else "-")

# ─────────────────────────────────────────
# 메인 데이터 수집
# ─────────────────────────────────────────
@st.cache_data(ttl=180)
def get_stock_data(query, is_kr=False):
    base = {"Name": query, "error": None}
    try:
        kst_now = get_kst_now()
        start   = (kst_now - datetime.timedelta(days=365)).strftime('%Y-%m-%d')

        if is_kr:
            kr_info = KRX_DICT.get(str(query).strip().upper())
            if kr_info: raw_code, yf_code = kr_info["raw_code"], kr_info["yf_code"]
            else:        raw_code, yf_code = query, f"{query}.KS"
            hist = fdr.DataReader(raw_code, start=start).dropna()
            tk   = yf.Ticker(yf_code)
            info = tk.info
            ticker_str = raw_code
        else:
            ticker_str = US_NAME_MAP.get(str(query).strip().upper(), query).upper()
            tk         = yf.Ticker(ticker_str)
            hist       = tk.history(period="1y").dropna()
            info       = tk.info

        if hist.empty or len(hist) < 30:
            base["error"] = "데이터 부족"
            return base

        close = hist['Close']
        vol   = hist['Volume']
        price = float(close.iloc[-1])
        prev  = float(close.iloc[-2])

        high_52w  = float(close.max())
        low_52w   = float(close.min())
        w52_range = high_52w - low_52w
        w52_pos   = round((price - low_52w) / w52_range * 100, 1) if w52_range > 0 else 50.0
        gap_high  = round((price - high_52w) / high_52w * 100, 1)

        base["Price"]    = int(price) if is_kr else round(price, 2)
        base["Change"]   = round((price - prev) / prev * 100, 2)
        base["RSI_7"]    = calc_rsi(close, 7)
        base["RSI_14"]   = calc_rsi(close, 14)
        base["RSI_21"]   = calc_rsi(close, 21)
        base["W52_pos"]  = w52_pos
        base["Gap_High"] = gap_high
        base["MACD_dir"] = calc_macd(close)[1]

        ma5  = close.rolling(5).mean().iloc[-1]
        ma20 = close.rolling(20).mean().iloc[-1]
        std  = close.rolling(20).std().iloc[-1]
        base["MA5"]       = ma5
        base["MA20"]      = ma20
        base["BB_upper"]  = ma20 + 2 * std
        base["BB_lower"]  = ma20 - 2 * std
        base["Vol_ratio"] = round(float(vol.iloc[-1] / vol.rolling(20).mean().iloc[-2] * 100), 1)
        base["MA20_gap"]  = round((price - ma20) / ma20 * 100, 2)
        base["_ticker"]   = ticker_str

        base.update({
            "MarketCap":  info.get('marketCap', 0),
            "PER":        info.get('trailingPE'),
            "PBR":        info.get('priceToBook'),
            "ROE":        info.get('returnOnEquity'),
            "Op_Margin":  info.get('operatingMargins'),
            "PEG":        info.get('pegRatio'),
            "Rev_Growth": info.get('revenueGrowth'),
        })

        for k in ["Earnings_Beat","Next_Earning","Short_Interest","Beta",
                  "Latest_News","Insider_Buy","Insider_Detail","Edgar_URL", "Risk_Grade"]:
            base[k] = "N/A"
        base["Insider_Detail"] = ""
        base["Edgar_URL"]      = ""

        if not is_kr:
            # 어닝
            try:
                earns = tk.get_earnings_dates(limit=10)
                beats, valid = 0, 0
                if earns is not None and not earns.empty:
                    past = earns[earns.index < pd.Timestamp.now(tz='UTC')].head(4)
                    for _, row in past.iterrows():
                        rep = row.get('Reported EPS')
                        est = row.get('Estimate')
                        if pd.notna(rep) and pd.notna(est):
                            valid += 1
                            if rep > est: beats += 1
                    if valid > 0:
                        base["Earnings_Beat"] = f"{valid}전 {beats}승"
                    future = earns[earns.index > pd.Timestamp.now(tz='UTC')].sort_index()
                    if not future.empty:
                        base["Next_Earning"] = future.index[0].strftime('%Y-%m-%d')
            except:
                pass

            # 공매도 비율 및 변동성
            short_raw = info.get('shortPercentOfFloat')
            beta_raw = info.get('beta')

            base["Short_Interest"] = short_interest_label(short_raw)

            if beta_raw:
                tag = "🎢 고변동성" if beta_raw >= 1.2 else ("🛡️ 방어적" if beta_raw <= 0.8 else "⚖️ 시장수준")
                base["Beta"] = f"{beta_raw:.2f} ({tag})"

            # ★ 종합 리스크 등급 생성
            base["Risk_Grade"] = get_comprehensive_risk_grade(short_raw, beta_raw)

            # 뉴스
            try:
                news_data = tk.news
                if news_data:
                    base["Latest_News"] = (
                        news_data[0].get('content', {}).get('title')
                        or news_data[0].get('title', 'N/A')
                    )
            except:
                pass

            # 내부자 거래
            status, detail, edgar_url = parse_insider(tk, ticker_str)
            base["Insider_Buy"]    = status
            base["Insider_Detail"] = detail
            base["Edgar_URL"]      = edgar_url

    except Exception as e:
        base["error"] = str(e)
    return base

# ─────────────────────────────────────────
# 포맷 헬퍼 및 컬러링 
# ─────────────────────────────────────────
def fmt_mcap(mcap, region):
    if not mcap or mcap == 0: return "N/A"
    return f"${mcap/1e9:.1f}B" if region == "미국" else (
        f"{mcap/1e12:.2f}조 원" if mcap >= 1e12 else f"{mcap/1e8:.0f}억 원"
    )

def fmt_price(val, region):
    if val is None or val == "-": return "-"
    return f"{int(val):,}원" if region == "한국" else f"${float(val):,.2f}"

def fmt(val, sfx="", dig=2, na="N/A"):
    if val is None or (isinstance(val, float) and np.isnan(val)) or val == "N/A":
        return na
    if isinstance(val, (int, float)):
        return f"{val:.{dig}f}{sfx}"
    return f"{val}{sfx}"

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
    if any(x in val for x in ["🔥 바닥 줍줍","🚀 추세 탑승","🚀 텐배거","🟢 매수 기록"]):
        return 'background-color: #ffcccc; font-weight: bold; color: black'
    if any(x in val for x in ["🟢 얕은 눌림목","🌱 폭발적 성장","💪","📈 주도주", "🟢 안정형"]):
        return 'background-color: #ccffcc; font-weight: bold; color: black'
    if any(x in val for x in ["⚫ 경고","📉 강한 소외주", "🔴 고위험", "🔴 매우 높음"]):
        return 'background-color: #555555; font-weight: bold; color: white'
    if any(x in val for x in ["🟡 모멘텀형", "🟠 논란형", "🟠 높음", "🟡 보통"]):
        return 'background-color: #fff3cd; font-weight: bold; color: black'
    if any(x in val for x in ["🔵 과매수","🔵 동반 과매수"]):
        return 'color: blue; font-weight: bold'
    if "🐘 대형주" in val:
        return 'color: gray; font-style: italic'
    if "⚪ 데이터 부족" in val:
        return 'color: gray; font-style: italic'
    return ''

# ─────────────────────────────────────────
# UI
# ─────────────────────────────────────────
st.title("🧭 11원칙 퀀트 트레이딩 대시보드 v17.13")
st.caption("v17.13: 종합 리스크 등급 탭 신설 + 자동해석 로직 탑재 | VIX 차트 직관성(색상) 개선")

# ★ 탭 구성 추가 (리스크 등급 가이드 탭 신설)
tab1, tab5, tab_risk, tab4, tab2, tab3 = st.tabs([
    "📊 실시간 포트폴리오", "📖 11원칙 매매 가이드라인", "🚨 리스크 등급 가이드",
    "🚀 오늘의 텐배거 레이더", "🌐 매크로 & F&G Index", "🤖 AI 참모 리포트"
])

with tab5:
    st.header("📖 11원칙 퀀트 매매 가이드라인")
    st.markdown("""
이 대시보드는 팩트와 데이터를 기반으로 감정을 배제하고 기계적으로 매매하기 위한 11가지 핵심 원칙입니다.

**[ 펀더멘탈 필터링 ]**
- **1원칙 (시가총액):** 소형주 변동성 리스크 배제, 텐배거 후보에서 초대형주 제외
- **2원칙 (매출성장률):** 전년 대비 20% 이상 구조적 성장
- **3원칙 (영업이익률):** 10% 이상의 수익 체력
- **4원칙 (PEG):** 1.5 이하 = 저평가 성장주
- **5원칙 (ROE):** 5% 이상 흑자 기업

**[ 기술적 타점 ]**
- **6원칙 (RSI):** 45 미만 = 바닥 할인 / 75 이상 = 과매수 익절. 7/14/21일 멀티타임프레임 교차 확인
- **7원칙 (이동평균선):** 20일선 지지 기준, 20일선 대비 +15% 이상 추격 금지
- **8원칙 (거래량):** 평소 대비 120% 이상 + MACD 상승 = 세력 추세 탑승 신호

**[ 리스크 & 심리 관리 ]**
- **9원칙 (F&G 역발상):** 극단적 공포 → 우량주 바닥 진입 / 극단적 탐욕 → 현금 비중 확대
- **10원칙 (섹터 상대강도):** SPY ETF RSI 14일 기준으로 종목 RSI 비교. 단, 둘 다 과매수/과매도면 절댓값 우선 판단
- **11원칙 (스마트머니):** 내부자 순수 매수(행사·자동매매 제외) 확인 → SEC EDGAR Form 4 원문 교차확인 권장
    """)

# ★ 종합 리스크 등급 안내 탭 구현
with tab_risk:
    st.header("🚨 공매도 & 변동성(Beta) 종합 리스크 가이드")
    st.markdown("""
    공매도 비율(Short Interest)과 시장 민감도(Beta)를 조합하여 개별 종목의 리스크 성격을 4가지로 분류합니다.
    투자에 진입하기 전, 해당 종목이 어떤 위험을 내포하고 있는지 직관적으로 파악하여 비중 조절에 활용하세요.

    | 공매도 비율 | Beta (변동성) | 종합 리스크 등급 및 해석 |
    | :--- | :--- | :--- |
    | 낮음 (5% 미만) | 낮음 (1.2 미만) | **🟢 안정형 — 방어적 투자에 적합** |
    | 낮음 (5% 미만) | 높음 (1.2 이상) | **🟡 모멘텀형 — 상승장에 강하지만 하락 시 크게 빠짐** |
    | 높음 (5% 이상) | 낮음 (1.2 미만) | **🟠 논란형 — 시장은 의심하지만 변동성은 낮음, 이유 확인 필요** |
    | 높음 (5% 이상) | 높음 (1.2 이상) | **🔴 고위험 — 하락 베팅 + 큰 변동성, 진입 신중** |

    * **공매도 비율(Short Interest)**: 유통 주식 중 공매도가 차지하는 비율입니다. 5% 이상이면 시장의 하락 베팅 세력이 존재함을 의미합니다.
    * **Beta**: 시장(S&P 500)이 1% 움직일 때 종목이 움직이는 민감도입니다. 1.2 이상이면 시장보다 변동성이 큰 '고변동성' 종목으로 분류합니다.
    """)

cnn_score, cnn_rating, cnn_history = get_real_cnn_fg()
sector_base = get_sector_baseline()
spy_rsi_val = sector_base.get("S&P 500 (SPY)")

with tab2:
    st.subheader("🌐 글로벌 매크로 및 시장 심리")
    with st.spinner("매크로 데이터 수집 중..."):
        usd_krw = get_stock_data("KRW=X")
        vix_1y  = yf.Ticker("^VIX").history(period="1y")
        current_vix = round(float(vix_1y['Close'].iloc[-1]), 2) if not vix_1y.empty else "N/A"
        vix_change  = round(((current_vix - float(vix_1y['Close'].iloc[-2])) /
                              float(vix_1y['Close'].iloc[-2])) * 100, 2) if not vix_1y.empty else 0

    col1, col2, col3 = st.columns(3)
    col1.metric("환율 (USD/KRW)",
                fmt_price(usd_krw.get('Price'), "한국").replace("원", " 원"),
                fmt_change(usd_krw.get('Change')))
    col2.metric("미국 VIX", current_vix, f"{vix_change}%", delta_color="inverse")
    if cnn_score is not None:
        if cnn_score <= 25:   fg_color, fg_stat = "🔴", "극단적 공포"
        elif cnn_score <= 45: fg_color, fg_stat = "🟠", "공포"
        elif cnn_score <= 55: fg_color, fg_stat = "🟡", "중립"
        elif cnn_score <= 75: fg_color, fg_stat = "🟢", "탐욕"
        else:                 fg_color, fg_stat = "🟢", "극단적 탐욕"
        col3.metric("CNN Fear & Greed", f"{cnn_score} / 100", f"{fg_color} {fg_stat}")
    else:
        col3.metric("CNN Fear & Greed", "N/A", cnn_rating)

    st.divider()
    st.markdown("#### 🧭 섹터 ETF 기준선 (RSI 14일) — 시장대비 강도 비교 기준값")
    m1, m2, m3 = st.columns(3)
    m1.metric("S&P 500 (SPY)", fmt(spy_rsi_val, dig=1))
    m2.metric("미국 반도체 (SOXX)", fmt(sector_base.get("반도체 (SOXX)"), dig=1))
    m3.metric("미국 유틸리티 (XLU)", fmt(sector_base.get("유틸리티 (XLU)"), dig=1))
    st.caption(
        "💡 **시장대비 강도** = 내 종목 RSI(14일) − SPY RSI(14일). "
        "양수면 시장보다 강한 것, 음수면 시장보다 약한 것. "
        "단, 둘 다 65↑(과매수) 또는 둘 다 35↓(과매도)면 '동반' 상태로 별도 표시."
    )

    st.divider()
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("#### 📉 최근 1년 VIX 추이")
        if not vix_1y.empty:
            # ★ VIX 차트 색상 오류 해결 (VIX 파랑, 위험선 빨강, 평온선 초록으로 명확화)
            st.line_chart(pd.DataFrame({
                "VIX": vix_1y['Close'], "🔴 위험선(30)": 30.0, "🟢 평온선(15)": 15.0
            }), height=300, color=["#1f77b4", "#ff4b4b", "#21c354"])
    with c2:
        st.markdown("#### 🧭 CNN Fear & Greed 1년 추이")
        if cnn_history is not None:
            st.line_chart(pd.DataFrame({
                "F&G Score": cnn_history, "🟢 탐욕(75)": 75.0, "🔴 공포(25)": 25.0
            }), height=300)
        else:
            st.warning("⚠️ CNN 서버 차단 중. 잠시 후 새로고침 해주세요.")

with tab1:
    st.subheader("🔍 관심 종목 스캔")
    c1, c2 = st.columns(2)
    us_input = c1.text_input("🇺🇸 미국 주식", "TSMC, 브로드컴, 버티브")
    kr_input = c2.text_input("🇰🇷 한국 주식", "LS ELECTRIC")

    queries = (
        [("미국", q.strip()) for q in us_input.split(",") if q.strip()] +
        [("한국", q.strip()) for q in kr_input.split(",") if q.strip()]
    )

    all_data, failed_queries = [], []
    with st.spinner("분석 중..."):
        for region, q in queries:
            d = get_stock_data(q, is_kr=(region == "한국"))
            d["Region"] = region
            if not d.get("error"): all_data.append(d)
            else: failed_queries.append(q)

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
                "텐배거 등급": tb_sig,
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
                "종목":       d["Name"],
                "매출성장":   pct(d.get("Rev_Growth")),
                "영업이익률": pct(d.get("Op_Margin")),
                "ROE":        pct(d.get("ROE")),
                "PEG":        fmt(d.get("PEG"), dig=2),
                "PER":        fmt(d.get("PER"), dig=1),
            })

            # ★ 리스크 관리에 종합 리스크 등급 연결
            risk_rows.append({
                "종목":            d["Name"],
                "종합 리스크 등급": d.get("Risk_Grade", "N/A"),
                "다음 실적일":     d.get("Next_Earning", "N/A"),
                "내부자 매수":     d.get("Insider_Buy",  "N/A"),
                "과거 어닝":       d.get("Earnings_Beat","N/A"),
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
                            f"**[📄 SEC EDGAR Form 4 원문 보기 →]({block['url']})**\n\n"
                            f"<small>※ 위 링크에서 거래유형(Transaction Code), "
                            f"직접 매수(P) vs 옵션행사(M) vs 자동매매(F)를 구분할 수 있습니다.</small>",
                            unsafe_allow_html=True
                        )

        st.markdown("#### 💰 4. 밸류에이션")
        st.dataframe(pd.DataFrame(fin_rows).set_index("종목"), use_container_width=True)

with tab4:
    st.subheader("🚀 섹터별 텐배거 마스터 레이더")
    UNIVERSE = {
        "🇺🇸 미국 AI & 클라우드":              ["PLTR","CRWD","SNOW","DDOG","NET","SOUN","MDB","ZS","MNDY"],
        "🇺🇸 미국 혁신성장 (우주/바이오/핀테크)": ["IONQ","SOFI","RIVN","CELH","RKLB","ASTS","CRSP","LUNR","SYM","HOOD"],
        "🇰🇷 한국 K-뷰티 & K-푸드":            ["실리콘투","클래시스","파마리서치","삼양식품","브이티","에이피알","휴젤"],
        "🇰🇷 한국 바이오텍 & 헬스케어":          ["알테오젠","HLB","리가켐바이오","루닛","뷰노","제이엘케이"],
        "🇰🇷 한국 전력기기 & 로봇":             ["HD현대일렉트릭","레인보우로보틱스","두산로보틱스","LS ELECTRIC"],
    }
    selected_theme = st.selectbox("스캔할 섹터:", list(UNIVERSE.keys()))
    if st.button("해당 섹터 레이더 가동"):
        with st.spinner(f"[{selected_theme}] 전수 스캔 중..."):
            is_korea = "한국" in selected_theme
            radar_data = []
            for q in UNIVERSE[selected_theme]:
                d = get_stock_data(q, is_kr=is_korea)
                d["Region"] = "한국" if is_korea else "미국"
                if not d.get("error"): radar_data.append(d)
            radar_rows = []
            for d in radar_data:
                tb_sig = get_tenbagger_signal(d)
                if "🚀" in tb_sig or "🌱" in tb_sig:
                    radar_rows.append({
                        "종목":       d["Name"], "등급": tb_sig,
                        "시가총액":   fmt_mcap(d.get("MarketCap"), d["Region"]),
                        "매출성장":   pct(d.get("Rev_Growth")),
                        "영업이익률": pct(d.get("Op_Margin")),
                        "PEG":        fmt(d.get("PEG"), dig=2),
                    })
            if radar_rows:
                st.dataframe(
                    pd.DataFrame(radar_rows).set_index("종목").style.map(color_df),
                    use_container_width=True
                )
            else:
                st.warning("오늘은 해당 섹터에서 텐배거 기준을 통과한 종목이 없습니다.")

with tab3:
    st.subheader("🤖 AI 참모 전용 구조화 리포트 v17.13")
    now = get_kst_now().strftime('%Y-%m-%d %H:%M:%S KST')
    lines = [
        f"[11원칙 퀀트 분석 리포트 v17.13] ({now})",
        f"- CNN F&G: {cnn_score} ({cnn_rating})",
        f"- SPY RSI(14): {fmt(spy_rsi_val, dig=1)}",
        "",
    ]
    for d in all_data:
        ai_sig = get_ai_signal(d)
        tb_sig = get_tenbagger_signal(d)
        target_p, target_d = calculate_smart_target(d, ai_sig)
        rs_txt = relative_strength_label(d.get("RSI_14"), spy_rsi_val)
        w52    = d.get("W52_pos")
        w52_str = f"{w52}%" if w52 is not None else "N/A"

        lines += [
            f"┌─ [{d['Region']}] {d['Name']} (시그널: {ai_sig} / {tb_sig})",
            f"│ 가격: {fmt_price(d.get('Price'), d['Region'])} | 타점: {target_d} ({fmt_price(target_p, d['Region'])})",
            f"│ RSI 7/14/21: {fmt(d.get('RSI_7'),dig=1)} / {fmt(d.get('RSI_14'),dig=1)} / {fmt(d.get('RSI_21'),dig=1)}",
            f"│ 52주 위치: {w52_str} | 고점대비: {fmt(d.get('Gap_High'),'%',dig=1)} | 시장대비: {rs_txt}",
            f"│ 종합 리스크: {d.get('Risk_Grade', 'N/A')}",
            f"│ 실적일: {d.get('Next_Earning','N/A')} | 내부자: {d.get('Insider_Buy','N/A')} | 공매도: {d.get('Short_Interest','N/A')}",
            f"└──────────────────────────────────────────────────",
        ]

    lines += [
        "",
        "[분석 요청]",
        "1. RSI 멀티타임프레임과 52주 위치를 종합해 지금 가장 매수 신뢰도 높은 종목은?",
        "2. 공매도 비율과 Beta 기준으로 리스크가 가장 높은/낮은 종목을 구분해줘.",
        "3. 위 데이터를 종합해 지금 시장 상황에 맞는 매매 시나리오를 제안해줘.",
    ]
    st.code("\n".join(lines), language="text")