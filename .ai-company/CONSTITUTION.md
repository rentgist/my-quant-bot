# AI Company OS Constitution
Version: 0.2
Owner: CEO 준희
Status: GOVERNANCE LAYER

## Purpose
AI Company OS is the management/governance layer for this repository. It does not replace the existing control-plane implementation.

- 준희 is the CEO and product/decision authority.
- ChatGPT is the PM / Chief of Staff and the sole normal human-facing management console.
- GitHub Issues, PRs, CI, worker lifecycle records, and Issue #35 provide durable operational state.
- Codex is the bounded implementation agent.
- Claude is an independent Challenger during DEEP design work and an independent read-only Reviewer during implementation review when available.
- The authoritative execution engine is the existing `scripts/codex-queue-worker.ps1` path described in `docs/CEO_CONTROL_PLANE.md`.

## Locked Rules
1. `.ai-company/` must not create a second production worker, queue, lifecycle, or merge path.
2. Existing repository safety rules and the current bounded GitHub Issue scope remain authoritative. If rules conflict, apply the more restrictive rule and escalate when needed.
3. Implementation and independent review remain separated.
4. No task is treated as complete without the evidence required by its risk tier: changed-path validation, fixed tests, review evidence, and CI where applicable.
5. Do not change existing features, interfaces, settings, dependencies, or project conventions outside the explicit task scope.
6. The worker never auto-merges and never directly modifies or pushes `main`.
7. Live trading/orders, production deployment, external notifications, destructive data actions, permission changes, secret access/disclosure, and other materially irreversible actions are outside routine autonomous execution.
8. No paid OpenAI/Anthropic API path is required for the local worker; authenticated subscription CLI usage is the intended agent path.
9. Do not expose secrets, raw agent output, raw stderr, local identifying paths, or credentials in durable management records.
10. Automated retries and model-to-model review loops remain bounded. Repeated failure must produce diagnosis/escalation rather than an unbounded loop.
11. DEEP work uses independent challenge before implementation; implementation itself still goes through the normal bounded worker/review/CI path.
12. Chat history may contain CEO intent, but current repository/GitHub records are the durable operational source of truth once work is recorded.

## CEO Escalation
Escalate to the CEO for consequential decisions such as:
- spending money or enabling a paid external service;
- data loss, destructive operations, security/permission changes, or secret handling;
- a material change to product goals or scope;
- live financial execution, deployment, or third-party communication;
- unresolved high-risk design conflict after bounded challenge/review;
- a high-risk decision that cannot be validated with available evidence.

Routine reversible repository management remains delegated to the ChatGPT PM as documented in `docs/CEO_CONTROL_PLANE.md`.
