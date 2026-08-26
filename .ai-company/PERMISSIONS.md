# Permissions
Version: 0.2

| Action | Codex | Claude | CEO |
|---|---|---|---|
| Read repository | ALLOW | ALLOW | ALLOW |
| Edit task branch | ALLOW | DENY by default | ALLOW |
| Run local tests/backtests | ALLOW | ALLOW if read-only | ALLOW |
| Create commit/PR | ALLOW | DENY by default | ALLOW |
| Merge main | DENY | DENY | APPROVAL REQUIRED |
| Change dependencies/config | CONDITIONAL | REVIEW ONLY | APPROVAL if material |
| Delete data/files | DENY unless task explicitly authorizes | DENY | APPROVAL REQUIRED |
| Spend money / paid API | DENY | DENY | APPROVAL REQUIRED |
| Live trading / brokerage order | FORBIDDEN | FORBIDDEN | Separate constitution change required |
| Reveal/copy secrets | FORBIDDEN | FORBIDDEN | FORBIDDEN |

## Secrets
API keys, tokens, passwords and brokerage credentials must not be written to task files, handoffs, reviews or chat logs. Use local environment variables or GitHub Secrets only.

## Primary Worker
v0.2 uses one PRIMARY worker. Additional PCs remain STANDBY until task locking is validated.
