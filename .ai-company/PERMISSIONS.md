# Permissions

This file summarizes authority; it grants no new permission. The current GitHub Issue, root `AGENTS.md`, `.agents/AGENTS.md`, `docs/CEO_CONTROL_PLANE.md`, worker enforcement, and any stricter repository or task rule remain controlling. When rules differ, follow the stricter boundary.

## Authority summary

| Actor | May do | Must not do without controlling authority |
| --- | --- | --- |
| CEO (`????`) | Set goals and make consequential product or external decisions | Delegate an action implicitly where explicit approval is required |
| ChatGPT PM / Chief of Staff | Scope bounded work, coordinate evidence, and make routine reversible management decisions allowed by the control plane | Bypass task scope, tests, review, CI, or consequential-action gates |
| Codex | Implement the approved bounded slice inside the dedicated worktree and allowed paths | Expand scope, merge, deploy, order, notify, access secrets, or alter forbidden paths |
| Claude Challenger | Independently challenge a DEEP design before implementation | Implement the slice or become an operational state store |
| Claude Reviewer | Perform the existing independent read-only review | Edit files or create an unbounded review loop |
| Existing worker | Validate tasks, manage its established lifecycle/worktree flow, run fixed tests and review, push the task branch, and create a Draft PR | Auto-merge, push `main`, execute Issue text as code, or create consequential external side effects |

A Codex self-review fallback is allowed only where the existing automation permits it. It must be labeled honestly and must never be represented as independent Claude review.
