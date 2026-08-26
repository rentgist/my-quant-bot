# Primary Worker Bootstrap
Version: 0.2

## Goal
한 대의 로컬 PC가 GitHub를 기준으로 작업을 받아 Codex CLI와 Claude Code를 순차 실행하는 첫 worker가 된다. v0.2에서는 멀티 PC 분산 실행을 하지 않는다.

## Local Requirements
- Git
- Python 3
- GitHub 접근 가능한 인증
- Codex CLI: ChatGPT 구독 계정 로그인
- Claude Code: Claude 구독 계정 로그인
- repository clone: rentgist/my-quant-bot

## Billing Guard
- OpenAI/Anthropic API key를 worker용으로 요구하지 않는다.
- `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`가 설정되어 있더라도 worker는 API 호출 경로를 사용하지 않도록 설계한다.
- Codex CLI와 Claude Code의 구독 로그인 상태를 각각 사람이 최초 1회 확인한다.

## v0.2 Worker Loop
1. git fetch
2. main 및 AI Company 상태 확인
3. READY task 탐색
4. Worker=PRIMARY인 task만 claim
5. task branch 생성/checkout
6. Codex CLI 실행
7. 결과/hand-off 파일 확인
8. Claude Code review 실행
9. FIX_REQUIRED면 Codex에 최대 2회 반환
10. 테스트/검증 상태 확인
11. 결과 push 및 PR 생성
12. STATE 갱신
13. CEO에게 필요한 결정이 있으면 ESCALATE 상태로 기록

## Safety
- main에 직접 push하지 않는다.
- worker는 merge하지 않는다.
- live trading 금지.
- 외부 유료 API 신규 호출 금지.
- credentials/log secrets 출력 금지.
- task claim/lock이 구현되기 전에는 Primary Worker 하나만 실행한다.

## First Local Test
TASK-001은 코드 수정 없는 read-only onboarding task다. 이 작업으로 Codex/Claude CLI 호출, Git handoff, review loop가 정상 동작하는지 검증한다.
