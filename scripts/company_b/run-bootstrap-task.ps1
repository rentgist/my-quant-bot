[CmdletBinding()]
param(
    [string]$TaskSpec = "companies/company-b/tasks/B-TASK-001.json",
    [string]$BaseRef = "origin/company-b/bootstrap-claude-led-v0.1",
    [switch]$PushOnPass
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$sourceWorker = Join-Path $PSScriptRoot "company-b-worker.ps1"
if (-not (Test-Path -LiteralPath $sourceWorker -PathType Leaf)) {
    throw "Company B worker source was not found."
}

$repositoryRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$resolvedTaskSpec = if ([System.IO.Path]::IsPathRooted($TaskSpec)) { $TaskSpec } else { Join-Path $repositoryRoot $TaskSpec }
$taskId = "B-TASK-001"
if (Test-Path -LiteralPath $resolvedTaskSpec -PathType Leaf) {
    try {
        $task = Get-Content -LiteralPath $resolvedTaskSpec -Raw | ConvertFrom-Json
        if (-not [string]::IsNullOrWhiteSpace([string]$task.id)) {
            $taskId = [string]$task.id
        }
    }
    catch { }
}

$runtimeRoot = if (-not [string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) {
    Join-Path $env:LOCALAPPDATA "AICompany\company-b\my-quant-bot"
} else {
    Join-Path ([System.IO.Path]::GetTempPath()) "AICompany\company-b\my-quant-bot"
}
$taskRuntime = Join-Path $runtimeRoot $taskId

$runtimeWorker = Join-Path $PSScriptRoot (".company-b-worker.bootstrap.{0}.ps1" -f ([guid]::NewGuid().ToString("N")))

try {
    $content = Get-Content -LiteralPath $sourceWorker -Raw
    $needle = '--permission-mode plan --max-turns 1 --output-format text'
    $replacement = '--permission-mode plan --max-turns 12 --output-format text'
    if (-not $content.Contains($needle)) {
        throw "Company B bootstrap wrapper could not find the expected planning-turn limit. Refusing to run an unknown worker shape."
    }
    $patched = $content.Replace($needle, $replacement)
    Set-Content -LiteralPath $runtimeWorker -Value $patched -Encoding utf8

    $args = @(
        '-NoProfile',
        '-ExecutionPolicy', 'Bypass',
        '-File', $runtimeWorker,
        '-TaskSpec', $TaskSpec,
        '-BaseRef', $BaseRef
    )
    if ($PushOnPass) {
        $args += '-PushOnPass'
    }

    & powershell @args
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0) {
        $planPath = Join-Path $taskRuntime "claude-plan.txt"
        $statePath = Join-Path $taskRuntime "state.json"
        if (Test-Path -LiteralPath $planPath -PathType Leaf) {
            Write-Output "--- Company B Claude planning output ---"
            Get-Content -LiteralPath $planPath -ErrorAction SilentlyContinue | Select-Object -First 80 | Write-Output
            Write-Output "--- end planning output ---"
        }
        if (Test-Path -LiteralPath $statePath -PathType Leaf) {
            Write-Output "--- Company B runtime state ---"
            Get-Content -LiteralPath $statePath -ErrorAction SilentlyContinue | Write-Output
            Write-Output "--- end runtime state ---"
        }
        throw "Company B bootstrap worker exited with code $exitCode."
    }
}
finally {
    Remove-Item -LiteralPath $runtimeWorker -Force -ErrorAction SilentlyContinue
}
