# Primary Worker
Version: 0.2
Status: AUTHORITATIVE EXISTING CONTROL PLANE

## Authoritative engine
The production Primary Worker is the existing PowerShell control plane centered on:

- `scripts/codex-queue-worker.ps1`
- `scripts/run-codex-queue-scheduled.ps1`
- the existing lifecycle/diagnostic/review helper scripts

`docs/CEO_CONTROL_PLANE.md` is the detailed behavioral contract. `.ai-company/` is a governance and planning layer; it does not implement a second production worker.

## Durable task state
Production work is represented by GitHub Issues using the validated Codex task contract and lifecycle labels:

- `agent:queued`
- `agent:running`
- `agent:blocked`
- `agent:done`

`agent:approval-required` is an additional risk/visibility gate, never a bypass. Persistent worker health is published to Issue #35.

## Normal execution
1. CEO states the goal to ChatGPT.
2. ChatGPT PM / Chief of Staff scopes a bounded GitHub Issue.
3. The local worker validates the Issue and creates/recovers a dedicated task worktree/branch.
4. Codex implements only within allowed scope using explicit model routing.
5. The worker enforces changed paths and runs a fixed test profile.
6. Claude performs independent read-only review when available.
7. If Claude requests changes, Codex receives at most one bounded correction turn, followed by path checks/tests and one final Claude review.
8. If final review still requests changes, automation stops and escalates; there is no unbounded loop.
9. The worker pushes the task branch and creates a Draft PR only after required safeguards pass.
10. CI runs on the PR.
11. ChatGPT PM reviews scope, diff, tests, review evidence, and CI and may make a routine reversible repository merge decision under standing delegation.

The local worker itself never merges `main`.

## Claude availability
Claude is the preferred independent reviewer. If Claude is unavailable/unauthenticated, the existing read-only Codex self-review fallback may be used only when the automation allows it. Evidence must identify the fallback honestly; it must never be described as independent Claude review.

## Billing / login
- Codex CLI and Claude Code are intended to use authenticated subscription sessions.
- A paid OpenAI/Anthropic API-key path is not required for the Primary Worker.
- Agent automation must not read, print, copy, or persist secrets.

## No duplicate worker
The bootstrap `scripts/ai_company/worker.py` and `scripts/ai_company/run_worker.ps1` experiment from PR #62 are not part of the consolidated production architecture and must not be introduced as a parallel queue, lifecycle, or execution engine.

## Multi-PC
Additional PCs remain standby until explicit task locking/concurrency behavior is designed and tested against the authoritative worker. Do not run competing production workers against the same queue before that point.
