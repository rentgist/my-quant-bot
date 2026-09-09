[CmdletBinding()]
param(
    [string]$Repository = "rentgist/my-quant-bot",
    [string]$WorktreeRoot,
    [string]$RecoveryCodexModel = "gpt-5.6-sol",
    [switch]$SelfTest
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$AllowedReasonCodes = @(
    "EMPTY_LAST_MESSAGE",
    "WRITE_BLOCKED_OR_POLICY_CONFLICT",
    "MISSING_CONTEXT",
    "ANALYSIS_ONLY",
    "NO_CHANGE_NEEDED",
    "UNKNOWN_ZERO_CHANGE"
)

function Resolve-RequiredCommand {
    param([string[]]$Names, [string]$DisplayName)

    foreach ($name in $Names) {
        $command = Get-Command $name -ErrorAction SilentlyContinue
        if ($null -ne $command) { return $command.Source }
    }

    foreach ($base in @($env:APPDATA, $env:LOCALAPPDATA)) {
        if ([string]::IsNullOrWhiteSpace($base)) { continue }
        foreach ($name in $Names) {
            $candidate = Join-Path $base "npm\$name"
            if (Test-Path -LiteralPath $candidate -PathType Leaf) { return $candidate }
        }
    }

    throw "$DisplayName command was not found."
}

function Get-CodexZeroChangeReasonCode {
    param([string]$Text)

    if ([string]::IsNullOrWhiteSpace($Text)) { return "EMPTY_LAST_MESSAGE" }
    $normalized = ($Text -replace "`r", " " -replace "`n", " ").ToLowerInvariant()

    if ($normalized -match "cannot\s+(edit|modify|write)|not\s+allowed\s+to\s+(edit|modify|write)|read[- ]only|permission|conflict") {
        return "WRITE_BLOCKED_OR_POLICY_CONFLICT"
    }
    if ($normalized -match "need\s+more\s+(context|information)|missing\s+(context|information)|cannot\s+determine") {
        return "MISSING_CONTEXT"
    }
    if ($normalized -match "already\s+(implemented|done|satisfied)|no\s+changes\s+(needed|required)|nothing\s+to\s+change") {
        return "NO_CHANGE_NEEDED"
    }
    if ($normalized -match "plan|analysis|investigat|reviewed|inspected" -and $normalized -notmatch "updated|changed|modified|implemented|created") {
        return "ANALYSIS_ONLY"
    }
    return "UNKNOWN_ZERO_CHANGE"
}

function Invoke-SelfTest {
    $cases = @(
        @{ Text = ""; Expected = "EMPTY_LAST_MESSAGE" },
        @{ Text = "I cannot write because this conflicts with the allowed policy."; Expected = "WRITE_BLOCKED_OR_POLICY_CONFLICT" },
        @{ Text = "I need more context before I can determine the change."; Expected = "MISSING_CONTEXT" },
        @{ Text = "I inspected the worker and prepared a plan."; Expected = "ANALYSIS_ONLY" },
        @{ Text = "No changes are needed because this is already implemented."; Expected = "NO_CHANGE_NEEDED" },
        @{ Text = "Task completed without a recognizable explanation."; Expected = "UNKNOWN_ZERO_CHANGE" }
    )

    foreach ($case in $cases) {
        $actual = Get-CodexZeroChangeReasonCode -Text ([string]$case.Text)
        if ($actual -ne [string]$case.Expected) {
            throw "Zero-change classifier self-test failed: expected $($case.Expected), got $actual."
        }
    }
    Write-Output "Zero-change diagnosis self-test passed."
}

if ($SelfTest) {
    Invoke-SelfTest
    exit 0
}

$repositoryRoot = (Resolve-Path -LiteralPath (Split-Path -Parent $PSScriptRoot)).Path
if ([string]::IsNullOrWhiteSpace($WorktreeRoot)) {
    $repositoryParent = Split-Path -Parent $repositoryRoot
    $repositoryName = Split-Path -Leaf $repositoryRoot
    $WorktreeRoot = Join-Path $repositoryParent "$repositoryName-agent-worktrees"
}
$WorktreeRoot = [System.IO.Path]::GetFullPath($WorktreeRoot)
$lifecycleDirectory = Join-Path $WorktreeRoot "lifecycle"
if (-not (Test-Path -LiteralPath $lifecycleDirectory -PathType Container)) { exit 2 }

$ghPath = Resolve-RequiredCommand -Names @("gh.exe", "gh") -DisplayName "GitHub CLI"
$codexPath = Resolve-RequiredCommand -Names @("codex.exe", "codex.cmd", "codex") -DisplayName "Codex"

$stateFile = $null
$state = $null
$issue = $null
foreach ($candidate in @(Get-ChildItem -LiteralPath $lifecycleDirectory -Filter "issue-*.json" -File | Sort-Object LastWriteTimeUtc -Descending)) {
    try {
        $candidateState = Get-Content -LiteralPath $candidate.FullName -Raw -Encoding UTF8 | ConvertFrom-Json
    }
    catch { continue }

    if ([string]$candidateState.failureReason -notlike "*Codex made no changes*") { continue }
    if ($null -eq $candidateState.issueNumber) { continue }

    $candidateIssueJson = & $ghPath issue view ([int]$candidateState.issueNumber) --repo $Repository --json number,title,body,url,state,labels 2> $null
    if ($LASTEXITCODE -ne 0) { continue }
    try { $candidateIssue = $candidateIssueJson | ConvertFrom-Json }
    catch { continue }
    if ([string]$candidateIssue.state -ne "OPEN") { continue }

    $stateFile = $candidate
    $state = $candidateState
    $issue = $candidateIssue
    break
}

if ($null -eq $stateFile -or $null -eq $state -or $null -eq $issue) {
    Write-Output "No open zero-change lifecycle is available for diagnosis."
    exit 2
}

$worktreePath = [string]$state.worktreePath
if (-not (Test-Path -LiteralPath $worktreePath -PathType Container)) {
    throw "Dedicated zero-change worktree was not found."
}
if ([string]::IsNullOrWhiteSpace($RecoveryCodexModel)) {
    throw "Diagnosis Codex model must be explicit and non-empty."
}

$promptPath = (New-TemporaryFile).FullName
$outputPath = Join-Path $WorktreeRoot ("{0}-zero-change-diagnosis.txt" -f [int]$state.issueNumber)
try {
    Set-Content -LiteralPath $promptPath -Encoding UTF8 -Value @"
You are performing a bounded read-only diagnosis of a Codex task that exited successfully but changed no files.
Inspect the dedicated worktree and the Issue below. Do not write files, run Git write commands, commit, push, create a PR, deploy, order, notify, access secrets, or expose repository contents.
Explain briefly why the implementation likely produced zero repository changes. Focus on concrete task/repository constraints, missing context, analysis-only behavior, or whether the requested change is already satisfied.
Do not include secrets, environment values, user-home paths, or large file excerpts.

Issue #$([int]$state.issueNumber): $($issue.title)
$($issue.url)

Issue body:
$($issue.body)
"@

    Remove-Item -LiteralPath $outputPath -Force -ErrorAction SilentlyContinue
    $previousErrorActionPreference = $ErrorActionPreference
    $exitCode = -1
    try {
        $ErrorActionPreference = "Continue"
        Get-Content -LiteralPath $promptPath -Raw -Encoding UTF8 |
            & $codexPath exec --model $RecoveryCodexModel --cd $worktreePath --sandbox read-only --output-last-message $outputPath - 1> $null 2> $null
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }

    if ($exitCode -ne 0) { throw "Read-only zero-change diagnosis failed with exit code $exitCode." }
    if (-not (Test-Path -LiteralPath $outputPath -PathType Leaf)) {
        throw "Zero-change diagnosis did not produce a last-message file."
    }

    $raw = [System.IO.File]::ReadAllText($outputPath, [System.Text.Encoding]::UTF8)
    $reasonCode = Get-CodexZeroChangeReasonCode -Text $raw
    if ($reasonCode -notin $AllowedReasonCodes) { $reasonCode = "UNKNOWN_ZERO_CHANGE" }

    $baseFailure = ([string]$state.failureReason -replace "\s*\|\s*zero_change_reason=[A-Z_]+\s*$", "").Trim()
    $state.failureReason = "$baseFailure | zero_change_reason=$reasonCode"
    $state.updatedAtUtc = [DateTime]::UtcNow.ToString("o")
    Set-Content -LiteralPath $stateFile.FullName -Value ($state | ConvertTo-Json -Depth 5) -Encoding UTF8

    Write-Output $reasonCode
    exit 0
}
finally {
    Remove-Item -LiteralPath $promptPath -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $outputPath -Force -ErrorAction SilentlyContinue
}
