# AI Company / `rentgist/my-quant-bot` 인수인계 컨텍스트

> 다른 GPT 채팅에 그대로 업로드/붙여넣기 위한 프로젝트 핸드오프 문서  
> 기준일: 2026-09-22  
> 사용자: 준희  
> 핵심 저장소: `rentgist/my-quant-bot`

---

## 0. 이 문서를 읽는 다음 GPT에게

이 문서는 준희가 진행해 온 **AI Company 자동화 구조 설계/구현/감사 및 A/B 회사 분리 실험**의 현재 상태를 이어가기 위한 컨텍스트다.

가장 중요한 운영 원칙은 다음 한 문장이다.

> **one execution plane, multiple bounded roles, durable GitHub state, evidence-based gates, no duplicate workers, no silent safeguard weakening**

준희는 구현 세부사항을 매번 직접 조작하기보다 **CEO처럼 목표만 말하고**, ChatGPT가 PM/Chief of Staff로 업무를 구조화해 GitHub Issue로 넘기고, 로컬 Codex/Claude가 실행·리뷰한 결과를 검증해 관리하는 방식을 원한다.

이 프로젝트에서는 "작동하는 것처럼 보인다"보다 **실제 diff / 테스트 / reviewer evidence / CI / exact head SHA**를 확인한 뒤 상태를 판단해야 한다.

---

# 1. 사용자 운영 선호

## 1.1 준희의 역할

- 준희 = CEO / 제품 방향 및 중요한 최종 결정자
- 구현 과정은 최대한 에이전트들이 처리하고, 준희는 결과를 보고 판단하는 구조 선호
- 자연어로 업무를 맡기는 것을 원함
- 반복적으로 PowerShell 명령을 직접 입력하거나 agent 간 전달을 사람이 중계하는 구조는 지양

## 1.2 도구/비용 선호

- ChatGPT 중심
- Codex + Claude Code를 직원처럼 사용
- **API 과금은 원하지 않음**
- 로컬/구독 기반 CLI + GitHub 중심 선호
- GitHub를 durable communication / operational ledger로 사용
- PC 2~3대 환경 가능성이 있으나, 현재 A회사 worker는 사실상 **single-machine topology**를 전제로 함

## 1.3 로컬 production clone

지금까지 사용한 production repo 경로:

```text
C:\Users\최준희\.gemini\antigravity\scratch\my-quant-bot
```

GitHub repo:

```text
rentgist/my-quant-bot
```

---

# 2. 전체 회사 구조

## 2.1 A회사 — GPT/ChatGPT 주도

역할:

- 준희: CEO
- ChatGPT: PM / Chief of Staff / 관리 콘솔
- Codex: Primary Developer / 구현자
- Claude Code: Independent Senior Reviewer
- CI: deterministic QA
- GitHub: durable source of operational truth
- `scripts/codex-queue-worker.ps1`: 단일 authoritative production execution engine

정상 업무 흐름:

```text
준희가 목표 전달
→ ChatGPT가 bounded GitHub Issue 작성
→ agent:queued
→ 로컬 scheduled worker가 Issue 선택
→ 전용 branch + worktree 생성
→ Codex 구현
→ changed-path enforcement
→ fixed test profile
→ Claude 독립 read-only review
→ PASS면 진행
→ CHANGES_REQUESTED면 Codex가 딱 1회 최소 수정
→ 다시 path check + tests
→ Claude final review 딱 1회
→ 다시 CHANGES_REQUESTED면 자동 반복 중단/관리층에 escalation
→ task branch commit/push
→ Draft PR
→ exact-head durable reviewer evidence
→ GitHub CI
→ ChatGPT PM이 실제 diff/evidence/CI 확인
→ routine reversible work는 관리층 merge 결정
```

중요:

- worker는 **절대 auto-merge하지 않음**
- worker는 **main을 직접 수정/push하지 않음**
- routine repo merge는 worker가 아니라 관리층(ChatGPT PM)의 별도 결정
- live trading, secrets, destructive actions, production deployment, 법적/재정적으로 중요한 행동 등은 준희의 명시적 결정이 필요

