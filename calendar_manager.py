import os
import pandas as pd
import datetime
import yfinance as yf
import concurrent.futures
import json
import re
from zoneinfo import ZoneInfo

CALENDAR_FILE = "market_calendar.csv"

# 공식 발표 일정으로 확인한 고중요도 거시 이벤트입니다. 뉴스 제목을 파싱해
# 날짜를 추정하지 않고, 일정이 확정된 뒤에만 이 목록을 갱신합니다.
CORE_MACRO_EVENTS_2026 = [
    ("2026-08-12", "물가·금리", "미국 7월 CPI 발표 (21:30 KST)", "High",
     "물가 상회 시 장기금리와 기술주 할인율 부담 확대. 둔화 시 신규진입 여건 개선."),
    ("2026-08-13", "물가·금리", "미국 7월 PPI 발표 (21:30 KST)", "High",
     "기업 비용의 물가 압력을 확인. CPI와 같은 방향이면 금리 반응이 커질 수 있음."),
    ("2026-08-14", "경기·고용", "미국 7월 소매판매 발표 (21:30 KST)", "High",
     "소비·경기 지속성 확인. 고물가와 소비 둔화의 동시 발생은 위험 신호."),
    ("2026-08-14", "경기·고용", "미시간대 8월 소비심리 잠정치 (23:00 KST)", "Medium",
     "기대인플레이션 급등 여부를 점검. 장기금리 민감 구간에서는 중요도가 높아짐."),
    ("2026-08-19", "연준", "7월 FOMC 의사록 공개 (03:00 KST, 8/20)", "High",
     "연준 내부의 물가·유동성 인식 확인. 매파적이면 기술주 비중 확대를 보류."),
    ("2026-08-26", "물가·금리", "미국 7월 PCE·개인소득 발표 (21:30 KST)", "High",
     "연준 선호 물가 지표. 핵심 PCE의 방향이 금리 경로 판단에 직접 연결됨."),
    ("2026-08-26", "경기·고용", "미국 2분기 GDP 수정치 발표 (21:30 KST)", "High",
     "성장과 물가를 함께 해석. 성장 둔화와 물가 재상승 조합은 가장 불리."),
    ("2026-08-27", "연준", "잭슨홀 경제정책 심포지엄 시작", "High",
     "8/27~29 연준 인사 발언에 따른 장기금리 변동성 경계. 갭 상승 추격 금지."),
    ("2026-09-04", "경기·고용", "미국 8월 고용보고서 발표 (21:30 KST)", "High",
     "고용·임금이 9월 연준 판단에 미치는 핵심 입력값."),
    ("2026-09-11", "물가·금리", "미국 8월 CPI 발표 (21:30 KST)", "High",
     "9월 FOMC 직전의 핵심 물가 확인. 예상치 대비 방향을 우선 해석."),
    ("2026-09-15", "연준", "9월 FOMC 회의 시작", "High",
     "9/15~16 회의 및 점도표. 정책금리·유동성 경로 재평가 구간."),
]

# 조회 시 합치는 공식 일정입니다. CSV 수동 입력은 조회만으로 변경하지 않습니다.
OFFICIAL_VERIFIED_AT = "2026-10-20"
OFFICIAL_COVERAGE_END = datetime.date(2026, 12, 31)
CALENDAR_COLUMNS = ["Date", "Type", "Event", "Impact", "Notes"]
BOK_SCHEDULE = "https://www.bok.or.kr/portal/singl/crncyPolicyDrcMtg/listYear.do?menuNo=200755&mtgSe=A"
FED_SCHEDULE = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
BEA_SCHEDULE = "https://www.bea.gov/news/schedule/full"
BLS_NOVEMBER = "https://www.bls.gov/schedule/2026/11_sched_list.htm"
BLS_DECEMBER = "https://www.bls.gov/schedule/2026/12_sched_list.htm"


def _official(date, kind, event, source, detail=""):
    return (date, kind, event, "High",
            f"[공식 확인] 확인일 {OFFICIAL_VERIFIED_AT}; 날짜 KST; {detail} 출처: {source}")


