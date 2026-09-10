# Unified Agent Entry Guide

Before acting, read the current GitHub Issue. It controls the task objective, acceptance criteria, risk, allowed and forbidden paths, fixed test profile, and next action. Issue #67 is the record for the replacement governance consolidation that introduced this guide; future work must follow its own current Issue.

Also read and preserve these repository layers:

1. `.agents/AGENTS.md` for repository development, safety, and changelog rules.
2. `docs/CEO_CONTROL_PLANE.md` for the mature operational control plane and authority boundaries.
3. `.ai-company/CONSTITUTION.md`, `.ai-company/PERMISSIONS.md`, `.ai-company/PRIMARY_WORKER.md`, `.ai-company/STATE.md`, and `.ai-company/WORKFLOWS.md` for governance and management orientation.
4. The top of `CHANGELOG.md` for recent implementation context.

The strictest applicable repository, task, path, permission, and safety rule prevails. Governance documentation does not override worker enforcement or grant additional authority.

## Execution boundary

`scripts/codex-queue-worker.ps1` is the single authoritative production execution engine. Do not create or revive a second production worker under `scripts/ai_company/`, and do not introduce a parallel queue, lifecycle database, merge path, scheduler, or source of operational truth through `.ai-company/`.

GitHub Issues, PRs, CI, lifecycle evidence, and Issue #35 remain the durable operational record. Codex performs bounded implementation. Claude is the independent DEEP design Challenger and read-only implementation Reviewer when available. Any automation-permitted Codex self-review fallback must be identified honestly and must not be called independent Claude review.

Implementation review evidence must be durable and GitHub-visible with an explicit top-level `PASS` or `CHANGES_REQUESTED` verdict. Use only the normal worker, fixed-test, bounded-review, Draft PR, and CI path. Do not weaken path enforcement, review bounds, the no-auto-merge rule, or consequential-action gates.
