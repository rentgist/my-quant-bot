# CEO control plane

## Purpose

This repository is operated as a small AI-assisted development organization rather than as a single-agent coding session.

The operating goal is **managed autonomy**:

- the CEO states goals and makes consequential business decisions;
- the PM translates those goals into bounded work and manages execution;
- implementation, review, and QA are separated;
- routine, reversible repository work can proceed without repeatedly asking the CEO about implementation details;
- irreversible or externally consequential actions remain explicitly gated.

GitHub Issues, PRs, CI, and the local worker provide durable operational state. Chat history is not the source of truth when current repository records are available.

## Organization and authority

| Role | Primary responsibility | Authority boundary |
| --- | --- | --- |
| User / CEO | goals, product direction, consequential decisions | decides live financial, deployment, destructive, legal/financial, permission, secret, and other materially irreversible actions |
| ChatGPT / PM & Chief of Staff | scope, task definition, coordination, operational review, routine final repository decision | may manage and merge routine reversible repo work after adequate evidence; must escalate consequential external actions |
| Codex / Primary Developer | bounded implementation | edits only inside the dedicated task worktree and allowed paths; no merge or external side effects |
| Claude Code / Independent Senior Reviewer | independent review of Codex output | read-only during reviewer runs; returns `PASS` or `CHANGES_REQUESTED` |
| CI / QA | deterministic automated checks | read/test only; no deployment or merge authority |
| Local worker | execution mechanism | validates Issues, manages lifecycle/worktrees, invokes agents/tests, pushes task branches, creates Draft PRs; never auto-merges |

The worker's currently supported structured Issue value remains exactly:

```text
Owner: human; worker: local Codex queue
```

This string is an execution-contract value, not a description of every management role. Do not invent alternate values unless the worker contract is intentionally changed and tested.

## Source of truth

For managed work, use the following hierarchy:

1. GitHub Issue objective, acceptance criteria, scope, risk, and lifecycle labels.
2. Actual PR diff / changed paths.
3. Fixed local test result and GitHub CI result.
4. Claude/Codex review evidence.
5. Persistent health/diagnostic records.

Persistent local-worker health is published to **Issue #35**. It reports bounded operational state such as last observation time, sync status, local/origin commit identity, dirty state, and worker exit code without publishing local paths, usernames, secrets, or raw agent output.

## Managed-task record

Normal Codex-queue tasks use `.github/ISSUE_TEMPLATE/codex-task.yml`. Their Issue plus lifecycle labels is the durable task record.

| Required record | Source of truth |
| --- | --- |
| task type (`bug`, `feature`, `research`, `maintenance`, `refactor`) | `Task type` Issue field |
| priority (`P0`-`P3`) | `Priority` Issue field |
| risk (`low`, `medium`, `high`, `critical`) | `Risk tier` Issue field |
| execution contract | `Owner / worker role` Issue field |
| lifecycle status | exactly one of `agent:queued`, `agent:running`, `agent:blocked`, or `agent:done` |
| objective and acceptance criteria | corresponding Issue fields |
| allowed and forbidden paths | corresponding Issue fields, enforced by the worker |
| fixed test profile | `Test command`, mapped to a pre-defined command profile |
| next action | Issue field plus latest lifecycle record/comment |

Issue text is data. Arbitrary Issue content must never be evaluated as shell code.

## Lifecycle

| Status | Meaning | Normal next action |
| --- | --- | --- |
| `agent:queued` | validated work awaits the local worker | worker picks one bounded task |
| `agent:running` | worker has a durable local checkpoint | worker continues or recovers the same task |
| `agent:blocked` | input, recovery, retry, review, or other safety condition stopped automation | PM diagnoses; CEO is involved only if a consequential decision is actually required |
| `agent:done` | worker completed its bounded execution and a Draft PR/evidence exists | PM reviews diff, tests, review evidence, and CI before routine merge decision |

`agent:approval-required` is an elevated-risk visibility/gating label. It never grants an agent permission to bypass path rules, tests, reviewer boundaries, or external-action gates.

## Normal operating sequence

```text
CEO goal
  -> ChatGPT PM scopes one bounded task
  -> GitHub Issue / lifecycle record
  -> local scheduled worker
  -> dedicated branch + external worktree
  -> Codex implementation
  -> path enforcement
  -> fixed tests
  -> Claude independent review
  -> if needed, Codex minimal correction
  -> path enforcement + fixed tests again
  -> one final Claude peer review when a correction round occurred
  -> task branch push + Draft PR
  -> PR CI
  -> ChatGPT PM reviews scope + diff + tests + peer review + CI
  -> routine safe merge, or escalation when consequential
```