VERIFIED_EVENTS = [
    _official("2026-10-22", "국내", "한국은행 통화정책방향 결정회의", BOK_SCHEDULE),
    _official("2026-10-27", "연준", "10월 FOMC 회의 시작 (미국 현지 10/27~28)", FED_SCHEDULE,
              "회의 시작일 표기; 정책결정은 한국 10/29 새벽."),
    _official("2026-10-29", "연준", "10월 FOMC 정책결정 (미국 현지 10/28)", FED_SCHEDULE),
    _official("2026-10-29", "경기·고용", "미국 3분기 GDP 속보치 (21:30 KST)", BEA_SCHEDULE),
    _official("2026-10-29", "물가·금리", "미국 9월 PCE·개인소득 (21:30 KST)", BEA_SCHEDULE),
    _official("2026-10-29", "실적", "GOOGL 3분기 실적 (미국 10/28 장후)",
              "https://abc.xyz/investor/news/news-details/2026/Alphabet-Announces-Date-of-Third-Quarter-2026-Financial-Results-Conference-Call-2026-8tpGZsLS6v/default.aspx",
              "실적 공개 후 콘퍼런스콜 05:30 KST; 발표 시각과 콜 시각은 다름."),
    _official("2026-10-29", "실적", "MSFT FY2027 1분기 실적 (미국 10/28 장후)",
              "https://www.microsoft.com/en-us/investor/faq",
              "정확한 실적 공개 시각은 IR 재확인."),
    _official("2026-11-06", "경기·고용", "미국 10월 고용보고서 (22:30 KST)", BLS_NOVEMBER),
    _official("2026-11-10", "물가·금리", "미국 10월 CPI (22:30 KST)", BLS_NOVEMBER),
    _official("2026-11-13", "물가·금리", "미국 10월 PPI (22:30 KST)", BLS_NOVEMBER),
    _official("2026-11-25", "경기·고용", "미국 3분기 GDP 수정치 (22:30 KST)", BEA_SCHEDULE),
    _official("2026-11-25", "물가·금리", "미국 10월 PCE·개인소득 (22:30 KST)", BEA_SCHEDULE),
    _official("2026-11-26", "국내", "한국은행 통화정책방향 결정회의", BOK_SCHEDULE),
    _official("2026-12-04", "경기·고용", "미국 11월 고용보고서 (22:30 KST)", BLS_DECEMBER),
    _official("2026-12-08", "연준", "12월 FOMC 회의 시작 (미국 현지 12/8~9)", FED_SCHEDULE,
              "회의 시작일 표기; 정책결정은 한국 12/10 새벽."),
    _official("2026-12-10", "연준", "12월 FOMC 정책결정·경제전망 (미국 현지 12/9)", FED_SCHEDULE),
    _official("2026-12-10", "물가·금리", "미국 11월 CPI (22:30 KST)", BLS_DECEMBER),
    _official("2026-12-15", "물가·금리", "미국 11월 PPI (22:30 KST)", BLS_DECEMBER),
    _official("2026-12-23", "경기·고용", "미국 3분기 GDP 확정치 (22:30 KST)", BEA_SCHEDULE),
    _official("2026-12-23", "물가·금리", "미국 11월 PCE·개인소득 (22:30 KST)", BEA_SCHEDULE),
]


def calendar_today():
    return datetime.datetime.now(ZoneInfo("Asia/Seoul")).date()


def calendar_coverage_message(today=None):
    today = today or calendar_today()
    stale = today - datetime.date.fromisoformat(OFFICIAL_VERIFIED_AT) > datetime.timedelta(days=30)
    prefix = "⚠️ 일정 재확인 필요 · " if stale or today + datetime.timedelta(days=14) > OFFICIAL_COVERAGE_END else ""
    return (f"{prefix}공식 일정 확인일 {OFFICIAL_VERIFIED_AT} · 수록 범위 {OFFICIAL_COVERAGE_END}까지 · "
            "모든 기업·경제 일정을 포함한 목록은 아닙니다. 일정 변경·추가 여부는 공식 출처 재확인.")


def load_effective_calendar():
    """표와 프롬프트가 공유하는 읽기 전용 병합. 사용자 CSV는 보존한다."""
    df = load_calendar()
    official = pd.DataFrame(VERIFIED_EVENTS, columns=CALENDAR_COLUMNS)
    official["Date"] = pd.to_datetime(official["Date"]).dt.date
    # 같은 분기의 옛 Yahoo 예상 날짜가 공식 KST 일정과 함께 노출되지 않게 한다.
    # 저장된 사용자 파일·수동 메모·다른 분기 이력은 변경하지 않는다.
    automatic = df["Notes"].fillna("").str.startswith(("자동 업데이트됨", "[예상·미확인]"))
    superseded = []
    official_earnings = official[official["Type"].eq("실적")]
    for _, row in df.iterrows():
        name = str(row["Event"]).removesuffix(" 실적발표")
        superseded.append(any(
            event["Event"].startswith(name + " ")
            and pd.notna(row["Date"])
            and abs((event["Date"] - row["Date"]).days) <= 14
            for _, event in official_earnings.iterrows()
        ))
    df = df[~(automatic & pd.Series(superseded, index=df.index, dtype=bool))].copy()
    # 동일 날짜·이벤트의 수동 행은 유지하고, 서로 다른 설명은 출처와 함께 보여준다.
    keys = set(zip(df["Date"], df["Event"]))
    extra = official[[key not in keys for key in zip(official["Date"], official["Event"])]]
    return pd.concat([df, extra], ignore_index=True).sort_values("Date", na_position="last").reset_index(drop=True)


