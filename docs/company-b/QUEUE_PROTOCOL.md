# Company B queue protocol

This document describes `scripts/company_b/company-b-queue-worker.ps1`, the only Company B remote
queue consumer, and `scripts/company_b/setup-company-b-github.ps1`, its idempotent label bootstrap.

The queue wrapper is a thin sequencer. It discovers Company B work, hands one task at a time to
the already-validated `scripts/company_b/company-b-worker.ps1` unmodified, and publishes durable
evidence. It never re-implements Claude planning, Codex review, or path/test enforcement — that
logic lives exclusively in the worker.

## Lifecycle labels

| Label | Meaning |
| --- | --- |
| `company-b:queued` | A human (or PM) has added a Company B task spec to an Issue and asked the queue worker to process it. |
| `company-b:running` | The queue worker has claimed the Issue and is executing or publishing evidence for it. |
| `company-b:blocked` | The queue worker failed closed. A reason code and next action are posted as an Issue comment. Human review is required before requeueing. |
| `company-b:done` | A Draft PR exists with published, head-bound durable evidence. Human/PM review decides the merge. |
| `company-b:approval-required` | Supplementary visibility label added when `risk == "high"`. It does not replace the Draft PR gate and is applied best-effort. |

`scripts/company_b/setup-company-b-github.ps1` idempotently creates or updates exactly these five
labels (create-if-missing, update-if-present) and never touches or references any `agent:*` label.
Its `-SelfTest` switch is fully offline and only asserts the shape of the label set (five labels,
all prefixed `company-b:`, none prefixed `agent:`).

## Isolation from Company A

The queue wrapper:

- discovers work only via the `company-b:queued` label (default) and never reads or writes
  Company A's queued/running/blocked/done/approval-required lifecycle labels;
