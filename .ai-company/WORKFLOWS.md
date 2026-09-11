# Management Workflows

FAST, STANDARD, and DEEP describe management depth. They do not select a different execution engine. Every accepted implementation slice uses the existing GitHub Issue contract and the production PowerShell control plane centered on `scripts/codex-queue-worker.ps1`.

## FAST

Use for small, low-risk, reversible work with clear acceptance criteria. The PM creates one bounded task without a separate design-challenge phase. Codex implementation, path enforcement, the Issue-selected fixed test profile, existing bounded review, Draft PR, and CI safeguards still apply.

## STANDARD

Use for normal bounded implementation work:

1. The PM defines one Issue with objective, acceptance criteria, risk, allowed and forbidden paths, fixed test profile, and next action.
2. The existing worker creates or recovers the dedicated task worktree and invokes Codex for bounded implementation.
3. Changed-path enforcement and fixed tests run.
4. Claude performs the initial independent read-only implementation review when available.
5. An initial Claude `PASS` ends review; no redundant final Claude review runs.
6. An initial Claude `CHANGES_REQUESTED` permits exactly one Codex minimal-correction turn within the allowed paths.
7. After that turn, changed-path enforcement and fixed tests run again, followed by exactly one final Claude review.
8. A final `CHANGES_REQUESTED` blocks automation and returns the task to management; there is no further model-to-model correction loop.
9. When Claude is unavailable, only the fallback already permitted by existing automation may run. It must be recorded as `Codex self-review` and never described as independent Claude review.
10. Every review result must be preserved as durable GitHub-visible evidence with an explicit top-level `PASS` or `CHANGES_REQUESTED` verdict. A model route or local report filename alone is insufficient.
11. On successful completion, the existing worker pushes only the task branch and creates or preserves a Draft PR. CI and the management decision remain separate; the worker never auto-merges.

## DEEP

Use when architecture, safety, ambiguity, or cross-cutting impact merits independent design challenge.

1. The PM prepares a bounded proposed design and scope.
2. Claude, when available, acts as an independent Challenger before implementation, testing assumptions, interfaces, risks, failure modes, and whether the work should be split.
3. The PM resolves the challenge and records an accepted bounded implementation slice in the normal GitHub Issue contract. The challenge is advisory design evidence, not a queue or lifecycle record.
4. Each accepted slice then follows the complete STANDARD worker, path-check, fixed-test, implementation-review, Draft PR, and CI path.

DEEP adds deliberation before implementation; it does not weaken safeguards or authorize a second worker, queue, database, review loop, or merge path.
