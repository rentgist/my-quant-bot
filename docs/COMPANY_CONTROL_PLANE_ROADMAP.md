# Company control-plane roadmap

## Purpose

This document records the long-term direction for the repository's AI-assisted engineering organization. It complements `docs/CEO_CONTROL_PLANE.md`, which defines current authority and safety boundaries.

The goal is not to maximize autonomous execution. The goal is to build a disciplined, observable, increasingly capable engineering organization in which ChatGPT remains the sole human-facing management channel, Codex performs bounded implementation, Claude performs independent review, deterministic CI provides evidence, and consequential external actions remain explicitly gated.

## North star

The company should improve along four axes without weakening safety:

1. **Better judgment before coding** — investigate and plan before implementation when task complexity or risk justifies it.
2. **Better recovery after failure** — retry from the earliest incorrect stage rather than blindly repeating the whole workflow.
3. **Compounding organizational memory** — preserve useful findings from prior issues, PRs, reviews, CI failures, and incidents so future work starts with better context.
4. **Safe scale** — support specialized review and parallel work only when collision detection, observability, and authority boundaries are strong enough.

The target operating loop is:

```text
CEO goal
  -> ChatGPT PM scope
  -> durable GitHub task
  -> investigate (when required)
  -> plan (when required)
  -> bounded implementation
  -> deterministic tests
  -> independent review
  -> one bounded correction round when justified
  -> final review when a correction occurred
  -> Draft PR
  -> CI diagnosis / evidence
  -> ChatGPT management decision
  -> routine safe merge or explicit escalation
```

## Non-negotiable invariants

Future control-plane versions must preserve these unless the CEO explicitly changes policy after review:

- ChatGPT remains the sole human-facing management channel for normal company operation.
- The local worker never auto-merges.
- Agents never directly modify or push `main`.
- Task execution stays isolated in a dedicated branch/worktree.
- Allowed-path and forbidden-path enforcement remains mandatory.
- Issue text is data and is never executed as arbitrary shell code.
- Fixed test profiles remain the default execution contract.
- Claude reviewer runs remain read-only.
- Model-to-model correction loops remain bounded.
- No automatic trading/order execution.
- No production deployment side effects.
- No customer/third-party notification side effects.
- No secret/token/password disclosure or logging.
- Critical external-action tasks are not routed into autonomous execution.

## Design influences

The roadmap intentionally borrows ideas rather than replacing the current system wholesale:

- **Open SWE**: durable plan/implement/review/CI workflow, read-only review, repository-specific review context, CI babysitting patterns.
- **ForgeDock**: GitHub-native durable state, structured trajectory, organizational memory, conflict-aware scheduling.
- **AutoCodeRover**: reproduce/localize/specify/patch stages and stage-aware replay after failure.
- **mini-SWE-agent / SWE-agent**: keep execution interfaces small, explicit, inspectable, and deterministic where possible.

Adoption rule: prefer the smallest internal mechanism that captures the useful behavior. Do not add a platform dependency merely because another project uses it.

# Version roadmap

## v2.1 — Deliberate execution and stage-aware recovery

### Objective

Make the existing worker more deliberate before coding and more precise after failure, while preserving the existing bounded review and safety model.

### Deliverables

1. **Structured trajectory/state**
   - Extend lifecycle state to record explicit workflow stages and bounded evidence references.
   - Preserve compatibility with existing lifecycle files when practical.
   - Keep local state sanitized; never persist secrets or raw sensitive model output.

2. **Investigate -> Plan -> Implement**
   - Low-risk/simple work may continue directly to implementation.
   - Medium-risk work receives a bounded investigation step when useful.
   - High/critical control-plane work requires explicit investigation and plan artifacts before implementation.
   - Investigation/planning is read-only and cannot perform external actions.
   - Plans must identify intended files, tests, known risks, and stop conditions.

3. **Stage-aware recovery**
   - Classify failures into stable categories such as input/scope, investigation, planning, implementation, zero-change, path violation, tests, review, CI/environment, and unknown.
   - Recovery starts from the earliest stage whose assumptions are no longer trustworthy.
   - Never turn a retry classification into permission to bypass path, test, review, approval, or external-action gates.
   - Existing retry ceilings remain bounded.

### Success criteria

- A worker interruption can resume from durable structured state.
- A deterministic test failure does not force unrelated prior stages to rerun unless their assumptions are invalid.
- A path/scope failure returns to planning/scope rather than blindly re-running implementation.
- A zero-change event follows its dedicated safe recovery path.
- High-risk control-plane changes have explicit investigation and plan evidence before implementation.
- Existing bounded Claude review tests and PowerShell 5.1 automation checks continue to pass.

