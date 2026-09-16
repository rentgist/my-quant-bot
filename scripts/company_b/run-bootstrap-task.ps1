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

$runtimeWorker = Join-Path $PSScriptRoot (".company-b-worker.bootstrap.{0}.ps1" -f ([guid]::NewGuid().ToString("N")))

try {
    $content = Get-Content -LiteralPath $sourceWorker -Raw
    $needle = '--permission-mode plan --max-turns 1 --output-format text'
    $replacement = '--permission-mode plan --max-turns 4 --output-format text'
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
        throw "Company B bootstrap worker exited with code $exitCode."
    }
}
finally {
    Remove-Item -LiteralPath $runtimeWorker -Force -ErrorAction SilentlyContinue
}
