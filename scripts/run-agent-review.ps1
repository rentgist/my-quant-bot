[CmdletBinding()]
param(
    [string]$WorktreePath,
    [string]$TestResultPath,
    [string]$ReviewOutputPath,
    [string]$BaseBranch = "main",
    [ValidateSet("initial", "final")]
    [string]$ReviewRound = "initial",
    [switch]$SelfTest
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Resolve-OptionalCommand {
    param([Parameter(Mandatory)][string[]]$Names)

    foreach ($name in $Names) {
        $command = Get-Command $name -ErrorAction SilentlyContinue
        if ($null -ne $command) {
            return $command.Source
        }
    }

    foreach ($base in @($env:APPDATA, $env:LOCALAPPDATA)) {
        if ([string]::IsNullOrWhiteSpace($base)) {
            continue
        }
        foreach ($name in $Names) {
            $candidate = Join-Path $base "npm\$name"
            if (Test-Path -LiteralPath $candidate -PathType Leaf) {
                return $candidate
            }
        }
    }

    return $null
}

function Get-BoundedText {
    param(
        [AllowNull()][string]$Text,
        [ValidateRange(256, 12000)][int]$MaxLength = 6000
    )

    if ([string]::IsNullOrWhiteSpace($Text)) {
        return "(no reviewer detail)"
    }

    $normalized = $Text -replace "`0", ""
    if ($normalized.Length -le $MaxLength) {
        return $normalized.Trim()
    }
    return ($normalized.Substring(0, $MaxLength).TrimEnd() + "`n[review output truncated]")
}

function Get-ReviewVerdict {
    param([AllowNull()][string]$Text)

    if ([string]::IsNullOrWhiteSpace($Text)) {
        return $null
    }

    $first = @($Text -split "`r?`n" | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Select-Object -First 1)
    if ($first.Count -ne 1) {
        return $null
    }

    $line = $first[0].Trim()
    if ($line -match '^VERDICT:\s*(PASS|CHANGES_REQUESTED)\s*$') {
        return $matches[1]
    }
    return $null
}

function Write-SkipReport {
    param([Parameter(Mandatory)][string]$Reason)

    $report = @"
reviewer: Claude Code
round: $ReviewRound
status: SKIP
verdict: UNKNOWN
reason: $Reason
"@
    Set-Content -LiteralPath $ReviewOutputPath -Value $report -Encoding utf8
    Write-Output "Claude review: SKIP ($Reason)"
    exit 10
}

function Write-FailureReport {
    param([Parameter(Mandatory)][string]$Reason)

    $report = @"
reviewer: Claude Code
round: $ReviewRound
status: FAILED
verdict: UNKNOWN
reason: $Reason
"@
    Set-Content -LiteralPath $ReviewOutputPath -Value $report -Encoding utf8
    Write-Error "Claude review: FAILED ($Reason)"
    exit 1
}

function Write-CompletedReport {
    param(
        [Parameter(Mandatory)][ValidateSet("PASS", "CHANGES_REQUESTED")][string]$Verdict,
        [Parameter(Mandatory)][string]$RawReview
    )

    $detail = Get-BoundedText -Text $RawReview
    $report = @"
reviewer: Claude Code
round: $ReviewRound
status: COMPLETED
verdict: $Verdict

$detail
"@
    Set-Content -LiteralPath $ReviewOutputPath -Value $report -Encoding utf8
}

function Invoke-SelfTest {
    $pass = Get-ReviewVerdict -Text "VERDICT: PASS`nNo blocking findings."
    if ($pass -ne "PASS") { throw "PASS verdict parser regression failed." }

    $changes = Get-ReviewVerdict -Text "`nVERDICT: CHANGES_REQUESTED`n- high: sample.ps1"
    if ($changes -ne "CHANGES_REQUESTED") { throw "CHANGES_REQUESTED verdict parser regression failed." }

    $invalid = Get-ReviewVerdict -Text "Looks good`nVERDICT: PASS"
    if ($null -ne $invalid) { throw "Reviewer verdict must be the first non-empty line." }

    $bounded = Get-BoundedText -Text ("x" * 9000) -MaxLength 6000
    if ($bounded.Length -gt 6040 -or $bounded -notmatch 'truncated') {
        throw "Bounded reviewer output regression failed."
    }

    Write-Output "Claude reviewer verdict self-test passed."
}

if ($SelfTest) {
    Invoke-SelfTest
    exit 0
}

if ([string]::IsNullOrWhiteSpace($WorktreePath) -or
    [string]::IsNullOrWhiteSpace($TestResultPath) -or
    [string]::IsNullOrWhiteSpace($ReviewOutputPath)) {
    throw "WorktreePath, TestResultPath, and ReviewOutputPath are required outside SelfTest mode."
}

$rawOutputPath = $null
$tempPrompt = $null

try {
    $resolvedWorktree = (Resolve-Path -LiteralPath $WorktreePath).Path
    $resolvedTestResult = (Resolve-Path -LiteralPath $TestResultPath).Path
    $outputParent = Split-Path -Parent $ReviewOutputPath
    if (-not (Test-Path -LiteralPath $outputParent -PathType Container)) {
        New-Item -ItemType Directory -Path $outputParent -Force | Out-Null
    }

    $claudePath = Resolve-OptionalCommand -Names @("claude.cmd", "claude.exe", "claude")
    if ($null -eq $claudePath) {
        Write-SkipReport -Reason "Claude Code command was not found."
    }

    $diff = & git -C $resolvedWorktree diff --cached --no-ext-diff --unified=80 $BaseBranch
    if ($LASTEXITCODE -ne 0) {
        throw "Could not read the staged diff for review."
    }
    $testSummary = Get-Content -LiteralPath $resolvedTestResult -Raw

    $reviewPrompt = @"
You are the independent senior reviewer in round '$ReviewRound'. Review only the supplied staged diff and test summary.
You are read-only. Do not attempt edits, shell commands, Git operations, deployment, ordering, notifications, or secret access.

The first non-empty line of your response MUST be exactly one of:
VERDICT: PASS
VERDICT: CHANGES_REQUESTED

Use CHANGES_REQUESTED only for a blocking correctness, safety, stated-requirement, regression, or material maintainability problem. Do not block on style preferences.
After the verdict, provide concise findings with severity, file path, and rationale. Keep the response focused and bounded. If there is no blocking finding, use PASS.

TEST SUMMARY
$testSummary

STAGED DIFF
$diff
"@

    $tempPrompt = New-TemporaryFile
    $rawOutputPath = [System.IO.Path]::GetTempFileName()
    Set-Content -LiteralPath $tempPrompt.FullName -Value $reviewPrompt -Encoding utf8

    Push-Location -LiteralPath $tempPrompt.DirectoryName
    try {
        $previousErrorActionPreference = $ErrorActionPreference
        try {
            $ErrorActionPreference = "Continue"
            Get-Content -LiteralPath $tempPrompt.FullName -Raw |
                & $claudePath -p --permission-mode plan --max-turns 1 --output-format text --disallowedTools "Edit" "Write" "Bash" 1> $rawOutputPath 2> $null
            $claudeExitCode = $LASTEXITCODE
        }
        finally {
            $ErrorActionPreference = $previousErrorActionPreference
        }
    }
    finally {
        Pop-Location
    }

    if ($claudeExitCode -ne 0) {
        Write-SkipReport -Reason "Claude Code is unavailable, unauthenticated, or rejected the read-only review."
    }
    if (-not (Test-Path -LiteralPath $rawOutputPath -PathType Leaf)) {
        Write-SkipReport -Reason "Claude Code produced no review output."
    }

    $rawReview = Get-Content -LiteralPath $rawOutputPath -Raw
    $verdict = Get-ReviewVerdict -Text $rawReview
    if ($null -eq $verdict) {
        Write-FailureReport -Reason "Claude Code returned an invalid or missing machine-readable verdict."
    }

    Write-CompletedReport -Verdict $verdict -RawReview $rawReview
    if ($verdict -eq "PASS") {
        Write-Output "Claude review: PASS ($ReviewRound)."
        exit 0
    }

    Write-Output "Claude review: CHANGES_REQUESTED ($ReviewRound)."
    exit 11
}
catch {
    if (-not [string]::IsNullOrWhiteSpace($ReviewOutputPath)) {
        $outputParent = Split-Path -Parent $ReviewOutputPath
        if (-not [string]::IsNullOrWhiteSpace($outputParent) -and -not (Test-Path -LiteralPath $outputParent -PathType Container)) {
            New-Item -ItemType Directory -Path $outputParent -Force -ErrorAction SilentlyContinue | Out-Null
        }
        try {
            Write-SkipReport -Reason "Claude review could not start safely."
        }
        catch { }
    }
    Write-Error $_.Exception.Message
    exit 1
}
finally {
    if ($null -ne $tempPrompt) {
        Remove-Item -LiteralPath $tempPrompt.FullName -Force -ErrorAction SilentlyContinue
    }
    if ($null -ne $rawOutputPath) {
        Remove-Item -LiteralPath $rawOutputPath -Force -ErrorAction SilentlyContinue
    }
}
