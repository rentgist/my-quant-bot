# 안전한 로컬 에이전트 큐 자동화

## 결론

이 구조는 GitHub Issue의 제한된 구조화 필드만 데이터로 읽고, 로컬의 전용 Git worktree에서 Codex를 실행한 뒤, 테스트와 읽기 전용 리뷰를 거쳐 **Draft PR만** 만듭니다. `main` 브랜치를 체크아웃·수정·푸시·병합하는 자동 경로는 없습니다.

## 전체 흐름

```text
GitHub Issue (`agent:queued`)
  -> local `scripts/codex-queue-worker.ps1` (manual run or local scheduler)
  -> one mutex-protected task only
  -> external dedicated worktree + `automation/<issue>-<slug>` branch
  -> Codex implementation
  -> fixed Python test profile
  -> Claude Code plan-mode review, if available and authenticated
       -> otherwise Codex read-only self-review
  -> fixed Python test profile again
  -> task-branch commit, push, Draft PR
  -> human review and explicit merge
```

이것은 self-hosted GitHub Actions runner가 아닙니다. GitHub Actions의 CI는 PR 이벤트에서 읽기 권한으로만 실행되며, worker는 개발자 컴퓨터에서 수동 실행하거나 로컬 스케줄러로 실행합니다.

## Issue 입력 계약

`.github/ISSUE_TEMPLATE/codex-task.yml`은 다음 필드만 제공합니다.

- Title, Objective, Acceptance criteria
- Allowed paths, Forbidden paths
- Test command (`python-compile-and-pytest` 또는 `pytest`라는 고정 프로필)

worker는 Issue 본문에서 이 markdown 헤더를 정확히 한 번씩 읽습니다. 경로는 repository-relative 형식과 path traversal 여부를 검사합니다. 테스트는 자유 입력 명령을 호출하지 않고, 선택된 프로필을 고정된 Python 명령에 매핑합니다. `Invoke-Expression`, `cmd /c`, shell 문자열 평가를 사용하지 않습니다.

변경 파일이 허용 경로 밖이거나 금지 경로에 속하면 즉시 실패하며 PR을 만들지 않습니다. Issue의 금지 목록과 별도로 `final.py`, `signals.py`, `regime_playbook.py`, `hedging.py` 및 보호된 네 개의 untracked `fix_*.py` 파일은 worker가 항상 금지합니다.

## 권한 경계

| 구성 요소 | 가능한 작업 | 불가능하거나 의도적으로 하지 않는 작업 |
| --- | --- | --- |
| Issue form | 구조화된 요구사항 데이터 제공 | shell 코드 실행, 경로 정책 우회 |
| local worker | 새 작업 브랜치/worktree 생성, 검증, task branch push, Draft PR 생성 | main 수정/push/merge, 주문, Telegram, 배포 |
| Codex implementation | 전용 worktree 내의 허용 경로 수정 | commit, push, merge, PR 생성, 금지 경로 수정 |
| Claude review | 제공된 staged diff와 테스트 요약의 plan-mode 읽기 전용 리뷰 | 파일 수정, shell 실행, Git 쓰기 |
| PR CI | PR에서 Python 문법 검사와 현재 테스트 실행 | secrets, 배포, auto-merge |
| human | Draft PR 검토 및 병합 결정 | 자동화가 대신 승인하지 않음 |

worker는 기본 worktree가 `main`에 있고 tracked/staged 변경이 없을 때만 시작합니다. 그러나 기존의 untracked 파일은 검사·삭제·추적하지 않습니다. 새 worktree의 기본 위치는 저장소 바깥의 `<repo>-agent-worktrees`라서 주 작업 폴더에 untracked 폴더도 남기지 않습니다.

## 테스트 및 PR 정책

기본 테스트 프로필은 `python-compile-and-pytest`입니다. 이는 저장소 최상위와 `tests/`의 Python 파일을 컴파일한 뒤 `python -m pytest`를 실행합니다. CI도 동일하게 Python 문법 검사와 현재 pytest suite를 실행합니다.

테스트가 한 번이라도 실패하면 기본 정책은 **Draft PR을 만들지 않는 것**입니다. 실패한 전용 worktree는 삭제하지 않아 원인 확인에 사용할 수 있지만, `main`과 기존 작업 폴더는 변경되지 않습니다. 테스트 출력은 토큰이나 환경값이 로그에 노출되지 않도록 worker가 요약 상태만 보관합니다.

## Claude Code optional 동작

`scripts/run-agent-review.ps1`은 `claude.cmd`, `claude.exe`, `claude`와 일반 npm 설치 경로를 순서대로 찾습니다. 찾은 Claude는 `-p --permission-mode plan --max-turns 1`로 worktree 밖의 임시 디렉터리에서 실행합니다. staged diff와 테스트 요약만 prompt로 전달하고 `Edit`, `Write`, `Bash` 도구를 금지합니다.

Claude가 설치되지 않았거나, 로그인/구독이 없거나, read-only 실행이 실패하면 exit code `10`과 `SKIP` 보고서를 남깁니다. worker는 이를 정상적인 optional 단계로 처리해 Codex의 `read-only` self-review로 전환합니다. Claude 리뷰가 성공하면 Codex가 그 보고서를 평가해 유효한 지적만 허용 경로 안에서 최소 수정으로 반영하고, 이후 경로 정책 검사와 재테스트를 다시 통과해야 합니다. 따라서 이후 Claude Pro/Max 로그인만 완료하면 코드 변경 없이 Claude 단계가 자동 활성화됩니다.

## 실패와 복구

| 실패 지점 | 자동 동작 | 복구 방법 |
| --- | --- | --- |
| queue 없음 | 종료 | Issue에 `agent:queued` 라벨을 붙인 뒤 재실행 |
| 필드/경로 검증 실패 | worktree 생성 전 종료 | Issue form을 수정 |
| Codex/테스트/경로 정책 실패 | PR 없이 전용 worktree 보존 | 해당 worktree에서 원인을 검토하고, 필요하면 branch/worktree를 수동 제거한 후 Issue를 재큐잉 |
| Claude unavailable | SKIP 후 Codex self-review | 로그인 후 다음 실행부터 자동 사용 |
| push 또는 Draft PR 생성 실패 | main 불변, task branch/worktree 보존 | GitHub 인증/네트워크를 확인한 뒤 branch에서 수동 PR 생성 또는 새 실행 |

복구 시에도 `main`에서는 `git reset`, `git clean`, `git checkout --force`를 사용하지 않습니다. 전용 작업 디렉터리의 삭제나 branch 정리는 사람이 대상 경로와 PR 상태를 확인한 뒤 수행합니다.

## 수동 승인 지점

1. 사람이 Issue의 허용/금지 경로와 수용 기준을 작성하고 `agent:queued` 라벨을 붙입니다.
2. 사람이 Draft PR의 diff, CI, Codex/Claude review 내용을 검토합니다.
3. 사람이 merge를 명시적으로 승인하고 실행합니다.

worker와 CI에는 auto-merge, deploy, Telegram 발송, 실제 주문 기능이 없습니다.

## 실행

PowerShell에서 로컬 clone의 `main` worktree를 그대로 둔 채 실행합니다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\codex-queue-worker.ps1
```

성공 시에만 해당 Issue용 task branch를 push하고 Draft PR을 만듭니다. 이 저장소 변경을 도입하는 현재 작업은 별도 `automation/agent-queue-v1` 브랜치에서 검토하며, 이 문서 자체는 Draft PR을 자동 생성하지 않습니다.
