# Workflows
Version: 0.2

These are management/planning workflows. Actual repository execution still goes through the authoritative worker and safety contract in `docs/CEO_CONTROL_PLANE.md`.

## FAST
Use for low-risk, obvious, reversible work.

ChatGPT scopes a small task → normal worker path → fixed validation/review as applicable → Draft PR/CI → management decision.

FAST simplifies planning depth; it does not bypass path rules, fixed tests, review boundaries, approval gates, or the Draft PR boundary.

## STANDARD
Use for normal repository development.

1. ChatGPT defines one bounded GitHub Issue.
2. Codex implements in the dedicated worktree/allowed paths.
3. Worker enforces changed paths and runs the fixed test profile.
4. Claude performs independent read-only review when available.
5. If Claude returns `PASS`, no redundant second Claude call is needed.
6. If Claude returns `CHANGES_REQUESTED`, Codex gets exactly one bounded minimal-correction turn.
7. Path enforcement and fixed tests run again.
8. Exactly one final Claude review runs after a correction turn.
9. Final `CHANGES_REQUESTED` blocks Draft PR creation and escalates.
10. Successful work becomes a Draft PR, CI runs, and ChatGPT PM makes the routine management decision when evidence is sufficient.

The implementation review loop is intentionally bounded; `.ai-company` must not expand it into an unbounded model-to-model loop.

## DEEP
Mandatory for architecture, investment models, signal/scoring/risk logic, material data-flow changes, and other high-consequence design work.

DEEP adds an independent design challenge before normal implementation:

1. ChatGPT frames the decision/problem and required evidence.
2. Codex/GPT investigates and produces Proposal v1 with assumptions and validation plan.
3. Claude acts as an independent Challenger: identify failure modes, hidden assumptions, alternative designs, and missing evidence.
4. Codex/GPT responds to the challenge and produces a revised proposal.
5. If a second challenge round is materially useful, run one more bounded challenge/response round; otherwise stop.
6. ChatGPT synthesizes the accepted design, rejected alternatives, unresolved risks, and implementation slices.
7. Convert the accepted design into one or more bounded GitHub Issues.
8. Each implementation Issue proceeds through the normal STANDARD worker/test/review/CI path.
9. Final management review checks implementation evidence against the accepted design.

There is no unlimited debate loop. Unresolved high-risk conflict after the bounded challenge process is escalated to the CEO.

## Claude unavailable
When Claude cannot run, label the evidence accurately. A Codex read-only self-review fallback is not independent review and must never be described as such. High-risk DEEP design may remain blocked if independent challenge is materially required for a safe decision.

## DEEP synthesis record
Record at minimum:
- original objective/hypothesis;
- assumptions and evidence;
- Claude objections/challenges;
- Codex/GPT responses;
- accepted design;
- rejected alternatives and reasons;
- unresolved risks;
- validation plan;
- bounded implementation slices.

## Quant validation minimum
For quantitative/investment-model changes, consider as applicable:
- look-ahead bias;
- survivorship bias;
- transaction costs/slippage;
- chronological train/test separation;
- out-of-sample validation;
- walk-forward validation;
- regime dependency;
- parameter sensitivity;
- comparison against the current baseline.