## 2.2 B회사 — Claude 주도

원래 준희의 의도:

- A회사: GPT/ChatGPT가 director → Codex 구현 → Claude 리뷰
- B회사: Claude가 director/implementer → Codex/GPT가 independent reviewer

B회사는 A회사와 비교/실험하기 위한 별도 조직이다.

B회사 목표 구조:

- 준희: CEO
- ChatGPT: human-facing PM / Chief of Staff
- Claude Code: primary technical director / architect
- Claude Code: primary implementer
- Codex / GPT: independent challenger/reviewer
- 별도 task/state/branch/worktree namespace
- A회사 queue/lifecycle/heartbeat와 분리
- scheduler는 bootstrap 검증이 끝난 뒤에만 고려

현재 B회사는 **완료 상태가 아니라 bootstrap 검증 중**이다.

---

# 3. A회사 핵심 안전장치

A회사에서 유지해야 하는 불변조건:

- 단일 production execution engine: `scripts/codex-queue-worker.ps1`
- `.ai-company/`는 governance/planning/orientation layer
- `.ai-company/`가 별도 worker/queue/lifecycle DB/merge path/source of truth가 되면 안 됨
- Issue text를 shell code처럼 실행하지 않음
- test command는 arbitrary shell이 아니라 fixed profile enum
- allowed/forbidden path enforcement
- forbidden path가 allow-list보다 우선
- isolated branch/worktree per task
- base worktree는 `main`, tracked/staged clean 상태여야 worker 시작
- retry bounded
- fail-closed
- Claude reviewer read-only
- Claude unavailable 시 기존 정책이 허용하는 경우에만 Codex self-review fallback
- fallback은 반드시 `Codex self-review`로 표시
- independent Claude인 것처럼 속이면 안 됨
- review evidence는 exact head SHA에 bind
- malformed/missing/stale evidence는 fail closed
- Draft PR only
- no worker auto-merge
- no worker direct-main
- secrets/raw logs/local paths를 GitHub 진단에 노출하지 않음
- trading/deploy/customer notifications 같은 외부 consequential side effect 금지

---

# 4. Review state machine

Claude 리뷰는 단순 참고가 아니라 실제 gate다.

## Initial review

Claude가 최상단 verdict로 다음 중 하나를 반환:

```text
PASS
CHANGES_REQUESTED
```

### PASS
- reviewer loop 종료
- 다음 단계로 진행

### CHANGES_REQUESTED
- Codex가 allowed paths 내에서 **딱 한 번** 최소 수정
- path enforcement 재실행
- fixed tests 재실행
- Claude final review **딱 한 번**

### Final CHANGES_REQUESTED
- 더 이상 agent-to-agent 자동 왕복하지 않음
- BLOCK / PM escalation

## Claude unavailable

기존 control plane이 허용할 때:

```text
Codex self-review
```

로 fallback 가능.

단:

- independent Claude review라고 표시하면 안 됨
- durable evidence에 reviewer identity/provenance가 정직하게 남아야 함

---

# 5. Durable GitHub state

주요 durable state:

- GitHub Issues
- lifecycle labels
- PR
- CI
- reviewer evidence comments
- Issue #35 worker heartbeat
- local lifecycle JSON (restart/recovery용)

중요 label:

- `agent:queued`
- `agent:running`
- `agent:blocked`
- `agent:done`
- `agent:approval-required`

Issue #35는 local worker heartbeat로 사용됨.

---

# 6. 주요 역사 — governance consolidation

## 6.1 Issue #63

제목:

```text
[Codex] Consolidate AI Company governance with existing control plane
```

목표:

- `.ai-company/CONSTITUTION.md`
- `.ai-company/PERMISSIONS.md`
- `.ai-company/PRIMARY_WORKER.md`
- `.ai-company/STATE.md`
- `.ai-company/WORKFLOWS.md`
- `.ai-company/tasks/TASK-001.md`
- root `AGENTS.md`
- `CHANGELOG.md`

핵심:

