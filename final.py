import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import datetime
import FinanceDataReader as fdr
import requests

st.set_page_config(page_title="11원칙 퀀트 대시보드 v18.9", page_icon="🧭", layout="wide")

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
# 매크로 차트 데이터 수집 (🔥 NameError 수정: 누락되었던 함수 복구)
# ─────────────────────────────────────────
@st.cache_data(ttl=3600)
def get_macro_charts():
    result = {}
    try:
        result["vix_5y"]  = yf.Ticker("^VIX").history(period="5y")
    except:
        result["vix_5y"]  = pd.DataFrame()
    try:
        result["spy_5y"]  = yf.Ticker("SPY").history(period="5y")
    except:
        result["spy_5y"]  = pd.DataFrame()
    return result

# ─────────────────────────────────────────
# RSI & MACD
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
# 섹터 ETF 기준선 & 상대강도
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
    is_high_short = s_pct >= 5.0 
    is_high_beta = beta_val >= 1.2 
    
    if not is_high_short and not is_high_beta:
        return "🟢 안정형 — 방어적 투자에 적합"
    elif not is_high_short and is_high_beta:
        return "🟡 모멘텀형 — 상승장에 강하지만 하락 시 크게 빠짐"
    elif is_high_short and not is_high_beta:
        return "🟠 논란형 — 시장은 의심하지만 변동성은 낮음, 이유 확인 필요"
    else:
        return "🔴 고위험 — 하락 베팅 + 큰 변동성, 진입 신중"

# ─────────────────────────────────────────
# 내부자 거래 — 직급 파싱 + SEC EDGAR 링크 생성
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
# 시그널 로직 (포트폴리오 장투용)
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

