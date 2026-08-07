import os

with open('signals.py', 'r', encoding='utf-8') as f:
    content = f.read()

new_func = '''
def generate_us_economic_commentary(summary_dict, phase):
    import os
    
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return "⚠️ 환경 변수에 GEMINI_API_KEY가 설정되지 않아 AI 브리핑을 제공할 수 없습니다."
    
    prompt = f\"\"\"너는 월스트리트 출신의 매크로 전략가이자 퀀트 펀드 매니저다.
아래 전달받은 미국 증시 핵심 데이터와 시스템이 판정한 시장 국면을 바탕으로 가장 날카롭고 입체적인 브리핑을 작성하라.
단순히 숫자를 나열하지 말고, [매크로/유동성의 구조적 변화 ➔ 미국 증시 반영 여부 ➔ 섹터 수급(SPY, QQQ, SOXX) 괴리 포착 ➔ 유리한 섹터/테마 암시 ➔ 최종 행동 강령] 순으로 인과관계에 맞게 해설해라.

[미국 매크로 및 유동성 핵심 지표]
    - 미국 10년물 국채 금리: {summary_dict.get('TNX_10Y', 'N/A')}
    - 달러 인덱스 (DXY): {summary_dict.get('DXY', 'N/A')}
    - 하이일드 스프레드: {summary_dict.get('HY_Spread', 'N/A')}
    - 연준 순유동성: {summary_dict.get('Net_Liquidity', 'N/A')}
    - VIX 공포지수: {summary_dict.get('VIX', 'N/A')}

[미국 주요 ETF 당일 수급 프록시 강도 (양수=매수우위, 음수=매도우위)]
    - SPY (S&P 500): {summary_dict.get('SPY_Flow', 'N/A')}
    - QQQ (나스닥): {summary_dict.get('QQQ_Flow', 'N/A')}
    - SOXX (반도체): {summary_dict.get('SOXX_Flow', 'N/A')}

[시스템 판정 국면]
    - 현재 국면: {phase}

출력 형식은 마크다운을 사용하며, 너무 길지 않게 핵심만 3~4개의 글머리 기호(Bullet point)로 나누어 전달하라. 마지막엔 한 줄 요약(Action Point)을 덧붙여라.
\"\"\"
    
    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.5-flash")
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"⚠️ 브리핑 생성 중 오류가 발생했습니다: {e}"
'''

if 'def generate_us_economic_commentary' not in content:
    with open('signals.py', 'a', encoding='utf-8') as f:
        f.write('\n\n' + new_func + '\n')
    print("Added generate_us_economic_commentary")
else:
    print("Already exists")