- `.ai-company/`를 governance layer로 추가
- PowerShell worker는 그대로 단일 production engine
- TASK-001은 historical only
- FAST/STANDARD/DEEP governance 정의
- no second worker

### 관련 superseded PR

- PR #64: management design reference only
- PR #65: governance 구현 시도
  - CEO 이름이 `????`로 깨짐
  - durable independent Claude review evidence 부족

## 6.2 Issue #67 / PR #68

Issue #67:

```text
[Codex] Recreate AI Company governance consolidation with corrected UTF-8 and durable review evidence
```

PR #68은 실제 governance 파일에 literal UTF-8 `준희`가 정상이고 scope도 좋았음.

문제:

- reviewer durable evidence가 충분하지 않았음
- 이후 #70이 `CHANGELOG.md`를 바꾸면서 PR #68은 merge conflict/dirty 상태가 됨
- 최종적으로 merge하지 않고 superseded 처리

---

# 7. Reviewer evidence publisher — Issue #69 / PR #70

## Issue #69

```text
[Codex] Publish reviewer verdict as durable GitHub evidence
```

목표:

- reviewer verdict를 GitHub-visible evidence로 게시
- exact task head SHA에 bind
- reviewer identity/type 명시
- verdict: `PASS` / `CHANGES_REQUESTED`
- malformed/stale/missing/publication failure → fail closed
- Claude vs Codex self-review provenance 정직하게 유지
- idempotent publication

## PR #70

MERGED.

추가된 핵심 함수:

- `Get-SingleBoundedReviewField`
- `Get-ValidatedBoundedReviewEvidence`
- `ConvertTo-CodexSelfReviewReport`
- `Get-BoundedReviewEvidenceMarker`
- `New-BoundedReviewEvidenceBody`
- `Publish-BoundedReviewEvidence`

이 PR 이후 reviewer evidence는 durable GitHub record로 남길 수 있게 됨.

---

# 8. Issue #72 사건

Issue #72:

```text
[Codex] Recreate governance consolidation on current main with durable review evidence
```

목표는 #68의 좋은 governance 내용을 최신 main 위에서 다시 만드는 것이었음.

## Attempt 1

- tested phase까지 감
- reviewer가 PASS 안 함
- Draft PR 생성 차단

## Attempt 2

- tested phase까지 감
- 같은 reviewer failure

## Attempt 3

- worktree-ready 단계에서 Codex exit code 1
- retry exhausted
- `BLOCKED | code=RETRY_LIMIT`

처음에는 governance 구현 자체 문제처럼 보였지만 이후 Claude Code read-only 조사에서 원인이 밝혀짐.

---

# 9. Claude Code의 #72 사고 원인 분석

Claude의 결론:

## Primary defect — REVIEW_NORMALIZATION_DEFECT

reviewer가 본 diff가 잘못되었음.

### 원인 1: moving base-branch drift

reviewer diff가 task 고정 기준이 아니라 움직이는 `$BaseBranch` / `main`을 기준으로 계산됨.

결과:

- task와 상관없는 나중 main 변경이 reviewer diff에 섞임
- reviewer가 unrelated change라고 판단

### 원인 2: Windows PowerShell 5.1 UTF-8 native output handling

`git diff` native output을 reviewer prompt로 가져오는 경계에서 UTF-8 처리 미흡.

결과:

```text
준희
```

가 reviewer input에서:

```text
????
```

같이 깨질 수 있었음.

중요:

- 실제 governance 파일은 정상
- parser / fail-closed gate는 정상
- reviewer도 잘못된 input을 받은 상태에서는 정상적으로 CHANGES_REQUESTED를 냄

## Attempt 3

별개의 문제:

```text
TRANSIENT_ENVIRONMENT
```

Codex model server overload.

즉 최종 분류:

```text
MULTIPLE_DEFECTS
- Primary: REVIEW_NORMALIZATION_DEFECT
- Secondary: TRANSIENT_ENVIRONMENT
```

---

# 10. Issue #75 / PR #76 — review input fix

Issue #75:

```text
[Codex] Fix bounded-review staged diff normalization and UTF-8 capture
```

