# TASK-001 — ORION Project Onboarding
Type: STANDARD
Status: READY
Priority: HIGH
Owner: CODEX
Next Agent: CODEX
Worker: PRIMARY

## Objective
코드를 수정하지 않고 현재 ORION Quant Dashboard의 구조, 실행 경로, 데이터 흐름, 핵심 투자 로직, 테스트/자동화, 위험 요소를 인수인계 수준으로 문서화한다.

## Required Reading
1. .ai-company/CONSTITUTION.md
2. .ai-company/PERMISSIONS.md
3. AI_CONTEXT.md
4. .agents/AGENTS.md
5. .agents/rules/strict_verification.md
6. README.md
7. CHANGELOG.md 최신 구간

## Constraints
- 기존 코드 수정 금지
- dependency 변경 금지
- 설정 변경 금지
- 자동 주문/브로커리지 접근 금지
- secrets 출력 금지

## Codex Deliverable
`.ai-company/PROJECT_MAP.md` 작성. 최소 포함:
- entry point와 실행 명령
- 주요 모듈과 책임
- 주요 데이터 소스와 데이터 흐름
- ORION signal / regime / value scout / portfolio 관련 로직 위치
- 상태 파일 및 생성 데이터
- GitHub Actions/자동화
- 테스트/검증 구조
- 외부 의존성
- 현재 확인된 위험/기술부채
- AI Company worker가 건드리면 안 되는 영역
- 후속 자동화에 필요한 추천 포인트

## Handoff to Claude
Codex는 완료 후 `.ai-company/handoffs/TASK-001-CODEX.md`를 작성한다.
Claude는 PROJECT_MAP과 실제 repo를 대조하여 누락/오류를 검토하고 `.ai-company/reviews/TASK-001-CLAUDE.md`에 PASS 또는 FIX_REQUIRED를 기록한다.

## Acceptance Criteria
- 코드 변경 0건
- PROJECT_MAP 생성
- 근거 없는 추정은 명시적으로 UNKNOWN 처리
- Claude 독립 리뷰 완료
- 필요 시 Codex 1회 수정
- 최종 PASS 후 STATE의 NEXT_ACTION 갱신
