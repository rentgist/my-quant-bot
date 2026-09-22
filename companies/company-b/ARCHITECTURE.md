# Company B — Claude-led AI Company

## Purpose

Company B is an independent experimental AI-company organization used to compare a Claude-led engineering company against the existing GPT/Codex-led Company A.

Company B must remain operationally isolated from Company A. It may share the same repository contents and may later receive the same immutable benchmark task specification from the same base commit, but it must not share mutable lifecycle state, worker state, task queues, logs, review evidence, branches, or worktrees with Company A.

## Roles

- CEO / human decision maker: user
- Human-facing PM / Chief of Staff: ChatGPT
- Primary technical director / architect: Claude Code
- Primary implementer: Claude Code
- Independent challenger / reviewer: Codex / GPT
- Deterministic QA: fixed tests / CI

## Normal workflow

```text
CEO goal
  -> ChatGPT PM scopes a bounded Company B task
  -> Company B task record
  -> Claude investigation / plan
  -> Codex read-only challenge
  -> Claude response / synthesis
  -> Claude implementation in Company B isolated worktree
  -> fixed tests
  -> Codex independent read-only review
  -> at most one bounded Claude correction
  -> fixed tests again
  -> one final Codex review when correction occurred
  -> Company B Draft PR / evidence
  -> ChatGPT PM compares or manages outcome
```

Claude does not gain broader authority merely because it is the director. All write permissions remain worktree- and path-bounded.

## Isolation from Company A

Company B must not:

- consume Company A's `agent:queued` lifecycle;
- write Company A lifecycle or heartbeat state;
- reuse Company A local mutable state directories;
- modify Company A production worker scripts during bootstrap;
- read Company A generated task results during a paired benchmark before both companies finish;
- auto-merge to `main`.

Company B uses:

- repository namespace: `companies/company-b/`
- worker namespace: `scripts/company_b/`
- execution branches: `company-b/task-*`
- dedicated worktrees separate from Company A worktrees
- Company B-specific state/evidence paths defined by the Company B worker

## Safety invariants

- no direct agent write/push to `main`;
- no auto-merge;
- allowed/forbidden path enforcement;
- fixed test profiles instead of arbitrary issue shell commands;
- bounded model-to-model planning and correction loops;
- Codex reviewer is read-only;
- no live trading/order execution;
- no production deployment side effects;
- no external customer/third-party notifications;
- no secret/token/password disclosure or logging;
- use subscription-authenticated local `claude`/`claude.cmd` and `codex` CLIs only; no API-key billing dependency.

## Paired benchmark policy

A paired benchmark may begin only after Company A and Company B are independently operational.

The neutral dispatcher must freeze one normalized task spec and one base SHA, then copy that immutable input independently to both companies.

- Company A: GPT/Codex directs and implements; Claude challenges/reviews.
- Company B: Claude directs and implements; GPT/Codex challenges/reviews.

Neither company may read the other's generated plan, diff, review, or metrics until both reach a terminal state. Comparison happens only afterward.