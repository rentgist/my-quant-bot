[CmdletBinding()]
param(
    [string]$TaskSpec = "companies/company-b/tasks/B-TASK-001.json",
    [string]$BaseRef = "origin/company-b/bootstrap-claude-led-v0.1",
    [switch]$PushOnPass,
    [ValidateRange(1, 60)][int]$TimeoutMinutes = 15
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
New-Item -ItemType Directory -Path $runtimeRoot -Force | Out-Null
$taskRuntime = Join-Path $runtimeRoot $taskId

$runtimeWorker = Join-Path $PSScriptRoot (".company-b-worker.bootstrap.{0}.ps1" -f ([guid]::NewGuid().ToString("N")))
$stdoutPath = Join-Path $runtimeRoot ("bootstrap-{0}.stdout.log" -f $taskId.ToLowerInvariant())
$stderrPath = Join-Path $runtimeRoot ("bootstrap-{0}.stderr.log" -f $taskId.ToLowerInvariant())
Remove-Item -LiteralPath $stdoutPath, $stderrPath -Force -ErrorAction SilentlyContinue

function Write-RunDiagnostics {
    if (Test-Path -LiteralPath $stdoutPath -PathType Leaf) {
        Write-Output "--- Company B bootstrap stdout ---"
        Get-Content -LiteralPath $stdoutPath -ErrorAction SilentlyContinue | Select-Object -Last 120 | Write-Output
        Write-Output "--- end bootstrap stdout ---"
    }
    if (Test-Path -LiteralPath $stderrPath -PathType Leaf) {
        $stderrLines = @(Get-Content -LiteralPath $stderrPath -ErrorAction SilentlyContinue)
        if ($stderrLines.Count -gt 0) {
            Write-Output "--- Company B bootstrap stderr ---"
            $stderrLines | Select-Object -Last 120 | Write-Output
            Write-Output "--- end bootstrap stderr ---"
        }
    }

    $planPath = Join-Path $taskRuntime "claude-plan.txt"
    $statePath = Join-Path $taskRuntime "state.json"
    if (Test-Path -LiteralPath $planPath -PathType Leaf) {
        Write-Output "--- Company B Claude planning output ---"
        Get-Content -LiteralPath $planPath -ErrorAction SilentlyContinue | Select-Object -First 120 | Write-Output
        Write-Output "--- end planning output ---"
    }
    if (Test-Path -LiteralPath $statePath -PathType Leaf) {
        Write-Output "--- Company B runtime state ---"
        Get-Content -LiteralPath $statePath -ErrorAction SilentlyContinue | Write-Output
        Write-Output "--- end runtime state ---"
    }
}

try {
    $content = Get-Content -LiteralPath $sourceWorker -Raw

    $planNeedle = '--permission-mode plan --max-turns 1 --output-format text'
    $planReplacement = '--permission-mode plan --max-turns 12 --output-format text'
    if (-not $content.Contains($planNeedle)) {
        throw "Company B bootstrap wrapper could not find the expected planning-turn limit. Refusing to run an unknown worker shape."
    }
    $patched = $content.Replace($planNeedle, $planReplacement)

    $codexNeedle = @'
    Remove-Item -LiteralPath $OutputPath -Force -ErrorAction SilentlyContinue
    Get-Content -LiteralPath $PromptPath -Raw |
        & $CodexPath exec --model $Model --cd $WorktreePath --sandbox read-only --output-last-message $OutputPath - 1> $null 2> $null
    if ($LASTEXITCODE -ne 0) {
        throw "Codex could not complete the Company B read-only challenger/reviewer turn."
    }
'@

    $codexReplacement = @'
    Remove-Item -LiteralPath $OutputPath -Force -ErrorAction SilentlyContinue
    $codexStdoutPath = "$OutputPath.stdout.log"
    $codexStderrPath = "$OutputPath.stderr.log"
    Remove-Item -LiteralPath $codexStdoutPath, $codexStderrPath -Force -ErrorAction SilentlyContinue

    $codexArguments = @(
        "exec",
        "--model", $Model,
        "--cd", $WorktreePath,
        "--sandbox", "read-only",
        "--output-last-message", $OutputPath,
        "-"
    )

    $codexProcess = Start-Process -FilePath $CodexPath -ArgumentList $codexArguments -PassThru -NoNewWindow -Wait `
        -RedirectStandardInput $PromptPath -RedirectStandardOutput $codexStdoutPath -RedirectStandardError $codexStderrPath

    if ($codexProcess.ExitCode -ne 0) {
        $detail = ""
        if (Test-Path -LiteralPath $codexStderrPath -PathType Leaf) {
            $detail = ((Get-Content -LiteralPath $codexStderrPath -ErrorAction SilentlyContinue | Select-Object -Last 20) -join " | ")
        }
        throw "Codex could not complete the Company B read-only challenger/reviewer turn. Exit code: $($codexProcess.ExitCode). $detail"
    }
'@

    if (-not $patched.Contains($codexNeedle)) {
        throw "Company B bootstrap wrapper could not find the expected Codex invocation. Refusing to run an unknown worker shape."
    }
    $patched = $patched.Replace($codexNeedle, $codexReplacement)
    Set-Content -LiteralPath $runtimeWorker -Value $patched -Encoding utf8

    $argumentList = @(
        '-NoProfile',
        '-ExecutionPolicy', 'Bypass',
        '-File', ('"{0}"' -f $runtimeWorker),
        '-TaskSpec', ('"{0}"' -f $TaskSpec),
        '-BaseRef', ('"{0}"' -f $BaseRef)
    )
    if ($PushOnPass) {
        $argumentList += '-PushOnPass'
    }

    Write-Output "Company B bootstrap started. Hard timeout: $TimeoutMinutes minute(s)."
    $process = Start-Process -FilePath "powershell.exe" -ArgumentList $argumentList -PassThru -NoNewWindow -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath
    $startedAt = Get-Date
    $timedOut = $false

    while (-not $process.HasExited) {
        Start-Sleep -Seconds 15
        $process.Refresh()
        $elapsed = (Get-Date) - $startedAt
        if ($process.HasExited) {
            break
        }
        Write-Output ("Company B bootstrap running... {0:N1}/{1} min" -f $elapsed.TotalMinutes, $TimeoutMinutes)
        if ($elapsed.TotalMinutes -ge $TimeoutMinutes) {
            $timedOut = $true
            Write-Output "Company B bootstrap exceeded the hard timeout. Terminating only this worker process tree."
            & taskkill.exe /PID $process.Id /T /F 1> $null 2> $null
            Start-Sleep -Seconds 2
            break
        }
    }

    if (-not $timedOut) {
        $process.WaitForExit()
    }

    Write-RunDiagnostics

    if ($timedOut) {
        throw "Company B bootstrap timed out after $TimeoutMinutes minute(s)."
    }

    $exitCode = [int]$process.ExitCode
    if ($exitCode -ne 0) {
        throw "Company B bootstrap worker exited with code $exitCode."
    }
}
finally {
    Remove-Item -LiteralPath $runtimeWorker -Force -ErrorAction SilentlyContinue
}
