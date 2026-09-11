# TASK-001 — ORION Project Onboarding
Type: HISTORICAL BOOTSTRAP
Status: LOCAL_OUTPUT_REPORTED / GITHUB_IMPORT_PENDING
Priority: ARCHIVED
Owner: MANAGEMENT
Next Agent: NONE
Worker: NOT AN ACTIVE QUEUE ITEM

## Purpose
TASK-001 was the read-only onboarding exercise used while prototyping AI Company OS. It is retained as historical context, not as a production execution queue item.

Production tasks are GitHub Issues processed by the authoritative local Codex queue described in `docs/CEO_CONTROL_PLANE.md` and `.ai-company/PRIMARY_WORKER.md`.

## Original objective
Without changing application code, document the ORION Quant Dashboard structure, execution path, data flow, core investment logic, tests/automation, and known risks at handoff quality.

## Historical local result
During the bootstrap conversation, a local Codex run was reported to have produced:
- `.ai-company/PROJECT_MAP.md`
- `.ai-company/handoffs/TASK-001-CODEX.md`

Those locally reported artifacts are not contained in this consolidated PR. They must not be treated as durable GitHub-verified evidence until they are explicitly imported from the local workspace and reviewed against the current repository.

Claude review/import status is therefore not asserted as complete here.

## Original constraints
- no application-code changes;
- no dependency changes;
- no configuration changes;
- no automatic orders/brokerage access;
- no secret disclosure.

## If the historical artifacts are imported later
Use a bounded GitHub Issue. Verify the files against current `main`, record uncertainty explicitly, and use Claude as an independent Challenger/Reviewer where available. Do not revive the bootstrap Python worker or create a second task queue.

## Archival decision
This file must not use `READY`, `Owner: CODEX`, or another marker that could make it look like an active local queue task. Current work belongs in GitHub Issues.