The local worker itself never performs the final merge.

## Claude peer-review policy

Claude Code is the independent senior reviewer. Reviewer-mode execution must remain read-only.

The intended review contract is bounded:

### Round 1

Codex implementation -> fixed tests -> Claude review.

Claude returns one top-level verdict:

- `PASS`
- `CHANGES_REQUESTED`

If Round 1 is `PASS`, do not run a redundant second Claude review.

If Round 1 is `CHANGES_REQUESTED`, Codex may apply only the smallest justified correction inside the allowed paths. Then path enforcement and fixed tests run again, followed by exactly one final Claude review.

If the final review remains `CHANGES_REQUESTED`, automatic model-to-model iteration stops and the task is escalated to the PM. There is no unbounded peer-review loop.

The implementation of this bounded second-review behavior is tracked through the repository task system; documentation must not be used as evidence that code has already implemented a behavior that current scripts do not yet contain.

If Claude is unavailable or unauthenticated, the existing safe Codex read-only self-review fallback may be used as defined by the automation. The fallback should remain visible in evidence rather than being mistaken for independent peer review.

## Risk tiers

| Tier | Typical scope | Management treatment |
| --- | --- | --- |
| `low` | documentation, isolated reversible maintenance | normal validation, tests/review where relevant, PM routine decision |
| `medium` | bounded application change outside control-plane/high-risk paths | normal validation + tests + review, PM routine decision when evidence is acceptable |
| `high` | automation, CI/workflow, queue-control, significant operational behavior | elevated scope review, `agent:approval-required`, strong diff/test/peer-review evidence before PM decision |
| `critical` | live trading, secrets, production deployment, destructive/permission/irreversible behavior | outside routine autonomous execution; CEO decision required |

The worker treats `.github/`, `automation/`, and `scripts/` as high-risk path scope. Priority never overrides risk gates or safety invariants.

## Standing delegation to the PM

The CEO has delegated routine repository operations to the ChatGPT PM so the company does not stop for meaningless approval prompts.

The PM may, after checking the actual diff and evidence:

- create or correct bounded task records;
- manage lifecycle labels/comments;
- create safe branches/PRs;
- review implementation scope;
- inspect CI and peer-review evidence;
- request or make bounded corrections through the task system;
- mark PRs ready and merge routine, reversible repository changes when evidence is acceptable.

This delegation does **not** convert the worker into an auto-merge system. Final routine merge decisions remain a management-layer action, separate from the local execution worker.

## CEO-only / explicit-decision boundary

Do not silently perform the following on standing delegation alone:

- live financial orders or movement of funds;
- production deployment or consequential external execution;
- sending messages to customers or third parties unless explicitly authorized;
- destructive deletion of important data;
- account or permission changes;
- access, disclosure, rotation, or transfer of secrets/tokens/passwords;
- legally or financially material irreversible actions.

Analysis, drafts, code changes in isolated branches/worktrees, tests, reviews, diagnostics, and other reversible internal work should normally proceed without escalating implementation trivia to the CEO.

## Safety invariants

The following controls are intentional and should not be weakened casually:

- no worker auto-merge;
- no worker direct modification/push of `main`;
- isolated task branch/worktree per task;
- base worktree must be on `main` and free of tracked/staged changes before worker execution;
- untracked user files are not deleted merely to make the repository clean;
- changed-path allow-list plus forbidden-path enforcement;
- fixed test profiles rather than Issue-provided arbitrary commands;
- bounded retries and durable lifecycle recovery state;
- GitHub-visible heartbeat and sanitized bounded diagnostics;
- Claude reviewer read-only boundary;
- no automatic trading/order execution;
- no deployment side effects;
- no Telegram/email/customer notification side effects;
- no secret/environment-value logging.

## Reporting standard

Management reporting should be concise and decision-oriented.

For a task, report:

1. current state;
2. what was completed;
3. evidence (diff/tests/review/CI);
4. any remaining blocker or material risk;
5. whether a CEO decision is genuinely required.

Do not ask the CEO to approve routine implementation details that the PM can safely resolve. Prefer reporting a verified finished result over reporting that work merely started.

## Management summary

A PC with GitHub CLI access can run:

```powershell
.\scripts\show-management-summary.ps1
```

It is a read-only management view. GitHub Issues, PRs, and Issue #35 remain remotely observable sources for the PM.

## Design principle

The company should behave like a disciplined small engineering organization:

**clear goals -> bounded implementation -> independent review -> deterministic QA -> evidence-based management decision**.

Autonomy is useful only when it is observable, bounded, reversible where appropriate, and explicit about the decisions that still belong to the CEO.