# 🔥 [완전 개편 완료] 텐배거 알고리즘 (미래 선행지표/모멘텀 기준 적용 및 대형주 숨김)
def get_tenbagger_signal(d):
    mcap     = float(d.get('MarketCap') or 0)
    region   = d.get('Region')
    rev_g    = float(d.get('Rev_Growth') or 0)
    earn_g   = float(d.get('Earnings_Growth') or 0) # 미래 예상 이익성장률
    peg      = float(d.get('PEG')        or 99)
    gap_high = float(d.get('Gap_High')   or 0)
    is_turnaround = d.get("Is_Turnaround", False)

    # 1. 시총 필터 (UI 노이즈 제거: 대형주면 아예 '-' 반환하여 레이더 테이블에서 숨김)
    if region == "미국" and mcap >= 100_000_000_000:   return "-"
    if region == "한국" and mcap >= 10_000_000_000_000: return "-"

    # 2. [하드 필터] 매출 20% 이상 성장 못하면 탈락
    if rev_g < 0.20: 
        return "-"
        
    # 3. [하드 필터] 역추세/지하실 주식 절대 배제 (Minervini 룰: 고점대비 -35% 초과 하락시 무조건 탈락)
    if gap_high < -35.0: 
        return "-" 

    # 4. 미래 성장성 기반 종합 평점 (최대 3점)
    points = 0
    # ① 매출 폭발력 (30% 이상 성장 시 가산점)
    if rev_g >= 0.30: points += 1   
    
    # ② 미래 이익 폭발력 (예상 이익성장률 30% 이상 OR 흑자전환 시 가산점)
    if earn_g >= 0.30 or is_turnaround: points += 1    
    
    # ③ 가치 평가 (미래 성장 대비 PEG 1.5 이하 시 가산점)
    if 0 < peg <= 1.5: points += 1  
    
    if points >= 3: return "🔥 기관 최선호 대장주"
    if points == 2: return "🌱 우량 고성장주"
    return "-"

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

        # 🔥 흑자 전환(Turnaround) 로직 점검
        t_eps = info.get('trailingEps')
        f_eps = info.get('forwardEps')
        is_turnaround = False
        if t_eps is not None and f_eps is not None:
            if float(t_eps) <= 0 and float(f_eps) > 0:
                is_turnaround = True
        base["Is_Turnaround"] = is_turnaround

        # 🔥 Forward(선행) 지표 추가
        base.update({
            "MarketCap":       info.get('marketCap', 0),
            "PER":             info.get('trailingPE'),
            "Forward_PER":     info.get('forwardPE'),
            "Forward_EPS":     f_eps,
            "Earnings_Growth": info.get('earningsGrowth'),
            "PBR":             info.get('priceToBook'),
            "ROE":             info.get('returnOnEquity'),
            "Op_Margin":       info.get('operatingMargins'),
            "PEG":             info.get('pegRatio'),
            "Rev_Growth":      info.get('revenueGrowth'),
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

            # 종합 리스크 등급 생성
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
# 포맷 및 색상 맵핑 (pfx 에러 영구 해결본)
# ─────────────────────────────────────────
def fmt_mcap(mcap, region):
    if not mcap or mcap == 0: return "N/A"
    return f"${mcap/1e9:.1f}B" if region == "미국" else (
        f"{mcap/1e12:.2f}조 원" if mcap >= 1e12 else f"{mcap/1e8:.0f}억 원"
    )

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
st.title("🧭 11원칙 퀀트 트레이딩 대시보드 v18.9")
st.caption("v18.9: 매크로 함수 NameError 완벽 복구 / 기능 누락 일절 없는 진짜 최종 무결성 코드")

cnn_score, cnn_rating, cnn_history = get_real_cnn_fg()
sector_base = get_sector_baseline()
spy_rsi_val = sector_base.get("S&P 500 (SPY)")

macro_charts = get_macro_charts()
usd_krw      = get_stock_data("KRW=X")

# 🔥 사용자 요청 탭 순서
tab1, tab2, tab4, tab3, tab_port, tab5, tab_risk = st.tabs([
    "📊 실시간 포트폴리오",
    "🌐 매크로 & F&G Index",
    "🚀 오늘의 텐배거 레이더",
    "🤖 AI 참모 리포트",
    "💼 내 포트폴리오 장투 전략",
    "📖 11원칙 매매 가이드라인",
    "🚨 리스크 등급 가이드",
])

with tab_port:
    st.subheader("💼 내 포트폴리오 장투 전략 분석 (1~2년 기준)")
    st.caption("보유 종목과 매수가를 입력하면 현재 손익 현황 + 11원칙 종합평가 + AI 전달용 장투 전략 리포트를 생성합니다.")

    st.markdown("#### 📝 보유 종목 입력")
    st.info(
        "**입력 형식:** 종목명:매수가 (쉼표로 구분)\n\n"
        "🇺🇸 미국: `브로드컴:320.5, 버티브:250, TSMC:180`\n\n"
        "🇰🇷 한국: `LS ELECTRIC:185000, 삼성전자:72000`"
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
            with st.spinner("보유 종목 데이터 수집 중..."):
                for name, buy_price, region in port_items:
                    d = get_stock_data(name, is_kr=(region == "한국"))
                    d["Region"]    = region
                    d["BuyPrice"]  = buy_price
                    if not d.get("error"):
                        port_data.append(d)
                    else:
                        st.warning(f"⚠️ '{name}' 데이터 조회 실패: {d.get('error')}")

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
                        f"  - 매출성장: {pct(d.get('Rev_Growth'))} | 영업이익률: {pct(d.get('Op_Margin'))} | ROE: {pct(d.get('ROE'))}",
                        f"  - PER: {fmt(d.get('PER'),dig=1)} | Fwd PER: {fmt(d.get('Forward_PER'),dig=1)} | PEG: {fmt(d.get('PEG'),dig=2)} | PBR: {fmt(d.get('PBR'),dig=2)}",
                        f"  - RSI(14일): {fmt(rsi14,dig=1)} | 52주 위치: {w52}% | 매매시그널: {ai_sig}",
                        f"  - 종합리스크: {risk_g}",
                        f"  - 내부자: {d.get('Insider_Buy','N/A')} | 공매도: {d.get('Short_Interest','N/A')} | Beta: {d.get('Beta','N/A')}",
                        f"  - 어닝: {d.get('Earnings_Beat','N/A')} | 다음실적일: {d.get('Next_Earning','N/A')}",
                        f"  - 최신뉴스: {str(d.get('Latest_News','N/A'))[:80]}",
                    ]

                port_lines += [
                    "",
                    "【장투 전략 분석 요청】",
                    "위 보유 종목들에 대해 1~2년 장기투자 관점으로 다음을 분석해줘:",
                    "",
                    "1. 각 종목의 펀더멘탈(매출성장, 영업이익률, ROE, PEG)을 평가하고 장기 보유 가치가 있는지 판단해줘.",
                    "2. 현재 수익/손실 종목별로 추가 매수(물타기/불타기), 홀딩, 익절, 손절 중 어떤 전략이 적합한지 근거와 함께 알려줘.",
                    "3. 포트폴리오 전체의 섹터 쏠림이나 리스크 집중도를 평가하고 분산 관점에서 개선 방향을 제안해줘.",
                    "4. 현재 시장(F&G, SPY RSI) 상황을 고려해서 지금 시점에 가장 먼저 행동해야 할 종목과 이유를 1~2개 꼽아줘.",
                ]

                st.code("\n".join(port_lines), language="text")

with tab5:
    st.header("📖 11원칙 퀀트 매매 가이드라인 (오리지널 철학)")
    st.markdown("""
이 대시보드는 사용자님의 정통 가치투자 철학(위기 줍줍, 턴어라운드)과 기계적인 퀀트 필터링을 결합한 하이브리드 시스템입니다.

**[ 펀더멘탈: 실적과 턴어라운드 ]**
- **1원칙 (3개년 우상향):** 매출 and 영업이익 지속 상승.
- **2원칙 (시가총액 비교):** 시장/섹터 대비 시총 규모가 적정하게 낮을 것.
- **3원칙 (턴어라운드 기대):** 현재 마진이 낮아도 미래 개선이 뚜렷하면 투자 가능.
- **4원칙 (비즈니스 모델):** 단독 매출인지, 연결/종속 업체인지 파악하고 시장 점유율 이해.

**[ 투자 시계열과 위기 관리 ]**
- **5원칙 (3년 장기 투자):** 수확은 3년 뒤. 일부만 현금화하여 재투자 비율 스스로 설정.
- **6원칙 (글로벌 위기 줍줍):** 시장이 붕괴되어 고점 대비 20~30% 하락 시 분할 매수, 50% 밑이면 과감히 매수.
- **7원칙 (하락장 리밸런싱):** 시장 전체가 하락할 때 기존 비중 조절 및 신규 종목 편입.

**[ 퀀트 기술적 타점 보완 ]**
- **8원칙 (RSI 과매도):** RSI 45 미만 바닥 할인 / 75 이상 과매수 익절.
- **9원칙 (추세 지지):** 20일선 지지 기준, 급등주 추격 금지.
- **10원칙 (거래량):** 거래량 폭발 + MACD 상승 시 세력 편승.
- **11원칙 (스마트머니):** 내부자 순매수 및 공매도/Beta를 파악해 투매와 매집을 구분할 것.
    """)

with tab_risk:
    st.header("🚨 공매도 & 변동성(Beta) 종합 리스크 가이드")
    st.markdown("""
    | 공매도 비율 | Beta (변동성) | 종합 리스크 등급 및 해석 |
    | :--- | :--- | :--- |
    | 낮음 (5% 미만) | 낮음 (1.2 미만) | **🟢 안정형 — 방어적 투자에 적합** |
    | 낮음 (5% 미만) | 높음 (1.2 이상) | **🟡 모멘텀형 — 상승장에 강하지만 하락 시 크게 빠짐** |
    | 높음 (5% 이상) | 낮음 (1.2 미만) | **🟠 논란형 — 시장은 의심하지만 변동성은 낮음, 이유 확인 필요** |
    | 높음 (5% 이상) | 높음 (1.2 이상) | **🔴 고위험 — 하락 베팅 + 큰 변동성, 진입 신중** |
    """)

with tab2:
    st.subheader("🌐 글로벌 매크로 및 시장 심리")

    vix_5y = macro_charts.get("vix_5y", pd.DataFrame())
    spy_5y = macro_charts.get("spy_5y", pd.DataFrame())

    current_vix, vix_change = "N/A", 0
    if not vix_5y.empty:
        current_vix = round(float(vix_5y['Close'].iloc[-1]), 2)
        vix_change  = round(((current_vix - float(vix_5y['Close'].iloc[-2])) /
                              float(vix_5y['Close'].iloc[-2])) * 100, 2)

    current_spy, spy_change = "N/A", 0
    if not spy_5y.empty:
        current_spy = round(float(spy_5y['Close'].iloc[-1]), 2)
        spy_change  = round(((current_spy - float(spy_5y['Close'].iloc[-2])) /
                              float(spy_5y['Close'].iloc[-2])) * 100, 2)

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("환율 (USD/KRW)",
                fmt_price(usd_krw.get('Price'), "한국").replace("원", " 원"),
                fmt_change(usd_krw.get('Change')))
    col2.metric("미국 VIX", current_vix, f"{vix_change}%", delta_color="inverse")
    col3.metric("S&P 500 (SPY)", f"${current_spy:,.2f}" if current_spy != "N/A" else "N/A",
                f"{spy_change:+.2f}%" if current_spy != "N/A" else "N/A")
    if cnn_score is not None:
        if cnn_score <= 25:   fg_color, fg_stat = "🔴", "극단적 공포"
        elif cnn_score <= 45: fg_color, fg_stat = "🟠", "공포"
        elif cnn_score <= 55: fg_color, fg_stat = "🟡", "중립"
        elif cnn_score <= 75: fg_color, fg_stat = "🟢", "탐욕"
        else:                 fg_color, fg_stat = "🟢", "극단적 탐욕"
        col4.metric("CNN Fear & Greed", f"{cnn_score} / 100", f"{fg_color} {fg_stat}")
    else:
        col4.metric("CNN Fear & Greed", "N/A", cnn_rating)

    st.divider()
    st.markdown("#### 🧭 섹터 ETF 기준선 (RSI 14일) — 시장대비 강도 비교 기준값")
    m1, m2, m3 = st.columns(3)
    m1.metric("S&P 500 (SPY)", fmt(spy_rsi_val, dig=1))
    m2.metric("미국 반도체 (SOXX)", fmt(sector_base.get("반도체 (SOXX)"), dig=1))
    m3.metric("미국 유틸리티 (XLU)", fmt(sector_base.get("유틸리티 (XLU)"), dig=1))
    st.caption("💡 **시장대비 강도** = 내 종목 RSI(14일) − SPY RSI(14일). 양수면 시장보다 강한 것, 음수면 시장보다 약한 것. 단, 둘 다 65↑(과매수) 또는 둘 다 35↓(과매도)면 '동반' 상태로 별도 표시.")

    st.divider()

    st.markdown("#### 📊 시장 심리 & 지수 — 최근 5년 추이")
    c_chart1, c_chart2 = st.columns(2)
    with c_chart1:
        st.markdown("**① VIX (공포 지수) — 5년**")
        if not vix_5y.empty:
            st.line_chart(
                pd.DataFrame({
                    "VIX": vix_5y['Close'],
                    "🔴 위험선(30)": 30.0,
                    "🟢 평온선(15)": 15.0,
                }),
                height=280,
                color=["#1f77b4", "#ff4b4b", "#21c354"]
            )
            st.caption("VIX 30↑ = 시장 극도 공포. VIX 15↓ = 과도한 안심 (역발상 주의 구간).")
        else:
            st.warning("VIX 데이터를 불러오지 못했습니다.")
            
    with c_chart2:
        st.markdown("**② S&P 500 (SPY) — 5년**")
        if not spy_5y.empty:
            st.line_chart(
                pd.DataFrame({"S&P 500 (SPY)": spy_5y['Close']}),
                height=280,
                color=["#ff7f0e"]
            )
            spy_high = round(float(spy_5y['Close'].max()), 2)
            spy_low  = round(float(spy_5y['Close'].min()), 2)
            spy_pos  = round((current_spy - spy_low) / (spy_high - spy_low) * 100, 1) if current_spy != "N/A" else "N/A"
            st.caption(f"5년 고점 ${spy_high:,.2f} / 저점 ${spy_low:,.2f} | 현재 5년 범위 내 위치: **{spy_pos}%** (0%=5년 최저, 100%=5년 최고)")
        else:
            st.warning("S&P 500 데이터를 불러오지 못했습니다.")

    st.markdown("**③ CNN Fear & Greed Index**")
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
                "매출성장":      pct(d.get("Rev_Growth")),
                "이익성장(예상)": pct(d.get("Earnings_Growth")),
                "영업이익률":    pct(d.get("Op_Margin")),
                "ROE":           pct(d.get("ROE")),
                "PER":           fmt(d.get("PER"), dig=1),
                "Forward PER":   fmt(d.get("Forward_PER"), dig=1),
                "Forward EPS":   fmt(d.get("Forward_EPS"), pfx="$", dig=2) if d["Region"] == "미국" else fmt(d.get("Forward_EPS"), dig=2),
                "PEG":           fmt(d.get("PEG"), dig=2),
            })

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
                            f"**[📄 SEC EDGAR Form 4 원문 보기 →]({block['url']})**\n\n",
                            unsafe_allow_html=True
                        )

        st.markdown("#### 💰 4. 밸류에이션 (미래 선행 지표 포함)")
        st.dataframe(pd.DataFrame(fin_rows).set_index("종목"), use_container_width=True)

