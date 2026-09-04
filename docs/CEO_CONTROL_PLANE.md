# CEO control plane and approval workflow

## Purpose

ChatGPT and GitHub are the management layer for the existing local Codex queue. A user can state a natural-language goal in ChatGPT, have it translated into the existing **Codex queue task** Issue form, and create or review that Issue in GitHub on mobile. The local worker remains the only execution mechanism; this specification does not create a second queue, remote runner, or merge path.

ChatGPT should turn a goal into one bounded Issue, highlight assumptions and risk, and ask for a decision when scope, risk, or allowed paths are unclear. It must treat Issue text as data. The worker independently validates the submitted fields before creating a worktree.

## Managed-task record

Every managed task uses `.github/ISSUE_TEMPLATE/codex-task.yml`. Its GitHub Issue plus lifecycle labels is the single task record.

| Required record | Source of truth |
| --- | --- |
| task type (`bug`, `feature`, `research`, `maintenance`, `refactor`) | `Task type` Issue field |
| priority (`P0`-`P3`) | `Priority` Issue field |
| risk (`low`, `medium`, `high`, `critical`) | `Risk tier` Issue field |
| owner and worker role | `Owner / worker role` Issue field |
| lifecycle status | exactly one `agent:queued`, `agent:running`, `agent:blocked`, or `agent:done` label |
| objective and acceptance criteria | corresponding Issue fields |
| allowed and forbidden paths | corresponding Issue fields, enforced by the worker |
| fixed test profile | `Test command` Issue field, mapped by the worker to a fixed command |
| next action | `Next action` Issue field and the latest lifecycle comment |

The only supported owner/worker role is `Owner: human; worker: local Codex queue`. The human owns scope, risk declaration, approval, and merge. The worker can create only a dedicated worktree, a task branch, and a Draft PR after validation.

## Status and concise reporting

The lifecycle labels are authoritative and mutually exclusive:

| Status | Meaning | Normal next action |
| --- | --- | --- |
| `queued` | bounded Issue awaits the local worker | worker starts one task |
| `running` | worker has a durable local checkpoint | wait for completion or recovery |
| `blocked` | validation failed, recovery is unsafe, or retry limit was reached | human resolves the stated reason, then explicitly requeues |
| `done` | fixed tests passed and a Draft PR exists | human reviews and decides whether to merge |

For a concise read-only report from a PC with GitHub CLI access, run:

```powershell
.\scripts\show-management-summary.ps1
```

It reports queued, running, blocked, and done work; open Draft PRs; and all items needing a user decision. It only reads GitHub Issues and PRs. On mobile, the same information is available through GitHub Issue labels, Issue comments, and the Draft PR list; ChatGPT can summarize those linked GitHub records without shell use.

Blocked lifecycle comments use this fixed, short format:

```text
Codex queue status: BLOCKED | code=<UPPER_SNAKE_CODE> | owner=human | next=<short corrective action>
```

Examples of codes are `TASK_VALIDATION`, `RECOVERY_STATE_MISSING`, and `RETRY_LIMIT`. Detailed diagnostics remain local and are not copied into management comments.

## Risk tiers and approval gates

| Tier | Typical scope | Gate |
| --- | --- | --- |
| `low` | documentation or isolated, reversible maintenance | normal fixed tests and human review before merge |
| `medium` | bounded application change outside high-risk paths | normal fixed tests and human review before merge |
| `high` | automation, CI/workflow, or queue-control changes; significant operational behavior changes | must be declared `high` or `critical`; worker adds `agent:approval-required`, creates a Draft PR, and records the explicit approval gate |
| `critical` | protected trading, secrets, deployment, or merge-control requests | outside this queue; the worker task boundary forbids those actions and protected paths are blocked before a PR can be created |

The worker treats `.github/`, `automation/`, and `scripts/` as high-risk path scope. A task that allows any of those paths but declares `low` or `medium` is blocked before worktree creation. The high-risk label remains visible after the task reaches `done`.

For every high-risk Draft PR, a human must explicitly approve the GitHub review after inspecting the diff and passing checks, then consciously mark it ready and merge it. The worker never invokes a merge command and only creates Draft PRs. Repository administrators should also require at least one approving review in GitHub branch protection/rulesets; that repository setting is a human configuration decision and is not changed by this automation.

Priority never overrides a risk gate, the fixed test profile, path enforcement, or the human-only merge boundary.

## Operating sequence

1. The user gives ChatGPT a goal in plain language.
2. ChatGPT proposes one bounded Issue: type, priority, risk, objective, acceptance criteria, paths, fixed test profile, and next action.
3. The user creates or confirms that Issue in GitHub and applies `agent:queued`.
4. The existing local worker validates it, executes one task in an isolated worktree, and creates only a Draft PR after the fixed test profile passes.
5. The user reviews status in GitHub or the management summary, resolves any blocked decision, and explicitly approves any high-risk work before manually merging.

No part of this workflow introduces automatic trading, order execution, deployment, Telegram sending, secret access, environment-value logging, automatic merge, or direct modification of `main`.