허용 파일:

- `scripts/codex-queue-worker.ps1`
- `scripts/run-agent-review.ps1`
- `CHANGELOG.md`

핵심 수정:

- reviewer diff를 moving `main`이 아니라 task worktree의 stable HEAD 기준 staged diff로 생성
- strict UTF-8 native Git capture
- Windows PowerShell 5.1 regression coverage
- base-branch drift regression test
- Korean non-ASCII round-trip regression test
- initial Claude review / final Claude review / Codex self-review / resolution prompt 모두 동일 diff semantics 사용

PR #76:

- automation-smoke PASS
- GitHub CI PASS
- Independent Claude read-only review PASS
- exact head evidence 확인 후 merge

Merge commit:

```text
691c7057452d87657f0680fa4183e3b735ea76a6
```

Issue #75 completed.

---

# 11. Governance final replacement — Issue #77 / PR #78

#75 fix 후 새로운 governance replacement를 최신 main에서 다시 실행.

Issue #77:

```text
Recreate governance consolidation from post-#75 main
```

PR #78:

- 허용된 governance 파일만 변경
- literal UTF-8 `준희` 정상
- TASK-001 historical-only
- single production worker 명시
- automation-smoke PASS
- CI PASS
- Independent Claude read-only reviewer PASS
- exact-head evidence 확인

최종 merge commit:

```text
b57042dab70927bbf53b56e919b860390bd086c6
```

후속 정리:

- #77 completed
- #72 completed
- #67 completed
- #63 completed
- PR #68 closed unmerged as superseded
- PR #65 closed unmerged as superseded
- PR #64 closed unmerged as superseded

#49 / #61은 건드리지 않았음.

---

# 12. 최종 architecture audit — Issue #79

Issue #79:

```text
[Audit] Claude Code read-only architecture audit
```

Claude Code를 Principal Engineer / AI control-plane auditor로 실행.

감사 기준은 당시 current main:

```text
6f1430128782bdf1b4e758169a50e47d9d781755
```

Claude가 확인한 precondition:

- local HEAD exact match
- working tree clean
- 이전 governance merge 이후 control-plane 파일에는 변화 없음
- strict read-only inspection
- 파일/브랜치/worktree/GitHub state 변경 없음

## Audit final verdict

```text
Architecture score: 82/100
Production-use status: READY_WITH_FOLLOWUPS
Final verdict: READY_WITH_FOLLOWUPS
```

### 중요한 결론

- CRITICAL 없음
- HIGH 없음
- routine use 전에 반드시 고쳐야 하는 must-fix 없음
- A회사 control plane은 실제 운영 가능

## Audit가 확인한 강점

- single execution plane
- Codex bounded implementation
- Claude independent read-only review
- fail-closed path/test/review gates
- exact-head evidence
- durable GitHub evidence
- bounded retry/recovery
- UTF-8 + task-relative staged diff regression test
- Draft PR only
- no worker auto-merge
- Issue text를 shell로 실행하지 않음
- reviewer provenance spoof 방지
- #72/#75 사고가 regression coverage로 실제 닫힘

---

# 13. Audit findings

## MEDIUM — repository-wide 문서 표현 오류

기존 문서가:

> 어떤 자동 경로도 main을 수정/push하지 않는다

는 식으로 repo 전체에 대해 너무 절대적으로 씀.

하지만 실제로:

```text
.github/workflows/tenbagger-sector-cycle.yml
```

이 존재.

이 workflow는:

- deterministic scanner
- non-agentic
- scheduled GitHub Actions
- `contents: write`
- `main`에 직접 commit/push
- 대상 파일:
  - `data/tenbagger_scan_state.json`
  - `data/tenbagger_final_candidates.json`

중요한 해석:

> **A회사의 AI agent control plane은 여전히 단일 execution plane이고 worker direct-main을 하지 않는다.**
>
> 다만 저장소 전체에는 Tenbagger 데이터 refresh라는 별도의 deterministic direct-main write path가 존재한다.

즉 구조 결함보다 문서 scope 오류.