# 대표 글로벌/국내 빅테크 티커
MAJOR_TICKERS = {
    "ASML": "ASML",
    "NVDA": "NVDA",
    "MSFT": "MSFT",
    "AAPL": "AAPL",
    "META": "META",
    "GOOGL": "GOOGL",
    "AVGO": "AVGO",
    "VRT": "VRT",
    "MRVL": "MRVL",
    "TSMC": "TSM",
    "삼성전자": "005930.KS",
    "SK하이닉스": "000660.KS"
}

def load_calendar():
    if not os.path.exists(CALENDAR_FILE):
        df = pd.DataFrame(columns=["Date", "Type", "Event", "Impact", "Notes"])
        return df
    
    df = pd.read_csv(CALENDAR_FILE, encoding="utf-8-sig")
    # [BUG FIX] Convert 'Date' string to datetime.date to prevent StreamlitAPIException
    if "Date" not in df.columns or not set(CALENDAR_COLUMNS).issubset(df.columns):
        raise ValueError("캘린더 필수 열이 누락되었습니다. 원본을 확인하세요.")
    if not df.empty and 'Date' in df.columns:
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce').dt.date
        df = df.sort_values(by="Date", na_position="last").reset_index(drop=True)
    return df

def save_calendar(df):
    # Ensure dates are strings for saving
    df_save = df.copy()
    if not df_save.empty and 'Date' in df_save.columns:
        df_save['Date'] = pd.to_datetime(df_save['Date']).dt.strftime('%Y-%m-%d')
    df_save.to_csv(CALENDAR_FILE, index=False, encoding="utf-8-sig")


def sync_core_macro_events():
    """확정된 핵심 거시 일정만 추가·갱신한다.

    수동 입력과 기존 설명을 보존하며, 누락된 날짜·이벤트 조합만 추가한다.
    """
    df = load_calendar()
    core_df = pd.DataFrame(
        CORE_MACRO_EVENTS_2026 + VERIFIED_EVENTS,
        columns=["Date", "Type", "Event", "Impact", "Notes"],
    )
    core_df["Date"] = pd.to_datetime(core_df["Date"]).dt.date

    keys = set(zip(df["Date"], df["Event"]))
    missing = core_df[[key not in keys for key in zip(core_df["Date"], core_df["Event"])]]
    merged = pd.concat([df, missing], ignore_index=True)

    merged = merged.sort_values(by=["Date", "Impact", "Event"]).reset_index(drop=True)
    save_calendar(merged)
    return len(core_df)

def fetch_single_earnings(name, ticker):
    try:
        cal = yf.Ticker(ticker).calendar
        dates = cal.get("Earnings Date", []) if isinstance(cal, dict) else []
        dates = sorted(set(pd.Timestamp(value).date() for value in dates if not pd.isna(value)))
        dates = [day for day in dates if day >= calendar_today() - datetime.timedelta(days=2)]
        if not dates:
            return None
        date_window = " ~ ".join(day.isoformat() for day in (dates[:1] if len(dates) == 1 else [dates[0], dates[-1]]))
        return {"Date": dates[0].isoformat(), "Type": "실적", "Event": f"{name} 실적발표",
                "Impact": "High", "Notes": (
                    f"[예상·미확인] Yahoo 날짜/범위 {date_window}; 날짜의 시간대와 KST 일자는 IR 재확인. "
                    f"조회일 {calendar_today()}; 출처: https://finance.yahoo.com/quote/{ticker}/calendar/"
                )}
    except Exception:
        return None


