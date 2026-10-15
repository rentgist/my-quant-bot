[CmdletBinding()]
param(
    [string]$TaskId = 'B-TASK-001',
    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if ($TaskId -notmatch '^B-TASK-[0-9]{3,}$') {
    throw 'TaskId must match B-TASK-NNN.'
}
if (-not $Force) {
    throw 'Company B reset is destructive within the isolated task scope. Re-run with -Force.'
}

$repositoryRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$runtimeRoot = if (-not [string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) {
    Join-Path $env:LOCALAPPDATA 'AICompany\company-b\my-quant-bot'
} else {
    Join-Path ([System.IO.Path]::GetTempPath()) 'AICompany\company-b\my-quant-bot'
}

$taskRuntime = Join-Path $runtimeRoot $TaskId
$worktreePath = Join-Path (Join-Path $runtimeRoot 'worktrees') $TaskId.ToLowerInvariant()
$branchName = 'company-b/task-' + $TaskId.ToLowerInvariant()

Write-Output "Company B reset scope only:"
Write-Output "  task: $TaskId"
Write-Output "  branch: $branchName"
Write-Output "  worktree: $worktreePath"
Write-Output "  runtime: $taskRuntime"

if (Test-Path -LiteralPath $worktreePath) {
    & git -C $repositoryRoot worktree remove $worktreePath --force
    if ($LASTEXITCODE -ne 0) {
        throw 'Could not remove the failed Company B task worktree.'
    }
}

& git -C $repositoryRoot worktree prune

& git -C $repositoryRoot show-ref --verify --quiet "refs/heads/$branchName"
if ($LASTEXITCODE -eq 0) {
    & git -C $repositoryRoot branch -D $branchName
    if ($LASTEXITCODE -ne 0) {
        throw 'Could not delete the failed local Company B task branch.'
    }
}

if (Test-Path -LiteralPath $taskRuntime) {
    Remove-Item -LiteralPath $taskRuntime -Recurse -Force
}

Write-Output 'Company B failed-task reset complete.'
