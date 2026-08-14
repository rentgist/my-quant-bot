# ORION Quant Dashboard — AI 작업 컨텍스트

새 대화에서 이 파일, CHANGELOG.md, .agents/AGENTS.md를 먼저 읽고 작업합니다. 현재 작업 기준 저장소는 main 브랜치입니다.

## 목적과 실행 방식

- final.py가 Streamlit 대시보드의 진입점입니다.
- 기준 소스는 GitHub `rentgist/my-quant-bot`의 `main` 브랜치입니다. 바탕화면의 다른 복사본보다 이 저장소와 배포본을 우선합니다.
- 대시보드는 시장 분석과 검토용 행동 가이드를 제공하며 주문을 자동 실행하지 않습니다.
- 모든 일별 판단은 종가 기준이며, 실제 조정은 다음 거래일 분할 실행을 전제로 합니다.

## 최신 안전 규칙

- 미국 시장 국면(CLEAR)과 실제 주문 허용(STARTER_GO)을 분리합니다.
- 데이터가 오래되었거나 빠졌거나, 낙하 중인 시장이면 신규 진입을 차단합니다.
- 미국 신규 진입은 SPY 20일선 2일 확인, RSP/SPY 시장폭, HYG/IEF 신용, 최신 수급 프록시를 함께 확인합니다.
- 백테스트는 다음 거래일 체결과 거래비용을 반영한 시간순 검증을 사용합니다.
- Value Accumulation / Scout는 본대 신호와 분리된 Shadow 레이어입니다. 시장 게이트와 종목 적격성을 모두 통과해야 하며 종목당 총자산 2%p, 전체 5%p를 넘지 않습니다.
- 바닥 탐지값은 보정된 확률이 아니므로 UI와 문서에서 `바닥점수`로 표기합니다.

## 주요 구성

- signals.py: 한국·미국 ORION 점수, 바닥·거시·수급 신호
- data_loader.py: yfinance, KRX, FRED 등 외부 시장 데이터 수집
- regime_playbook.py: 폭락·반등·상승·횡보 국면 분류와 장기 현금·주식 운용 규칙
- value_scout.py: 독립 Scout 시장 게이트, 종목 품질·낙폭 심사, 비중 상한
- hedging.py, defensive_overlay.py: 인버스 검증과 방어 규칙
- portfolio_manager.py: data/portfolio-logs/의 최신 날짜 로그에서 보유 티커 추출
- ai_reporter.py: 현재 국면과 보유종목을 반영한 맞춤형 설명 생성
- regime_state.json: 재실행 간 시장 경고 상태 보존

## 비협상 원칙

- 폭락 당일에는 기술적 급매도·신규 인버스·추격매수를 동결합니다.
- 주식 비중은 국면별 허용범위를 사용하며, 한 번에 총자산 5%p를 넘겨 바꾸지 않습니다.
- 인버스는 기본 운용안이 아니라 별도 검증을 통과한 단기 보조수단입니다. 검증 실패 시 신규 주문은 0원입니다.
- 포트폴리오 매도는 손실률만으로 결정하지 않고 시장 국면·추세·펀더멘탈을 함께 확인합니다.
- Scout도 폭락 당일·낙하 칼날·시스템 위험에는 0%이며, 추세가 확인되면 기존 본대 규칙으로 넘깁니다.

## 문서와 데이터 관리

- README.md: 사용자용 소개와 실행법
- CHANGELOG.md: 날짜순 변경 이력의 단일 기준. GitHub push 전 최상단에 갱신합니다.
- data/portfolio-logs/portfolio_log_YYYYMMDD.md: 날짜별 계좌 스냅샷. 최신 파일이 대시보드 입력입니다.
- docs/templates/investment_log_template.md: 새 계좌 로그 작성 양식

## 작업 규칙

1. 수정 전 관련 코드와 .agents/rules/strict_verification.md를 읽습니다.
2. 수정 후 관련 파일을 python -m py_compile로 확인하고, 가능한 단위 테스트를 실행합니다.
3. 기능 변경은 CHANGELOG.md에 기록합니다.
4. share 저장소는 사용자의 명시적 승인 없이 push하지 않습니다.
