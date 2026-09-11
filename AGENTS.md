# ORION AI Agent Entry Rules

This repository has one production control plane. `.ai-company/` is a governance/planning layer and must not override or duplicate the existing execution engine.

## Read first
1. Current GitHub Issue: objective, acceptance criteria, risk, lifecycle, allowed/forbidden paths, fixed test profile.
2. `docs/CEO_CONTROL_PLANE.md`
3. `.agents/AGENTS.md`
4. `.agents/rules/strict_verification.md`
5. `.ai-company/CONSTITUTION.md`
6. `.ai-company/PERMISSIONS.md`
7. `.ai-company/WORKFLOWS.md`
8. `AI_CONTEXT.md`
9. `CHANGELOG.md` latest relevant entries.

## Source-of-truth rules
- Live task state: GitHub Issue/lifecycle labels.
- Worker health/synchronization: Issue #35.
- Proposed code: actual task branch/PR diff.
- Validation: fixed test result and GitHub CI.
- Review: recorded Claude/Codex review evidence.
- Detailed execution contract: `docs/CEO_CONTROL_PLANE.md` and the actual scripts on `main`.
- `.ai-company/STATE.md` is orientation only; it is not a competing live-state database.
- Chat can contain CEO intent, but durable operational decisions should be reflected in GitHub/repository records.

## Production worker
The authoritative execution engine is the existing PowerShell Codex queue centered on `scripts/codex-queue-worker.ps1`. Do not create, revive, or expand a second production worker/queue/lifecycle under `scripts/ai_company/` or `.ai-company/`.

## Roles
- 준희: CEO / product and consequential decision authority.
- ChatGPT: PM / Chief of Staff / normal human-facing management console.
- Codex: bounded implementation agent.
- Claude: independent Challenger for DEEP design and read-only Reviewer for implementation when available.
- CI: deterministic QA.
- Local worker: execution mechanism; never final merge authority.

## Non-negotiable
- More restrictive safety/task rules win when documents conflict.
- No worker auto-merge and no direct worker/Codex modification or push of `main`.
- No live trading/orders, production deploy, external notifications, destructive/permission actions, or secret handling through routine autonomous tasks.
- Do not evaluate arbitrary Issue text as shell commands.
- Respect dedicated worktree, allow/forbidden paths, fixed tests, bounded retries/reviews, explicit model routing, and approval gates.
- Claude-unavailable Codex self-review fallback must be labeled honestly and never represented as independent Claude review.
- Development changes must follow `.agents/AGENTS.md`, including the repository CHANGELOG requirement.
