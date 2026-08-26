# Workflows
Version: 0.2

## FAST
Use for low-risk, obvious changes.

Codex implement → local verification → DONE

Examples: text correction, small UI adjustment, logging, trivial bug.

## STANDARD
Use for normal development.

Task → Codex inspect/plan → implement → test → Claude review → Codex fix if needed → retest → PASS/ESCALATE

Maximum review-fix loops: 2.

## DEEP
Mandatory for investment models, signal logic, scoring, risk models, architecture, material data-flow changes.

1. Codex Proposal v1
2. Claude Critique v1
3. Codex Response + Proposal v2
4. Claude Critique v2
5. Synthesis document
6. Codex Implementation
7. Tests / Backtests
8. Claude Code Review
9. Codex Revision
10. Independent validation
11. PASS or CEO ESCALATION

## DEEP Synthesis must record
- original hypothesis
- Claude objections
- Codex responses
- accepted design
- rejected alternatives and reasons
- unresolved risks
- validation plan

## Quant Validation Minimum
- look-ahead bias
- survivorship bias when applicable
- transaction costs/slippage
- chronological train/test separation
- out-of-sample validation
- walk-forward where meaningful
- regime dependency
- parameter sensitivity
- comparison against current baseline
