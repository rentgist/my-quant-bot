# Company B Bootstrap Probe

COMPANY: B
DIRECTOR: Claude Code
REVIEWER: Codex / GPT
STATUS: bootstrap-probe

Company B is operationally isolated from Company A: it uses its own task
records under `companies/company-b/`, its own worker
(`scripts/company_b/company-b-worker.ps1`), and its own branches/PRs. This
probe does not modify or consume Company A's control plane, worker, or task
history.