def update_earnings_automatically():
    df = load_calendar()
    new_events = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(fetch_single_earnings, name, ticker): name for name, ticker in MAJOR_TICKERS.items()}
        for future in concurrent.futures.as_completed(futures):
            res = future.result()
            if res:
                res = dict(res)
                res["Date"] = pd.Timestamp(res["Date"]).date()
                new_events.append(res)
    if not new_events:
        return False

    for row in new_events:
        name = row["Event"].removesuffix(" 실적발표")
        verified = list(VERIFIED_EVENTS) + list(df.itertuples(index=False, name=None))
        if any(
            str(event[2]).startswith(name + " ")
            and str(event[4]).startswith("[공식 확인]")
            and abs((pd.Timestamp(event[0]).date() - row["Date"]).days) <= 14
            for event in verified
        ):
            continue
        # 실패한 다른 티커의 기존 행·과거 이력·수동 입력·공식 확인 행은 그대로 둔다.
        same = df["Event"].eq(row["Event"])
        automatic = df["Notes"].fillna("").str.startswith(("자동 업데이트됨", "[예상·미확인]"))
        future_row = df["Date"] >= calendar_today() - datetime.timedelta(days=2)
        df = df[~(same & automatic & future_row)]
        duplicate = ((df["Date"] == row["Date"]) & df["Event"].eq(row["Event"])).any()
        if not duplicate:
            df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    save_calendar(df.sort_values("Date").reset_index(drop=True))
    return True


def update_macro_events_automatically():
    news_file = os.path.join("data", "news_archive.json")
    if not os.path.exists(news_file):
        return False
        
    try:
        with open(news_file, "r", encoding="utf-8") as f:
            news_data = json.load(f)
    except Exception:
        return False
        
    keywords = ["FOMC", "금통위", "금리 결정", "금리결정", "리밸런싱", "CPI", "PCE"]
    new_events = []
    today = calendar_today()
    for item in news_data:
        title = item.get("title_ko", item.get("title", ""))
        matched_kw = next((kw for kw in keywords if kw.upper() in title.upper()), None)
        # 연·월·일이 없는 제목에서 날짜를 추측하지 않는다. 명시된 날짜도 확인 후보다.
        match = re.search(r"(20\d{2})년\s*(\d{1,2})월\s*(\d{1,2})일", title)
        if not matched_kw or not match:
            continue
        try:
            event_date = datetime.date(*(int(part) for part in match.groups()))
        except ValueError:
            continue
        if not today <= event_date <= today + datetime.timedelta(days=90):
            continue
        new_events.append({
            "Date": event_date, "Type": "매크로", "Event": f"{matched_kw} 확인 후보: {title}",
            "Impact": "High", "Notes": "[뉴스 후보·미확인] 제목 날짜이며 공식 발표일·시간대 재확인 필요. " + str(item.get("url", "")),
        })

    if not new_events:
        return False
        
    # Dedup
    df_new = pd.DataFrame(new_events)
    df_new = df_new.drop_duplicates(subset=["Date", "Event"])
    
    df = load_calendar()
    if not df.empty:
        # Avoid exact duplicates
        for _, row in df_new.iterrows():
            if not ((df['Date'] == row['Date']) & (df['Event'] == row['Event'])).any():
                df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    else:
        df = df_new
        
    df = df.sort_values(by="Date").reset_index(drop=True)
    save_calendar(df)
    return True

def get_upcoming_events_string():
    try:
        df = load_effective_calendar()
        today = calendar_today()
        start_date = today - datetime.timedelta(days=2)
        end_date = today + datetime.timedelta(days=14)
        mask = (df["Date"] >= start_date) & (df["Date"] <= end_date)
        upcoming = df[mask].sort_values("Date")
        coverage = calendar_coverage_message(today)
        if upcoming.empty:
            return (f"[일정 확인 필요] 최근 2일~향후 14일 범위에 등록된 일정이 없습니다. "
                    f"실제 주요 일정이 없다는 뜻이 아닙니다. {coverage}")
        lines = ["[최근 2일·향후 14일 마켓 일정 · 공식 행 KST / 미확인 행은 원문 날짜]", coverage]
        for _, row in upcoming.iterrows():
            notes = "" if pd.isna(row["Notes"]) else str(row["Notes"])
            status = "공식 확인" if notes.startswith("[공식 확인]") else "예상·미확인" if notes.startswith("[예상·미확인]") else "확인 필요"
            date_label = "원문 날짜·KST 미확인" if status == "예상·미확인" else "KST" if status == "공식 확인" else "시간대 미확인"
            lines.append(f"- {row['Date']:%Y-%m-%d} ({date_label}) [{row['Type']} / {status}] {row['Event']} : {notes}")
        return "\n".join(lines)
    except Exception:
        return "[일정 확인 실패] 저장된 일정 데이터를 읽지 못했습니다. 이벤트가 없다고 판단하지 말고 공식 발표 일정을 확인하세요."
