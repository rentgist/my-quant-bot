# Primary Worker

**Status (2026-09-29): paused.** Company A now runs the v2 operating model in `../docs/COMPANY_A_V2_OPERATING_MODEL.md`: Claude Code (PM, in the CEO's session) and Codex CLI share implementation and review through the Lead/Partner protocol. Work enters through GitHub Issues and leaves through PRs and CI; no scheduler is involved.

The v1 production execution engine is the PowerShell control plane centered on:

`../scripts/codex-queue-worker.ps1`

It remains in the repository, and its scheduled task may keep publishing the Issue #35 heartbeat. It only executes Issues labelled `agent:queued`, and v2 does not use that label. Reactivating it is a CEO decision.

`.ai-company/` is management documentation only. It does not run tasks and must not introduce another production worker, queue, lifecycle database, merge path, scheduler, or operational source of truth. In particular, no production worker may be created or revived under `scripts/ai_company/`.
