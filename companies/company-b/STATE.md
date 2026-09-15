# Company B State

## STATUS
BOOTSTRAP_DESIGN

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
This file and future Company B-specific task/evidence records only. Company A lifecycle/heartbeat files are not Company B state.

## CURRENT_WORK
Bootstrap the independent Company B worker namespace and one-shot validation path.

## NEXT_ACTION
Implement a Company B-specific manual worker entrypoint under `scripts/company_b/` that invokes Claude as bounded director/implementer and Codex as read-only reviewer without consuming Company A's queue.

## BLOCKERS
- Company B worker is not implemented yet.
- No Company B scheduler/poller should be enabled before one-shot validation succeeds.

## ISOLATION
- Do not mutate Company A active lifecycle or heartbeat.
- Do not use Company A worktree/state directories.
- Do not label Company B bootstrap issues `agent:queued` while Company A's Codex worker owns that lifecycle.
