# Company B operations

## Current phase

Company B is in **manual one-shot validation**. Do not enable a scheduler or reuse Company A's queue yet.

## Company identities

| Company | Director / implementer | Independent reviewer | Mutable operational state |
| --- | --- | --- | --- |
| A | GPT / Codex | Claude Code | Company A control plane |
| B | Claude Code | GPT / Codex | Company B-only runtime and task records |

## First-run sequence

1. Fetch the Company B bootstrap branch.
2. Run the worker self-test.
3. Run `B-TASK-001` with `-PushOnPass`.
4. Do not start Company A's worker against Company B task records.
5. On PASS, inspect the pushed `company-b/task-b-task-001` branch and verify that only the probe document changed.
6. Only then design Company B health reporting and remote queueing.

## PowerShell

```powershell
git fetch origin
git switch company-b/bootstrap-claude-led-v0.1
git pull

powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\company_b\company-b-worker.ps1 -SelfTest

powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\company_b\company-b-worker.ps1 `
  -TaskSpec .\companies\company-b\tasks\B-TASK-001.json `
  -PushOnPass
```

The worker resolves `claude.cmd` before `claude` on Windows, avoiding the PowerShell execution-policy problem that can block the npm-generated `claude.ps1` shim.

## Expected B-TASK-001 result

The pushed task branch must contain exactly one task change:

`docs/company-b/BOOTSTRAP_PROBE.md`

The fixed test requires the markers:

```text
COMPANY: B
DIRECTOR: Claude Code
REVIEWER: Codex / GPT
STATUS: bootstrap-probe
```

Codex must independently return `VERDICT: PASS`. If Codex requests changes, the worker permits exactly one bounded Claude correction and one final Codex review.

## Safety boundary

The worker never auto-merges. It does not consume `agent:queued`, does not write Company A heartbeat/lifecycle, and has built-in forbidden paths for Company A worker scripts and critical ORION files.