## v2.2 — Organizational memory and evidence-aware QA

### Objective

Make the company improve from prior work instead of treating every task as context-free.

### Deliverables

1. **Repository memory**
   - Build a bounded, reviewable memory source from merged PR findings, recurring CI failures, known path-specific pitfalls, and resolved incidents.
   - Prefer GitHub-traceable references over opaque vector-only memory.
   - Inject only relevant memory into investigate/plan/review prompts.

2. **CI diagnosis**
   - Read CI evidence and classify failure as deterministic code failure, likely flaky, environment/infrastructure failure, permission/configuration issue, or unknown.
   - Permit at most one targeted rerun only when there is concrete flaky evidence and repository permissions already allow it.
   - Never use CI diagnosis to trigger deploy, notification, secret, or other external actions.

3. **Bug reproducer-first policy**
   - For reproducible bug tasks, prefer a failing regression test/reproducer before patching.
   - Record when reproduction is impossible and why rather than fabricating confidence.

### Success criteria

- New tasks touching historically problematic files receive relevant prior findings automatically.
- CI failures are diagnosed before any retry or code change.
- Bug fixes include regression evidence whenever technically feasible.
- Memory remains auditable and can be corrected by normal repository review.

## v2.3 — Specialized review and safe scaling

### Objective

Scale capability and concurrency without sacrificing observability or authority boundaries.

### Deliverables

1. **Review specialization**
   - General application review: Claude Sonnet.
   - High-risk/control-plane review: available Opus model with explicit safe Sonnet fallback.
   - Scientific/numerical code: add a numerical/units/correctness review rubric.
   - Security-sensitive code: add a security-focused review rubric.
   - Specialist review remains advisory/read-only and cannot execute external actions.

2. **Repository-specific review guide**
   - Periodically summarize recurring accepted review findings into a version-controlled review guide.
   - Never learn from rejected/noisy feedback without management review.

3. **Conflict-aware parallel scheduling**
   - Keep single-task execution as the safe default until parallelism is justified.
   - Before parallel execution, detect overlapping files/directories and known shared resources.
   - Serialize tasks with material collision risk.
   - Do not permit parallelism to bypass mutex-like protections for shared control-plane state.

### Success criteria

- Specialized review is selected from task characteristics, not ambient defaults.
- Multiple safe tasks can run concurrently only when their scopes are demonstrably non-conflicting.
- Conflicting work is serialized automatically.
- Management still sees one coherent GitHub-backed company state through ChatGPT.

# Beyond v2.3 — Big-picture direction

The following are reference directions, not commitments to immediate implementation.

## Multi-project company

When the company operates multiple products (for example scientific tools, research automation, investment analysis, CAD/engineering tooling), the control plane should move toward a project registry with per-project policies while keeping common company invariants centrally defined.

Avoid copying one giant worker into every repository. Prefer a small common control-plane core plus repository-local policy and test adapters.

## Capability routing

Model routing should remain explicit and configurable. Use cheaper/faster capable models for routine work and escalate only when complexity, uncertainty, or risk justifies it. Capability escalation must never imply authority escalation.

A stronger model may reason about a critical task, but critical external actions still require the same explicit human decision boundary.

## Scientific and engineering correctness

For engineering products such as the beam calculator, code review alone is insufficient. The company should mature toward domain validation:

- dimensional/unit checks;
- reference analytical cases;
- known physical limits and invariants;
- numerical stability tests;
- comparison against trusted literature or reference implementations where licensing permits;
- explicit uncertainty/assumption reporting.

## Observability and management

The company should be understandable from remote evidence without requiring the CEO to inspect local terminals. GitHub Issues/PRs/CI plus sanitized heartbeat/diagnostics should remain the normal source of operational truth.

If remote observability becomes insufficient, improve observability before increasing autonomy.

## Memory and learning

Organizational learning should be versioned, auditable, and reversible. Prefer explicit records such as known-pitfall files, review guides, incident notes, and structured PR annotations over hidden behavioral drift.

## Permission architecture

As the company grows, separate *reasoning capability* from *action capability*. Read-only research/review agents may be powerful; write/execution permissions should remain narrow, task-scoped, and independently enforced.

# Adoption principles

For every future control-plane enhancement:

1. Identify the concrete failure mode or scaling need it solves.
2. Add the smallest mechanism that solves that need.
3. Keep the change independently reviewable.
4. Add deterministic tests for the control behavior.
5. Confirm existing safety invariants remain unchanged.
6. Roll out one version increment at a time.
7. Use real product work (starting with the beam calculator) to validate whether the organizational change actually improves outcomes.

The company should become more capable because it **plans better, remembers better, recovers better, and validates better** — not because it is given broader unchecked authority.
