# Company B worker namespace

This directory contains the independent Claude-led Company B execution engine.

Company B is intentionally **not** a mode flag inside Company A's production worker. It has separate task records, local runtime state, task branches/worktrees, and evidence.

## Role assignment

- primary technical director / architect: Claude Code
- primary implementer: Claude Code
- independent challenger / reviewer: Codex / GPT
- human-facing PM / Chief of Staff: ChatGPT
- CEO / consequential decisions: user

## One-shot workflow

`company-b-worker.ps1` performs one bounded task at a time:

```text
Company B task spec
  -> Claude read-only plan
  -> Codex read-only challenge
  -> Claude bounded implementation
  -> allow/forbidden-path enforcement
  -> fixed deterministic tests
  -> Codex read-only final review
  -> optional one Claude correction
  -> fixed tests again
  -> final Codex review
  -> local Company B task commit
  -> optional isolated task-branch push
```

There is deliberately no Company B scheduler/poller yet. One-shot validation must pass first.

## Isolation from Company A

The Company B worker does not consume Company A's `agent:queued` lifecycle and does not write Company A heartbeat, lifecycle, reviewer evidence, or `.ai-company/` state.

Company B uses:

- task records: `companies/company-b/tasks/`
- worker: `scripts/company_b/company-b-worker.ps1`
- branches: `company-b/task-*`
- local runtime namespace: `AICompany/company-b/my-quant-bot`
- dedicated Git worktrees under the Company B runtime root by default

The built-in forbidden paths include Company A's production worker scripts and critical ORION files.

## Authentication

Use the already authenticated native subscription CLIs:

- Claude Code: `claude.cmd` / `claude`
- Codex: `codex`

The worker does not require `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` and does not log secrets.

## First validation

From the repository root on the local PC:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\company_b\company-b-worker.ps1 -SelfTest
```

Then run the first real Company B task:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\company_b\company-b-worker.ps1 `
  -TaskSpec .\companies\company-b\tasks\B-TASK-001.json `
  -PushOnPass
```

`B-TASK-001` is intentionally tiny. It creates only `docs/company-b/BOOTSTRAP_PROBE.md`, runs a fixed probe test, and requires a final independent Codex PASS. Its purpose is to validate the Claude-led company loop without touching Company A or ORION logic.

On PASS, `-PushOnPass` pushes only the isolated `company-b/task-b-task-001` branch. It never merges to `main`.

## After the first PASS

Only after the one-shot round trip succeeds should Company B gain:

1. GitHub-visible Company B health evidence;
2. a Company B-specific remote task queue;
3. optional scheduling/polling;
4. the neutral A-vs-B benchmark dispatcher.

Do not reuse Company A's mutable task lifecycle for these steps.
