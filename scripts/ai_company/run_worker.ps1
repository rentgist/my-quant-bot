param(
  [string]$Task = "TASK-001"
)

$ErrorActionPreference = "Stop"
$repo = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $repo

Write-Host "[AI Company] Repo: $repo"
Write-Host "[AI Company] Checking Codex CLI..."
codex --version

Write-Host "[AI Company] Running $Task"
python .\scripts\ai_company\worker.py --task $Task

Write-Host "[AI Company] Done. Review git status and generated handoff before pushing."