- reads/writes local runtime state only under the Company B namespace
  (`%LOCALAPPDATA%\AICompany\company-b\my-quant-bot\`), never Company A's worktree/lifecycle
  directories or `.ai-company/`;
- creates branches only under `company-b/task-*`, using the existing worker's own commit,
  never `main`, and never auto-merges.

Concurrent invocations fail closed: the wrapper takes a dedicated, non-blocking named mutex
(`Global\rentgist-my-quant-bot-company-b-queue`, distinct from Company A's
`Global\rentgist-my-quant-bot-codex-queue`) with `WaitOne(0)`. If it cannot be acquired, the
invocation throws immediately instead of silently skipping or queueing behind another run.

Each invocation processes **at most one** queued Issue, end to end, then exits.

## Issue body task format

The Issue body must contain the task spec JSON between two literal marker lines, each appearing
exactly once:

```text
COMPANY_B_TASK_SPEC_START
{
  "id": "B-TASK-004",
  "title": "...",
  "objective": "...",
  "acceptance_criteria": ["..."],
  "risk": "low",
  "test_profile": "pytest",
  "allowed_paths": ["..."],
  "forbidden_paths": ["..."]
}
COMPANY_B_TASK_SPEC_END
```

The wrapper performs a fail-fast, **non-authoritative** preflight validation of this payload
(`id` matches `^B-TASK-[0-9]{3,}$`, non-empty `title`/`objective`, `risk` in
`low|medium|high`, `test_profile` in `company-b-bootstrap|pytest`, non-empty, traversal-free
`allowed_paths`/`forbidden_paths` with no overlap) before ever touching the worker runtime. This
preflight exists only to fail closed on an obviously malformed Issue without invoking the worker;
`company-b-worker.ps1` independently re-validates the materialized spec and remains the
authoritative gate. The validated JSON text is written verbatim, and only, to
`%LOCALAPPDATA%\AICompany\company-b\my-quant-bot\queue\issue-<n>\task-spec.json` — never into the
git-tracked `companies/company-b/tasks/` namespace used for hand-authored one-shot tasks.

If an Issue carries both a queued and a running label at once, the running label takes
precedence and the wrapper treats the Issue as a recovery candidate (see below) rather than
re-parsing the body.

## Execution

1. `git fetch origin <BaseRef>` (default `company-b/bootstrap-claude-led-v0.1`), then resolve
   `origin/<BaseRef>` explicitly. The worker is always invoked with this freshly fetched
   remote-tracking ref, never a possibly-stale local branch of the same name, so the branch the
   worker creates and the branch a Draft PR is opened against are guaranteed to share a base.
2. Transition `company-b:queued` → `company-b:running` and post a status comment. This
   transition, like every other lifecycle label/comment update, the Draft PR create-or-reuse
   step, and the evidence publish step, is **completion-critical**: a GitHub failure here stops
   the run instead of being logged as a warning. Only the `company-b:approval-required`
   visibility label is best-effort, because the Draft PR (never auto-merged) is the real gate.
3. Invoke `scripts/company_b/company-b-worker.ps1 -TaskSpec <materialized-spec> -BaseRef
   origin/<BaseRef> -PushOnPass`. No planning, challenge, implementation, test, or review logic is
   duplicated here.
4. Validate the worker's own `state.json` (`taskId`, `branch`, and a 40-hex `baseSha` all present
   and matching the selected task) and require `status == PASS`, `phase == DONE`, and
   `reviewVerdict == PASS` before proceeding. Any other state blocks the Issue with
   `WORKER_NOT_PASS`.
5. Validate `test-result.txt` unambiguously reports `PASSED` for the task's own `test_profile`,
   and `codex-review.txt` contains exactly one `VERDICT: PASS` line. Either gap blocks with
   `EVIDENCE_INVALID`.
6. Resolve the exact task branch head via `git rev-parse refs/heads/<branch>` (the branch ref
   survives worktree removal even though the worker deletes its worktree on success).
7. Ensure the remote branch matches that head (push it if not — this can happen on resume, see
   below), then create-or-reuse a Draft PR for that branch against `<BaseRef>`. The PR lookup
   filters by **both** exact head and exact base and requires exactly one open Draft PR; a
   matching non-draft PR blocks with `NONDRAFT_PR_EXISTS`, and more than one match blocks as
   ambiguous. The PR is re-read after creation and its `headRefOid` is compared byte-for-byte
   against the resolved head before anything is published; a mismatch blocks the run rather than
   publishing stale evidence.
8. Publish a durable evidence comment on the PR containing the exact task head SHA, the fixed-test
   PASS statement, and the independent Codex final review **verdict** (only the `VERDICT: ...`
   line is republished, not the raw agent transcript, to avoid leaking incidental local paths or
   other agent output — the full transcript remains available locally under the Company B
   runtime for audit). The comment is namespaced with an idempotency marker
   (`<!-- company-b-queue-evidence:v1 issue=<n> pr=<pr#> head=<sha> verdict=PASS -->`, distinct
   from Company A's `codex-bounded-review-evidence:v1`) and the wrapper reads the PR's comments
   back after publishing to confirm exactly one matching marker exists before continuing.
9. Transition `company-b:running` → `company-b:done` and post a completion comment. Company B
   never calls `gh pr merge` or otherwise merges the Draft PR.

## Recovery

The wrapper never deletes or overwrites a worker runtime directory. If
`%LOCALAPPDATA%\AICompany\company-b\my-quant-bot\<TaskId>\` already exists when a **queued** Issue
is selected, the wrapper blocks with `TASK_RUNTIME_ALREADY_EXISTS` rather than invoking the worker
(the worker itself throws in this situation and never self-cleans).

If the wrapper is interrupted after the worker has already reached `PASS`/`DONE` but before the
Draft PR/evidence/`done` transition completes, a later invocation recognizes the Issue's
`company-b:running` label, locates its own saved `queue-state.json` for that Issue, and resumes
directly from step 4 above — re-validating the worker's PASS state and evidence, then retrying
only the push/PR/evidence/lifecycle publication. It does not re-invoke the worker, re-plan, or
re-implement anything. Publication is safe to retry because the Draft PR lookup and the evidence
marker check are both idempotent.

If a `company-b:running` Issue has no matching local `queue-state.json` (for example, state was
lost or another process's label edit raced with this Issue), the wrapper blocks it as
`ORPHANED_RUNNING` rather than guessing at recovery.

### Reason codes

The worker's own outer error handler collapses almost every internal failure to a single
`COMPANY_B_TASK_FAILED` state, so the queue wrapper cannot reliably promise a granular
per-cause code for worker failures. Reason codes posted to a blocked Issue are therefore
deliberately coarse and always point back at the preserved local runtime for the real diagnostic
detail:

| Code | Meaning | Where to look |
| --- | --- | --- |
| `TASK_SPEC_INVALID_JSON` | The marker-delimited body content is not valid JSON. | The Issue body. |
| `TASK_SPEC_SCHEMA_INVALID` | The preflight envelope check rejected the spec. | The Issue body. |
| `TASK_RUNTIME_ALREADY_EXISTS` | A prior runtime directory exists for this task id. | `%LOCALAPPDATA%\AICompany\company-b\my-quant-bot\<TaskId>\`. |
| `WORKER_FAILED` | `company-b-worker.ps1` exited non-zero. | Same runtime directory (`state.json`, prompt/output files). |
| `WORKER_NOT_PASS` | Worker state exists but is not a validated PASS/DONE result. | `state.json` in the same directory. |
| `EVIDENCE_INVALID` | `test-result.txt` or `codex-review.txt` did not unambiguously show a PASS. | Same directory. |
| `ORPHANED_RUNNING` | A `company-b:running` Issue has no local recovery state. | Manual review; relabel only after investigation. |
| `PUBLISH_FAILED` | Push, Draft PR create/reuse, or evidence publish failed; the specific error is included in the Issue comment. | The comment itself, then rerun to resume. |

## No-auto-merge policy

The queue wrapper only ever creates or reuses a **Draft** PR. It never converts a PR out of draft,
never calls `gh pr merge`, and never pushes to `main`. Merge decisions remain a human/PM action
taken after reviewing the published evidence.