## LOW — mutex가 machine-local

현재 mutex는 Windows 한 머신 안에서는 안전.

하지만 동일 worker를 두 PC에서 동시에 돌리면 GitHub-side atomic lock은 없음.

현재 single-machine 운영에서는 blocker 아님.

향후 multi-machine worker를 실제 사용할 때만 개선 필요.

## LOW — closed Issue의 local worktree/lifecycle cleanup이 자동이 아님

예: 과거 #72 lifecycle/worktree state가 로컬에 남을 수 있음.

안전 문제는 아니지만:

- 디스크 누적
- 운영자가 active state로 착각 가능

현재는 manual cleanup이 의도된 정책.

## LOW — `automation-smoke` 문서 누락

실제 worker는 fixed profiles로:

- `python-compile-and-pytest`
- `pytest`
- `automation-smoke`

를 지원하지만 일부 문서에는 앞 두 개만 적혀 있었음.

## INFO — bounded review 문서가 실제 구현보다 뒤처짐

`docs/CEO_CONTROL_PLANE.md` 일부 문구가 옛 hedge를 유지.

현재는 실제 코드에:

- one correction
- final review
- self-tests

가 구현돼 있음.

---

# 14. Issue #80 — 현재 A회사 남은 follow-up

Issue #80:

```text
[Codex] Align control-plane documentation with audited repository behavior
```

현재 상태(2026-09-22 최신 확인):

```text
OPEN
agent:queued
Draft PR 아직 없음
```

목표: **문서만 수정**.

Allowed paths:

```text
docs/automation-architecture.md
docs/CEO_CONTROL_PLANE.md
CHANGELOG.md
```

Forbidden:

```text
.github/
automation/
.ai-company/
AGENTS.md
scripts/
data/
application/investment code
requirements.txt
tenbagger_scanner.py
```

할 일:

1. "no automated path modifies main" 표현을 **AI Company / Codex-Claude control plane scope**로 좁히기
2. Tenbagger cron workflow를 별도 deterministic non-agentic data-refresh job으로 문서화
3. normal PR CI는 read-only라는 점 유지
4. `automation-smoke` fixed profile 문서에 추가
5. bounded final review가 현재 구현/검증돼 있다는 식으로 stale hedge 갱신
6. CHANGELOG 추가
7. 실행 코드/워크플로 동작은 절대 변경하지 않음
8. automation-smoke + bounded review + CI + Draft PR

A회사 관점에서 이 #80은 **필수 구조 수정이 아니라 문서 정리**다.

---

# 15. A회사 현재 상태

현재 판단:

```text
A COMPANY = operational / routine-use ready
```

정확히는:

```text
READY_WITH_FOLLOWUPS
```

하지만 audit 기준:

```text
Must-fix before routine use: none
```

따라서 준희는 이미 A회사에 자연어로 업무를 맡겨도 됨.

예:

```text
빔 계산기에서 Gaussian beam propagation 기능 추가해줘.
```

```text
퀀트 대시보드 UI 개선해줘.
```

```text
이 버그 재현하고 원인 분석한 뒤 수정해줘.
```

ChatGPT PM이 Issue/task scope/gates를 구성하고 로컬 worker에게 넘기는 형태.

---

# 16. 최신 A회사 heartbeat

2026-09-22 최신 확인 기준 Issue #35:

```text
status: healthy
sync_status: synced
base_branch: main
local_branch: main
local_head: 6f1430128782
origin_main_head: 6f1430128782
synchronized: true
tracked_dirty: false
staged_dirty: false
worker_exit_code: 0
schedule_interval_minutes: 15
```

즉 #80을 local A worker가 잡아갈 수 있는 상태.

---

# 17. B회사 — Issue #73 / Draft PR #74

Issue #73:

```text
[Company B] Bootstrap independent Claude-led company
```

현재:

```text
OPEN
agent:approval-required
```

PR #74:

```text
feat(company-b): bootstrap independent Claude-led AI company
```

현재 최신 확인:

```text
OPEN
DRAFT
NOT MERGED
head_sha: 31b2b760b943c029f96a56eec873f1d71c9d76a0
base_sha: 588721d9ffe2365cd92b703248e6e49603726530
```

주의:

- PR base가 오래된 main에서 시작
- 최신 main 기준으로 재검증 필요
- 아직 merge 금지
- scheduler/poller 활성화 금지

---

# 18. B회사 구현 내용

B namespace:

```text
companies/company-b/
scripts/company_b/
docs/company-b/
automation/experiments/company-b/
```

대표 구현:

- `companies/company-b/ARCHITECTURE.md`
- `companies/company-b/STATE.md`
- `companies/company-b/tasks/B-TASK-001.json`
- `docs/company-b/OPERATIONS.md`
- `scripts/company_b/README.md`
- `scripts/company_b/claude-cli-probe.ps1`
- `scripts/company_b/company-b-worker.ps1`
- `scripts/company_b/reset-failed-task.ps1`
- `scripts/company_b/run-bootstrap-task.ps1`

B worker one-shot 의도:

```text
Claude plan
→ Codex challenge
→ Claude implementation
→ path enforcement
→ fixed tests
→ Codex review
→ 필요 시 Claude correction 1회
→ final Codex review
→ local commit
→ optional push
```

---

# 19. B-TASK-001 진행 역사

초기 목표:

안전한 bootstrap probe로:

```text
docs/company-b/BOOTSTRAP_PROBE.md
```

만 생성/검증.

## 초기 실패

Company B worker가 isolated task worktree까지는 도달.

하지만 첫 Claude read-only planning turn에서 실패.

당시 문제:

- Claude stderr가 worker에서 충분히 보이지 않음
- authentication / Windows Git Bash / model access / environment 중 무엇인지 즉시 구분 어려움

## 후속 조사

Claude CLI probe를 따로 만들고 확인.

결과:

- basic print PASS
- explicit `claude-sonnet-5` PASS
- bounded plan/read-only mode PASS
- exit_code 0

추가:

- B-only failed-task reset tooling
- bootstrap runner
- Claude planning max-turns를 bootstrap 동안 1 → 4로 제한적 확대
- Edit/Write/Bash restriction은 그대로

당시 다음 단계:

```text
failed local B-TASK-001 artifacts reset
→ isolated B-TASK-001 rerun
```

현재는 A회사 final audit/follow-up 후, 최신 main 기준 재검증한 다음 B-TASK-001을 다시 돌리는 것이 안전.

---

# 20. A/B 분리에서 절대 혼동하면 안 되는 점

## A회사

```text
ChatGPT/GPT-led
Codex implementation
Claude review
```

## B회사

```text
Claude-led
Claude implementation
Codex/GPT review
```

둘은 역할만 반대가 아니라 task/state/branch/worktree namespace도 논리적으로 분리한다.

단, 중요한 아키텍처 원칙:

> "두 회사"가 있다고 해서 repository에 **서로 경쟁하는 두 production control plane**을 아무렇게나 만들면 안 된다.

A회사의 production worker는 검증된 단일 execution engine.

B회사는 아직 실험/bootstrap 단계이며 A lifecycle/heartbeat를 건드리지 않도록 분리.

---

# 21. 로컬 Claude Code 실행 방식

현재 일반 ChatGPT 채팅에서는 준희 PC의 로컬 terminal을 직접 실행할 수 없다.

대신 ChatGPT Desktop의 Codex local session에서:

```text
C:\Users\최준희\.gemini\antigravity\scratch\my-quant-bot
```

repo를 열고 로컬 terminal을 통해 `claude` CLI를 실행할 수 있다.

실제로 #79 audit도 이 방식으로 성공.

중요:

- 작업 전에 반드시 `git rev-parse HEAD`
- audit target exact SHA 확인
- read-only task면 pull/reset 등으로 억지로 맞추지 말고 mismatch 시 stop

---

# 22. #79에서 사용한 audit 철학

Claude audit는 다음을 검사하도록 했음:

```text
AGENTS.md
→ .agents/AGENTS.md
→ .ai-company/*
→ docs/CEO_CONTROL_PLANE.md
→ scripts/codex-queue-worker.ps1
→ reviewer/recovery/scheduler scripts
→ GitHub lifecycle/PR/CI/#35
```

검사 영역:

- authority boundaries
- single execution plane
- docs vs executable behavior
- retries/recovery/reboot
- idempotency/stale state
- worktree cleanup
- review independence
- UTF-8/diff integrity
- exact-head evidence
- path validation
- fixed test profiles
- no-auto-merge/direct-main
- secrets/privacy
- races/concurrency
- observability
- #72/#75 regression closure
- extensibility
- dead/contradictory paths

이 수준의 audit을 향후 control-plane major change 후 재사용 가능.

---

# 23. 관리 자동 감시

현재 ChatGPT 측에 #80 후속을 감시하는 자동화가 설정돼 있다.

의도:

```text
#80 상태/PR 확인
→ docs-only scope 확인
→ automation-smoke
→ exact-head reviewer evidence
→ current-head CI
→ 정상일 경우 routine management-layer merge
→ #80 close
→ #35가 새 main에 healthy/synced 될 때까지 확인
→ 이후 B회사 #73/#74 재점검
```

B회사에 대해서는:

- PR #74 바로 merge 금지
- scheduler enable 금지
- 최신 main 기준 재검증 우선
- local Claude/Codex action이 꼭 필요하면 준희에게 최소 실행 명령/프롬프트 요청

---

# 24. Tenbagger workflow에 대한 올바른 해석

파일:

```text
.github/workflows/tenbagger-sector-cycle.yml
```

이건 AI Company worker가 아님.

특징:

- GitHub Actions cron
- deterministic scanner
- non-agentic
- `contents: write`
- direct `main` push 가능
- scope:
  - `data/tenbagger_scan_state.json`
  - `data/tenbagger_final_candidates.json`

따라서 앞으로 문서에서는 다음처럼 표현하는 것이 맞음:

> AI Company/Codex-Claude control plane에는 automated direct-main write/merge path가 없다.

하지만:

> Repository 전체에는 별도의 deterministic Tenbagger data-refresh workflow가 scoped JSON state를 main에 직접 갱신한다.

---

# 25. 현재 main

2026-09-22 최신 확인 기준 main:

```text
6f1430128782bdf1b4e758169a50e47d9d781755
```

이전 governance merge commit:

```text
b57042dab70927bbf53b56e919b860390bd086c6
```

그 이후 architecture/control-plane 변경 없이 Tenbagger data state 관련 commit이 들어온 상태였음.

---

# 26. 중요한 과거 SHA / PR / Issue 목록

## A회사 control plane

- #63 — initial governance consolidation
- PR #64 — superseded design/reference
- PR #65 — superseded governance implementation
- #67 — corrected governance recreation
- PR #68 — good governance content but superseded/unmerged
- #69 — durable reviewer evidence publisher
- PR #70 — merged
- #72 — failed governance recreation / incident evidence
- #75 — staged diff + UTF-8 fix
- PR #76 — merged, merge commit: `691c7057452d87657f0680fa4183e3b735ea76a6`
- #77 — fresh governance replacement
- PR #78 — merged, merge commit: `b57042dab70927bbf53b56e919b860390bd086c6`
- #79 — final Claude architecture audit
  - completed
  - verdict `READY_WITH_FOLLOWUPS`
  - score 82/100
- #80 — audit documentation follow-up
  - currently queued
  - docs only

## Health

- #35 — Local worker heartbeat

## B회사

- #73 — Company B bootstrap
- PR #74 — Company B Draft bootstrap PR

---

# 27. accidental branches

과거 #63 correction 과정에서 생긴 accidental branches:

```text
automation/63-governance-correction
automation/63-governance-correction-2
automation/63-governance-correction-final
automation/63-governance-correction-worker
automation/63-governance-correction-clean
```

이 브랜치들은 사용하지 않는 것이 원칙.

---

# 28. `공간히어로 자동화 CODEX`

준희가 최근 말한 새로운 로컬 항목:

