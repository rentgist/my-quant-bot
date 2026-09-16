# Primary Worker

The single authoritative production execution engine is the existing PowerShell control plane centered on:

`../scripts/codex-queue-worker.ps1`

Its established supporting scripts, GitHub task contract, path enforcement, fixed test profiles, bounded review state machine, lifecycle recovery, branch push, and Draft PR creation remain authoritative.

`.ai-company/` is management documentation only. It does not run tasks and must not introduce another production worker, queue, lifecycle database, merge path, scheduler, or operational source of truth. In particular, no production worker may be created or revived under `scripts/ai_company/`.

All accepted implementation slices, including slices produced by DEEP design work, enter the normal GitHub Issue and PowerShell worker path. The worker does not auto-merge; the existing review, CI, and management decision boundaries remain in force.
