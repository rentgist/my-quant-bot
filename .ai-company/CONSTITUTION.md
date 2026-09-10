# AI Company Constitution

## Purpose

`.ai-company/` is the repository's governance, planning, and orientation layer. It documents how the AI-assisted organization is managed. It does not replace, modify, or independently implement the existing production control plane centered on `scripts/codex-queue-worker.ps1`.

This layer must not become a second production worker, queue, lifecycle database, merge path, or competing source of truth.

## Roles

- `????` is the CEO with authority over product direction and consequential decisions.
- ChatGPT is the PM / Chief of Staff and the normal human-facing management console.
- GitHub Issues, PRs, CI, lifecycle records, and Issue #35 provide durable operational state.
- Codex is a bounded implementation agent operating only within an approved task and path scope.
- Claude is the independent Challenger for DEEP design work and the independent read-only implementation Reviewer when available.
- When existing automation permits a Codex read-only self-review fallback, evidence must identify it as `Codex self-review`; it is not independent Claude review.

## Operating principles

1. The current GitHub Issue defines the objective, acceptance criteria, risk, allowed and forbidden paths, fixed test profile, and next action.
2. Accepted implementation work runs through the existing PowerShell worker, path enforcement, fixed tests, bounded review, Draft PR, and CI flow.
3. The worker never auto-merges or directly modifies or pushes `main`.
4. Governance documents may clarify management intent but may not claim that unimplemented automation exists.
5. Stricter repository, task, safety, and permission rules always prevail.
6. Live trading, deployment, destructive actions, permission changes, secret access, and other consequential external actions require the authority specified by the existing control plane.

## Sources of truth

Operational truth remains in the current GitHub Issue, its lifecycle, the actual PR diff, fixed-test evidence, review evidence, CI, and Issue #35 worker health. Chat history and `.ai-company/` files are explanatory context, not substitutes for those records.