```text
공간히어로 자동화 CODEX
```

현재 상태:

- 준희 PC LOCAL에 존재한다고 함
- 현재 일반 채팅에서는 로컬 filesystem에 직접 접근하지 못해서 아직 구조를 읽지 못함
- GitHub repo인지도 아직 확인 안 됨
- 다음 GPT가 local Codex/Desktop context를 쓸 수 있다면 이 폴더를 직접 열어 구조 분석 가능
- 또는 ZIP 업로드 / GitHub repo name 제공 시 원격 분석 가능

이 항목은 현재 A/B AI Company 구조와 별개일 수 있으므로, 내용을 보기 전에는 함부로 합치지 말 것.

---

# 29. 다음 GPT가 지금 해야 할 일

## A회사

1. #80 진행 상태 fresh-check
2. Draft PR이 생기면:
   - changed paths가 정확히:
     - `docs/automation-architecture.md`
     - `docs/CEO_CONTROL_PLANE.md`
     - `CHANGELOG.md`
   - 실행 코드/workflow/data 변경 없는지 확인
   - automation-smoke PASS
   - exact-head bounded reviewer evidence
   - current-head CI PASS
3. 모두 통과하면 routine management-layer merge
4. #80 close
5. #35가 새 main에 healthy/synced인지 확인

A회사에서 이게 끝나면 문서 follow-up까지 완전히 닫힘.

## B회사

A와 독립적으로 진행.

다음:

1. PR #74를 최신 main 기준으로 재검증
2. 필요한 경우 safe rebase/recreation 전략 판단
3. Company A files/lifecycle 침범 금지
4. B-TASK-001 reset/rerun
5. Claude → Codex round trip 확인
6. fixed tests / review 확인
7. scheduler는 그 후에만 검토
8. merge는 아직 서두르지 말 것

---

# 30. 새로운 GPT가 준희에게 답할 때의 톤

준희는 다음 스타일을 선호:

- 결론 먼저
- 너무 장황하지 않게
- 사실 / 추론 / 의견 구분
- 현재 상태는 실제로 확인한 뒤 말하기
- "완벽하다"보다 "검증된 범위에서 operational ready"처럼 정확하게
- 에이전트가 테스트/리뷰를 안 했으면 했다고 말하지 않기
- 실패 시 safeguard를 낮추지 말고 원인을 보고하기
- 준희가 CEO처럼 결과만 볼 수 있도록 PM이 중간 implementation trivia를 최대한 흡수하기

---

# 31. 한 줄 현재 상태

```text
A회사 = 실사용 가능, Claude 독립 리뷰 포함, 최종 audit 통과(READY_WITH_FOLLOWUPS), 현재 #80 문서 정리 작업만 queued.
B회사 = 별도 Claude-led bootstrap 실험 중, PR #74 Draft, 최신 main 재검증 후 B-TASK-001 재실행 필요.
공간히어로 자동화 CODEX = 로컬에 존재하지만 아직 미분석.
```

---

# 32. 새 GPT용 즉시 컨텍스트 프롬프트

아래 문장을 새 채팅 첫 메시지로 같이 붙여도 됨:

```text
첨부한 MD는 이전 ChatGPT 채팅에서 진행해 온 AI Company / rentgist/my-quant-bot 프로젝트의 인수인계 컨텍스트다.

이 문서를 현재 source-of-context로 읽고 이어서 작업해줘.
다만 현재 GitHub state는 시간이 지나 변경됐을 수 있으니 Issue/PR/CI/heartbeat/SHA 같은 동적 상태를 주장하기 전에 반드시 fresh-check 해줘.

A회사와 B회사를 혼동하지 말고,
A회사의 검증된 single production execution plane과 fail-closed safeguards를 약화시키지 마.
기존 테스트/리뷰/evidence gate를 우회하거나 duplicate worker/control plane을 만들지 마.

나는 CEO처럼 목표만 전달하고 싶고,
너는 PM/Chief of Staff처럼 업무를 bounded Issue로 구조화하고 결과를 검증해 관리해줘.
```
