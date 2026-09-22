# Company B State

## STATUS
OPERATIONAL_BUILD

## COMPANY
CLAUDE_LED

## PRIMARY_DIRECTOR
Claude Code

## PRIMARY_IMPLEMENTER
Claude Code

## INDEPENDENT_REVIEWER
Codex / GPT

## HUMAN_FACING_PM
ChatGPT

## OPERATIONAL_SOURCE_OF_TRUTH
This file plus Company B-specific task/runtime/evidence records only. Company A lifecycle, heartbeat, queue, and reviewer-evidence files are not Company B state.

## VALIDATED_BOOTSTRAP
B-TASK-001 completed the isolated end-to-end round trip successfully.

Evidence:
- base SHA: `31b2b760b943c029f96a56eec873f1d71c9d76a0`
- result commit: `72e6aebeda824bf8772334081951719c3f54b98a`
- result branch: `company-b/task-b-task-001`
- Claude planning: PASS
- Codex challenge/review path: PASS
- fixed tests: PASSED
- final Codex verdict: PASS
- remote result branch push: succeeded
- exactly one bounded task file changed

## CURRENT_WORK
Complete Company B as an independently operable Claude-led control plane before the final Codex architecture audit.

Phase 1 is in progress on `company-b/operational-v0.1`:
- promote validated Claude planning turn budget into the authoritative worker;
- promote Windows-safe Codex invocation into the authoritative worker;
- remove reliance on bootstrap-time source patching for normal execution.

## NEXT_ACTION
Validate the authoritative `scripts/company_b/company-b-worker.ps1` directly on the local PC, without the bootstrap runner. After that passes, add the Company B-specific remote queue/lifecycle and Draft-PR/evidence path.

## BLOCKERS
- Company B does not yet have a production remote queue/lifecycle.
- Company B does not yet publish exact-head durable Codex reviewer evidence.
- Company B does not yet have its own scheduler/mutex/heartbeat.
- Final independent Codex architecture audit has not been run.

## ISOLATION
- Do not mutate Company A active lifecycle, queue, reviewer evidence, or heartbeat.
- Do not use Company A worktree/state directories.
- Do not label Company B issues `agent:queued` while Company A owns that lifecycle.
- Company B task branches use the `company-b/task-*` namespace.
- Company B local mutable runtime uses a dedicated `AICompany/company-b/my-quant-bot` namespace.
- No auto-merge.
- No direct agent push to `main`.
