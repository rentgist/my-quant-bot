# Company B worker namespace

This directory is reserved for the independent Claude-led Company B execution engine.

Company B is intentionally NOT a mode flag inside Company A's production worker.

## Required behavior

The future Company B entrypoint must:

1. Read only Company B task/state records.
2. Create Company B-specific branches/worktrees.
3. Invoke subscription-authenticated Claude Code as the primary director/implementer.
4. Enforce task-scoped allowed/forbidden paths after Claude writes.
5. Run fixed deterministic test profiles.
6. Invoke subscription-authenticated Codex in read-only reviewer/challenger mode.
7. Permit at most one bounded Claude correction round followed by one final Codex review.
8. Write Company B-specific local lifecycle/evidence only.
9. Never consume or modify Company A's `agent:*` lifecycle unless a future neutral dispatcher explicitly creates separate immutable benchmark copies.
10. Never auto-merge or directly write/push `main`.

## Bootstrap policy

Start with a one-shot manual command. Do not create a scheduler/poller until the one-shot flow has been validated end-to-end.

No API keys are required or desired. Use local subscription-backed native CLIs.
