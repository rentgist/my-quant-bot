import re

with open(r'C:\Users\로컬\Desktop\my-quant-bot\signals.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Define the new get_strategic_advice function
new_func = '''def get_strategic_advice(danger_count, bottom_score, bottom_verdict, regime="", recovery_score=None):
    """
    반환: (headline, color, actions[])
    v25 기준 일관성 반영 (평소 30~40%, 패닉 10%, 추세전환 20~30%)
    """
    actions = []
    is_knife = "칼날" in bottom_verdict
    is_top   = "고점" in bottom_verdict

    # 1순위: 떨어지는 칼날 (매수 보류)
    if is_knife:
        headline = "⚠️ 매수 보류 — 떨어지는 칼날 구간"
        color = "#ff9900"
        actions = [
            "지금은 '낙폭'이 아니라 '속도'가 문제입니다. 급락 진행 중 진입은 평균단가만 훼손합니다.",
            "매수 재개 조건: 일봉·주봉 마감 후 5일선 회복 여부를 확인하거나, 하락이 멈춘 다음 거래일에 진입.",
            "평소 유지하던 30~40% 코어 예산은 홀딩하되, 추가 스나이퍼 예산 투입은 보류하세요.",
        ]

    # 2순위: 고점권 (바닥 점수 무의미)
    elif is_top:
        if danger_count >= 5:
            headline = "🚨 고점권 + 위험 경보 다발 — 하락 '초입' 최악 조합"
            color = "#ff4b4b"
            actions = [
                "가장 위험한 조합입니다. 경보가 켜졌는데 낙폭이 아직 적음 = 빠질 공간이 크게 남아있는 하락 초입.",
                "신규 매수 전면 중단. 반등이 나오면 '탈출 기회'로 보고 코어 예산 비중을 줄이세요 (7원칙 리밸런싱).",
            ]
        elif danger_count >= 3:
            headline = "⚠️ 고점권 + 이상 징후 — 신규 진입 자제, 현금 확보 시작"
            color = "#ff9900"
            actions = [
                "지수는 고점권인데 위험 탐지기에 경고가 들어왔습니다. 추격 매수의 기댓값이 가장 낮은 구간입니다.",
                "수익 중인 종목 일부 익절로 현금을 추가 확보하세요. 신규는 '20일선 눌림목 확인' 조건부로만.",
            ]
        else:
            headline = "🟢 일상 상승 추세 — 지수 레벨 부담 없음, 기계적 적립"
            color = "#21c354"
            actions = [
                "[Tier 1 구간] 시장에 큰 패닉 없는 안정 구간입니다.",
                "총 예산의 30~40% 코어 자산을 기계적으로 분할 매수 및 유지하세요.",
                "미국 빅테크 우량주가 RSI 40 이하 또는 볼린저 밴드 하단 터치 시 GTC 예약 주문을 걸어두세요.",
            ]

    # 3순위: 극단 패닉 (바닥 점수 80+) -> Tier 3
    elif bottom_score >= 80:
        headline = "🔥 강력 매수 (Tier 3) — 극단적 패닉장 1차 선발대"
        color = "#e94560"
        actions = [
            "바닥 탐지 점수가 80점 이상인 극단적 패닉장입니다.",
            "기술적 지표가 무너져 있어도, 우량주에 [스나이퍼 예산의 10%]를 1차 선발대로 투입할 수 있습니다.",
            "오직 재무 퀄리티(FCF Yield, PEG 등)가 검증된 1등 우량주만 타겟으로 하세요.",
            "단, 오전 갭상승 속임수를 피해 반드시 오후 3시 종가 무렵에 집행하세요.",
        ]
        
    # 4순위: 추세 전환 및 불타기 (바닥 점수 50~79) -> Tier 2
    elif bottom_score >= 50:
        gates_ok = (recovery_score is not None and recovery_score >= 2)
        if gates_ok:
            headline = "🟡 비중 확대 (Tier 2) — 추세 전환 / 불타기 구간"
            color = "#fcca46"
            actions = [
                "바닥 점수 50점대 진입 및 게이트키퍼(5일선 돌파·환율 안정·수급) 중 2~3가지가 확인되었습니다.",
                "기존 코어(3~40%) + 스나이퍼(10%)에 이어, 남은 불타기 예산(20~30%)을 10% 단위로 추가 투입하는 실질적 풀매수 타이밍입니다.",
                "완벽한 V자 반등이 확인되는 오후 3시에 집행하여 리스크를 최소화하세요.",
            ]
        else:
            headline = "🟡 대기 (Tier 2 대기) — 바닥 확인 중 (게이트키퍼 미충족)"
            color = "#fcca46"
            actions = [
                "바닥 점수는 50점대이지만 아직 게이트키퍼(반등 신뢰도)가 2점 미만입니다.",
                "수급(기관/외국인 매수)·5일선 돌파·환율 안정 중 2가지 이상이 충족될 때까지 추가 매수를 보류하고 현금 대기하세요.",
            ]

    # 5순위: 애매한 하락 (35~49)
    elif bottom_score >= 35:
        headline = "⚪ 애매한 하락 — 관망 (매수 금지)"
        color = "#aaaaaa"
        actions = [
            "단기 조정은 나왔지만 바닥이라 부르기엔 어설픈 35~49점 구간입니다.",
            "가장 돈을 많이 잃기 쉬운 어설픈 물타기 구간이므로 철저히 관망하세요.",
            "기존 코어 예산(30~40%)만 유지한 채 추가 투입은 절대 금물입니다.",
        ]

    # 6순위: 평범 (그 외) -> Tier 1
    else:
        headline = "🟢 일상 적립 (Tier 1) — 평이한 시장 흐름"
        color = "#21c354"
        actions = [
            "[Tier 1 구간] 큰 패닉이나 과열이 없는 평이한 시장입니다.",
            "총 예산의 30~40% 코어 자산 비중을 기계적으로 유지하세요.",
            "매수는 정해진 원칙에 따라 우량주 눌림목에서만 기계적으로 진행하세요.",
        ]

    return headline, color, actions
'''

# Use regex to replace the old function completely
pattern = re.compile(r'def get_strategic_advice\(.*?(?=def run_historical_backtest\()', re.DOTALL)
content = pattern.sub(new_func + '\n\n', content)

with open(r'C:\Users\로컬\Desktop\my-quant-bot\signals.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Updated get_strategic_advice")
