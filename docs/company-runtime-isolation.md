# One scheduler with isolated company runtimes

Issue #98 retains the existing `MyQuantBot-CodexQueueWorker` scheduler and
`codex-queue-worker.ps1` execution engine. There is no second poller or lifecycle
database. Company A operates on `main`; Company B is still under development and
cannot be dispatched by this entry point. Do not infer a B production base from a
development checkout. B activation requires a separate validated change.

The scheduled wrapper, worker, and installer accept a local `RuntimeConfigPath`.
They also discover `company.runtimeConfigPath` in the clone's local Git config.
Existing unbound installations retain legacy behavior until explicitly migrated.
The configuration is local operator data, never Issue-supplied code. Example
(replace every path with a real absolute path; do not publish local configuration):

```json
{
  "schemaVersion": 1,
  "companyBEnabled": false,
  "aPrimaryRoot": "C:/CompanyRuntime/a/primary",
  "aWorktreeRoot": "C:/CompanyRuntime/a/worktrees",
  "aLogRoot": "C:/CompanyRuntime/a/logs",
  "bPrimaryRoot": "C:/CompanyRuntime/b/primary",
  "bWorktreeRoot": "C:/CompanyRuntime/b/worktrees",
  "bStateRoot": "C:/CompanyRuntime/b/state",
  "bLogRoot": "C:/CompanyRuntime/b/logs"
}
```

All roots must be disjoint, non-nested, and free of junctions/symlinks. Both
primary roots must contain their own `.git` directory and no Git alternates.
A lifecycle remains at `aWorktreeRoot/lifecycle`; private scheduled transcripts
go to `aLogRoot`. B paths are reserved and disabled, not a new production state
store. Existing B state/worktrees remain preserved outside these reserved paths.
The wrapper and worker retain their existing global mutex identities. The one
registered scheduler uses `IgnoreNew`. `-Company B`, a wrong root/base/queue,
mixed-company labels, or premature B activation is rejected. Mixed labels stop
the queue without lifecycle mutation; exit code 4 also suppresses the wrapper's
recovery writers. GitHub labels are not a transactional claim API: this does not
promise protection against simultaneous external relabeling after validation.

## Local operator rollout

1. Keep #97 held. Export the current scheduler XML and preserve all commits,
   dirty/untracked files, detached heads, task worktrees, state, and logs. Wait for
   active work to finish; do not terminate it or delete locks.
2. Create independent full clones without shared object alternates/hardlinks.
   Preserve the B checkout's exact commit as a disabled development snapshot.
   Keep original repositories/worktrees intact for rollback.
3. Validate this change through a Draft PR, independent Claude read-only review
   bound to its exact head, and current-head CI. Do not auto-merge. Install the
   guarded source on A's current `main` only after the normal merge decision.
4. Write the local manifest and bind it with `git config --local
   company.runtimeConfigPath <absolute-manifest-path>`. Verify the actual
   branch, common directories, state paths, and disabled B before scheduling.
5. With no worker active, update the existing scheduled action (same task name,
   account, trigger and settings) to the new A wrapper, adding
   `-RuntimeConfigPath <absolute-manifest-path> -Company A`. Retain exported XML
   for rollback; never enable both the old and new action. Do not run the
   installer blindly over an existing task: it creates its default trigger and
   settings. Migration must preserve the existing task's configuration.
6. Observe the next normal run's #35 healthy/synced evidence. Record sanitized
   acceptance on #98; only then restore #97's queue label once and verify its
   single claim. B remains disabled. No B business lifecycle is changed.

Run `scripts/test-company-runtime-isolation.ps1` on an idle host for real
duplicate-entry tests. The worker's fixed-test profile uses
`-SkipLiveMutexTests` because the production mutex is already held; CI runs the
full test. Tests create disposable Git fixtures and never execute product work.
This separation prevents ordinary Git/worktree cross-effects; it is not an OS
security boundary against an arbitrary process running as the same user.
