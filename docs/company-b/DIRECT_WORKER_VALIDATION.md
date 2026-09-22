# Company B direct-worker validation (B-TASK-002)

This record validates that the authoritative Company B worker, `scripts/company_b/company-b-worker.ps1`, completes a real Claude-led, Codex-reviewed round trip on its own, without the temporary `run-bootstrap-task.ps1` wrapper used for earlier probes.

```text
COMPANY: B
EXECUTION: authoritative-worker
DIRECTOR: Claude Code
REVIEWER: Codex / GPT
STATUS: validation-pass
```

## Execution path

`run-bootstrap-task.ps1` is not part of the execution path for this validation. This task ran directly through the authoritative `scripts/company_b/company-b-worker.ps1`, with Claude Code as director and Codex / GPT as independent reviewer.

## Scope boundary

Company A's mutable queue, lifecycle, heartbeat, runtime, branches, and worktrees are out of scope for this validation and must remain untouched.

## Evidence

- The fixed pytest profile passed for this task.
- The final independent Codex review returned `VERDICT: PASS`.
