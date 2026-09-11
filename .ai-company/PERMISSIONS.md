# Permissions
Version: 0.2

This file summarizes authority. It does not override stricter repository or task-specific safety rules.

| Action | Codex | Claude | Local worker | ChatGPT PM | CEO |
|---|---|---|---|---|---|
| Read repository | ALLOW | ALLOW | ALLOW | ALLOW | ALLOW |
| Edit bounded task worktree | ALLOW within task scope | DENY in reviewer mode | manages worktree only | management-only corrections when justified | ALLOW |
| Run fixed tests/backtests | ALLOW through task flow | read-only validation only | ALLOW | inspect evidence | ALLOW |
| Commit/push task branch | DENY directly | DENY | ALLOW after safeguards | CONDITIONAL management action | ALLOW |
| Create Draft PR | DENY directly | DENY | ALLOW after safeguards | ALLOW | ALLOW |
| Merge `main` | DENY | DENY | DENY | ALLOW only for routine reversible repo work after evidence | consequential decision authority |
| Change dependencies/config | only when explicitly scoped | REVIEW ONLY | enforce scope | CONDITIONAL | APPROVAL if material/consequential |
| Delete important data/files | DENY unless explicitly and safely authorized | DENY | DENY by default | consequential approval required | APPROVAL REQUIRED |
| Spend money / paid API | DENY | DENY | DENY | DENY without CEO decision | APPROVAL REQUIRED |
| Live trading / brokerage order | FORBIDDEN | FORBIDDEN | FORBIDDEN | FORBIDDEN | separate explicit authorization/constitution change required |
| Production deploy / external notification | FORBIDDEN in routine worker | FORBIDDEN | FORBIDDEN | explicit CEO authorization required | APPROVAL REQUIRED |
| Reveal/copy secrets | FORBIDDEN | FORBIDDEN | FORBIDDEN | FORBIDDEN | FORBIDDEN as a logging/disclosure action |

## Secrets and billing
- API keys, tokens, passwords, brokerage credentials, raw stderr, raw agent output, and local identifying paths must not be written into task/handoff/review/diagnostic records.
- The local agent path is intended to use authenticated Codex CLI / Claude Code subscription sessions rather than paid API-key calls.
- Environment variables or GitHub Secrets may exist for unrelated repository functions; they are not permission for agents to read or disclose them.

## Primary Worker
There is exactly one authoritative production execution engine: the existing local Codex queue based on `scripts/codex-queue-worker.ps1` and its scheduled wrapper/supporting scripts. Additional experimental/bootstrap workers are not production authority.
