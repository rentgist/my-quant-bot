# Company B State

## STATUS
READY_FOR_LOCAL_VALIDATION

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

## CURRENT_WORK
Validate the independent Company B one-shot worker with `B-TASK-001`.

Implemented on the Company B bootstrap branch:
- isolated architecture and authority model;
- Company B-specific worker namespace;
- one-shot Claude-led worker entrypoint;
- Claude read-only planning -> Codex read-only challenge -> Claude bounded implementation -> fixed tests -> Codex read-only final review;
- at most one bounded Claude correction and one final Codex review;
- Company B-specific local runtime state outside Company A state;
- Company B-specific task branches/worktrees;
- optional push of the isolated Company B task branch after PASS;
- no scheduler/poller yet.

## NEXT_ACTION
On a local PC with subscription-authenticated Claude Code and Codex CLIs, run the Company B worker self-test, then run `B-TASK-001` with `-PushOnPass`. ChatGPT can inspect the pushed Company B task branch afterward without using Company A's queue.

## BLOCKERS
- The new Company B worker has not yet completed its first real local Claude -> Codex round trip.
- No Company B scheduler/poller may be enabled before the one-shot validation succeeds.

## ISOLATION
- Do not mutate Company A active lifecycle, queue, reviewer evidence, or heartbeat.
- Do not use Company A worktree/state directories.
- Do not label Company B bootstrap issues `agent:queued` while Company A's Codex worker owns that lifecycle.
- Company B task branches use the `company-b/task-*` namespace.
- Company B local mutable runtime uses a dedicated `AICompany/company-b/my-quant-bot` namespace.
