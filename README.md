# ORION Quant Dashboard

한국·미국 시장의 국면, 거시 지표, 종목 분석과 포트폴리오 리밸런싱 판단을 지원하는 Streamlit 대시보드입니다. 투자 판단을 자동으로 실행하지 않으며, 모든 신호는 검토용입니다.

## 시작하기

    pip install -r requirements.txt
    streamlit run final.py

## 주요 기능

- 한국·미국 ORION Signal과 거시 위험 점검
- 종목 발굴, AI 리포트, 시장 일정
- 폭락·반등·상승·횡보 국면별 주식·현금 운용 가이드
- 본대 추세확인과 분리된 Value Accumulation / Scout Shadow 판정
- 구조적 가치·추세·당일 체결 품질을 분리한 한국 시장 실행 가드
- 보유종목의 시장 국면·추세·펀더멘탈 기반 부분축소 검토
- 인버스 전략의 별도 시간순 검증 및 안전 차단

## 문서 역할

| 문서 | 용도 |
|---|---|
| [AI_CONTEXT.md](AI_CONTEXT.md) | 새 AI 작업이 시작될 때 읽는 현재 설계·원칙 |
| [CHANGELOG.md](CHANGELOG.md) | 날짜별 코드·기능 변경 이력 |
| [포트폴리오 로그 템플릿](docs/templates/investment_log_template.md) | 날짜별 계좌 스냅샷 작성 양식 |
| [Value Scout 운용 규칙](docs/VALUE_SCOUT_POLICY.md) | 시장 게이트·종목 적격성·비중·무효화 기준 |
| [한국 시장 체결 품질 정책](docs/MARKET_EXECUTION_POLICY.md) | 외국인 선물·시장 폭·종가 돌파 실패의 해석과 주문 유예 기준 |

## 포트폴리오 로그

data/portfolio-logs/portfolio_log_YYYYMMDD.md에 날짜별로 새 로그를 쌓습니다. 대시보드는 가장 최신 날짜 파일을 자동으로 읽습니다. 과거 로그는 투자 판단의 근거와 변화를 남기는 기록이며, 변경 이력인 CHANGELOG.md와는 목적이 다릅니다.

## 데이터 공개 주의

이 저장소는 public입니다. 포트폴리오 로그에 보유 종목·수량·금액을 기록하면 GitHub에 공개됩니다. 현재는 공개를 허용한 상태를 전제로 관리합니다.
