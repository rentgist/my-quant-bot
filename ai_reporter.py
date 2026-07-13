import os
import json
from datetime import datetime

def generate_smart_control_room_report(market_context: str) -> str:
    """
    Reads data/news_archive.json and asks Gemini to synthesize a market report.
    market_context is a string containing the current algorithm's verdict and scores.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return "🚨 `GEMINI_API_KEY` 환경변수가 설정되지 않아 AI 리포트를 생성할 수 없습니다. `.env` 파일을 확인하세요."
        
    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        
        import requests
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
                news_file = os.path.join("data", "news_archive.json")
            if os.path.exists(news_file):
                try:
                    with open(news_file, "r", encoding="utf-8") as f:
                        news_data = json.load(f)
                except:
                    pass

        news_text = "최근 수집된 뉴스가 없습니다. (백그라운드 뉴스 수집 파이프라인 대기 중)"
        
        if news_data:
            top_news = news_data[:60]
            if top_news:
                news_lines = []
                for n in top_news:
                    title = n.get("title_ko", n.get("title", "제목 없음"))
                    sentiment = n.get("sentiment", "중립")
                    importance = n.get("importance", 0)
                    action = n.get("action_point", "")
                    news_lines.append(f"- [{sentiment}/중요도:{importance}] {title} (대응: {action})")
                news_text = "\n".join(news_lines)
                
        prompt = f"""너는 대한민국 상위 1% 자산가를 위한 월스트리트 최고 수준의 매크로 애널리스트이자 퀀트 트레이더다.
다음 주어진 '알고리즘 시스템의 현재 판독 결과'와 '최근 글로벌 뉴스'를 바탕으로, 대시보드 상황판에 어울리는 브리핑을 Markdown 포맷으로 작성하라.

[알고리즘 시스템 판독 결과]
{market_context}

[최근 글로벌 속보 요약]
{news_text}

[작성 지침]
1. 반드시 아래 3가지 섹션으로 나누어 작성하라 (Markdown Header ### 사용).
   - ### 🌐 현재 시장 국면 요약 (알고리즘 수치와 뉴스를 종합하여 현재 상황을 예리하게 통찰)
   - ### 🔭 72시간 단기 전망 (이러한 뉴스 및 수급 흐름이 자산 가격에 미칠 구체적 영향 분석)
   - ### 🎯 최종 행동 지침 (알고리즘 지침과 뉴스를 결합하여, 유저가 당장 어떻게 자금을 집행해야 할지 명확히 명시)
2. 알고리즘 판독 결과(안전장치)를 **최우선 절대 원칙**으로 삼아라. 
   - 예컨대 알고리즘이 "떨어지는 칼날(매수 보류)" 상태라고 판정했다면, 비록 뉴스에 좋은 소식이 있더라도 매수를 보류하고 리스크를 관리해야 함을 강력히 조언해야 한다. 
   - 모순된 지시(예: 매수 금지인데 낙폭 과대니까 매수해라)를 절대로 내리지 마라.
3. 리포트는 엘리트 트레이더의 톤앤매너로, 매우 확신에 찬 어조(~~하십시오, ~~입니다, ~~해야 합니다)를 사용하라. 애매모호한 표현을 금지한다.
4. 마크다운의 굵은 글씨(** **)와 인용구(>)를 적절히 활용하여 가독성을 극대화하라.
"""

        models_to_try = [
            "gemini-2.0-flash",
            "gemini-1.5-flash",
            "gemini-1.5-flash-latest",
            "gemini-2.0-flash-exp",
            "gemini-2.5-flash"
        ]
        
        response = None
        last_err = None
        successful_model = None
        
        for model_name in models_to_try:
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt
                )
                successful_model = model_name
                break
            except Exception as e:
                last_err = e
                continue
                
        if response:
            return f"*(사용된 AI 모델: {successful_model})*\n\n" + response.text.strip()
        else:
            raise last_err
        
    except Exception as e:
        return f"🚨 AI 리포트 생성 중 API 연동 오류 발생: {e}"