with tab4:
    st.subheader("🚀 섹터별 텐배거 마스터 레이더 (미래 지표 및 트렌드 필터)")
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
            else:
                st.warning("⚠️ 현재 조건(지하실 역추세 및 매출성장 20% 미만 기업 강제 퇴출)을 통과한 진성 우량주가 이 섹터에 존재하지 않습니다.")

with tab3:
    st.subheader("🤖 AI 참모 전용 구조화 리포트 v18.9 (듀얼 분석 강화본)")
    st.caption("아래 텍스트를 복사하여 ChatGPT, Claude, Gemini 등에 붙여넣고 심층 분석을 받아보세요.")
    
    now = get_kst_now().strftime('%Y-%m-%d %H:%M:%S KST')
    lines = [
        f"[11원칙 퀀트 분석 리포트 v18.9] ({now})",
        f"- CNN F&G (시장 심리): {cnn_score} ({cnn_rating})",
        f"- SPY RSI(14) (시장 과열도): {fmt(spy_rsi_val, dig=1)}",
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

        # 추가된 펀더멘탈 및 밸류에이션 지표 추출
        rev_g   = pct(d.get('Rev_Growth'))
        op_m    = pct(d.get('Op_Margin'))
        earn_g  = pct(d.get('Earnings_Growth'))
        roe     = pct(d.get('ROE'))
        per     = fmt(d.get('PER'), dig=1)
        fwd_per = fmt(d.get('Forward_PER'), dig=1)
        peg     = fmt(d.get('PEG'), dig=2)

        lines += [
            f"┌─ [{d['Region']}] {d['Name']} (단기 시그널: {ai_sig} / 텐배거 등급: {tb_sig})",
            f"│ 1. 가격 및 타점: 현재가 {fmt_price(d.get('Price'), d['Region'])} | 추천 타점: {target_d} ({fmt_price(target_p, d['Region'])})",
            f"│ 2. 기술적 지표: RSI(7/14/21) {fmt(d.get('RSI_7'),dig=1)} / {fmt(d.get('RSI_14'),dig=1)} / {fmt(d.get('RSI_21'),dig=1)} | 시장대비: {rs_txt}",
            f"│ 3. 추세 및 위치: 52주 위치 {w52_str} | 고점 대비 {fmt(d.get('Gap_High'),'%',dig=1)} 하락",
            f"│ 4. 펀더멘탈(과거vs미래): 매출성장 {rev_g} | 영업이익률 {op_m} | 🎯예상이익 성장률 {earn_g} | ROE {roe}",
            f"│ 5. 밸류에이션: PER {per} | 🎯Forward PER {fwd_per} | 🎯PEG {peg}",
            f"│ 6. 리스크 및 수급: 종합 리스크 {d.get('Risk_Grade', 'N/A')} | 내부자 {d.get('Insider_Buy','N/A')} | 공매도 {d.get('Short_Interest','N/A')} | Beta {d.get('Beta','N/A')}",
            f"└──────────────────────────────────────────────────",
        ]

    lines += [
        "",
        "【AI 참모 심층 분석 요청사항】",
        "위 데이터를 바탕으로 나의 11원칙 퀀트 투자 룰에 맞춰 다음 4가지를 심층 분석해 줘.",
        "",
        "1. [가치와 성장 듀얼 분석 (Turnaround & Bubble Check)]",
        "   - 각 종목의 '과거 영업이익률/PER'과 '미래 예상 이익성장률/Forward PER/PEG'를 교차 비교해 줘.",
        "   - 과거 실적은 부진해도 미래 턴어라운드가 기대되는 종목과, 주가가 많이 올랐어도 실적 팽창 속도가 빨라 PEG가 저평가인 진짜 성장주를 골라내 줘 (가짜 거품 배제).",
        "",
        "2. [리스크 및 수급 점검]",
        "   - 공매도 비율, Beta(변동성), 내부자 매수 여부를 종합하여 숨겨진 하방 리스크가 큰 종목을 경고해 줘.",
        "",
        "3. [기술적 타점 분석]",
        "   - RSI 멀티타임프레임(7/14/21)의 배열과 52주 위치, 시장대비 강도(SPY 대비)를 종합하여 현재 가장 매수 신뢰도가 높은 바닥/눌림목 종목을 선정해 줘.",
        "",
        "4. [최종 매매 시나리오 제안]",
        "   - 현재 CNN F&G 지수와 SPY RSI가 보여주는 시장 심리를 바탕으로, 지금 당장 '적극 매수', '관망(타점 대기)', '비중 축소' 해야 할 종목들을 분류하고 구체적인 액션 플랜을 제시해 줘."
    ]
    st.code("\n".join(lines), language="text")