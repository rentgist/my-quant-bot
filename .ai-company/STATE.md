# AI Company Project State
Project: ORION Quant Dashboard
Repository: rentgist/my-quant-bot
Layer: MANAGEMENT / GOVERNANCE
Version: 0.2

## Important: this is not live execution state
This file is an orientation document. It must not duplicate or override live operational state.

Use these sources for current truth:
- Worker health / synchronization: GitHub Issue #35
- Active work and lifecycle: current GitHub Issues and lifecycle labels
- Proposed implementation: actual PR diff / changed paths
- Deterministic validation: fixed test evidence and GitHub CI
- Review: Claude/Codex review evidence recorded by the task flow
- Detailed execution contract: `docs/CEO_CONTROL_PLANE.md`

## Current architecture goal
Operate one AI-assisted company with one execution engine:

CEO 준희
→ ChatGPT PM / Chief of Staff
→ GitHub task/state
→ existing local Codex queue worker
→ Codex implementation
→ fixed tests
→ independent Claude review when available
→ bounded correction/final review
→ Draft PR + CI
→ ChatGPT PM management decision

`.ai-company/` provides governance, planning workflows, permissions, handoff conventions, and long-term company memory. It does not own a parallel production queue or worker.

## Bootstrap migration note
PR #62 introduced useful governance concepts but also a lightweight Python worker that duplicated the mature control plane. The consolidated architecture keeps the governance concepts and intentionally excludes the duplicate worker.

TASK-001 was used as a local onboarding/bootstrap exercise. Its locally reported PROJECT_MAP / Codex handoff are not treated as durable GitHub evidence until the artifacts are explicitly imported and independently reviewed.

## Operational next action
Use the current GitHub Issue/PR lifecycle for the next action. During this consolidation, Issue #63 tracks convergence on one authoritative architecture. Control-plane stabilization work such as #49/#61 remains a separate execution concern and must not be hidden by this governance layer.

## CEO decision boundary
Routine reversible repository management stays delegated to ChatGPT PM. Consequential external, financial, destructive, permission, secret, or deployment actions remain CEO-gated as defined in `docs/CEO_CONTROL_PLANE.md`.
