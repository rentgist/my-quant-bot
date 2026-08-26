# ORION AI Agent Entry Rules

이 파일은 Codex/Claude/기타 에이전트가 저장소 루트에서 가장 먼저 확인하는 공통 진입점이다.

## Read First
1. `.ai-company/CONSTITUTION.md`
2. `.ai-company/PERMISSIONS.md`
3. `.ai-company/STATE.md`
4. `AI_CONTEXT.md`
5. `.agents/AGENTS.md`
6. `.agents/rules/strict_verification.md`
7. 현재 `.ai-company/tasks/`의 담당 task

## Source of Truth Priority
1. `.ai-company/CONSTITUTION.md`
2. `AI_CONTEXT.md` 및 기존 프로젝트 정책 문서
3. `.ai-company/STATE.md`
4. 현재 Task / Handoff / Review
5. `CHANGELOG.md`
6. 채팅 기록

## Non-negotiable
- 기존 프로젝트 규칙을 AI Company OS가 덮어쓰지 않는다. 충돌 시 더 엄격한 안전 규칙을 적용하고 필요하면 ESCALATE한다.
- 실제 투자 주문은 금지한다.
- main 직접 수정/merge 금지. task branch와 PR을 사용한다.
- 구현자는 자기 결과를 최종 승인하지 않는다.
- 작업 종료 전 NEXT_ACTION과 OWNER를 남긴다.
