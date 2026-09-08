[CmdletBinding()]
param(
    [string]$WorktreePath,
    [string]$TestResultPath,
    [string]$ReviewOutputPath,
    [string]$BaseBranch = "main",
    [ValidateSet("initial", "final")]
    [string]$Round = "initial",
    [ValidateRange(256, 8192)]
    [int]$MaxOutputChars = 2048,
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

function Get-ClaudeVerdict {
    param([AllowNull()][string]$Output)

    if ([string]::IsNullOrWhiteSpace($Output)) {
        return "UNAVAILABLE"
    }

    $matches = [regex]::Matches($Output, '(?im)^\s*VERDICT\s*:\s*(PASS|CHANGES_REQUESTED)\s*$')
    if ($matches.Count -ne 1) {
        return "UNAVAILABLE"
    }

    return $matches[0].Groups[1].Value.ToUpperInvariant()
}

function Get-BoundedText {
    param([AllowNull()][string]$Text, [int]$Limit)

    if ([string]::IsNullOrWhiteSpace($Text)) {
        return "(empty output)"
    }

    $normalized = (($Text -replace "`0", '') -replace '\r\n', "`n").Trim()
    if ($normalized.Length -le $Limit) {
        return $normalized
    }
    return $normalized.Substring(0, $Limit) + "..."
}

function Write-ReviewReport {
    param(
        [Parameter(Mandatory)][ValidateSet("PASS", "CHANGES_REQUESTED", "UNAVAILABLE")][string]$Verdict,
        [Parameter(Mandatory)][string]$Summary,
        [Parameter(Mandatory)][string]$Reason
    )

    $report = @"
reviewer: Claude Code
round: $Round
VERDICT: $Verdict
reason: $Reason
summary:
$Summary
"@
    Set-Content -LiteralPath $ReviewOutputPath -Value $report -Encoding utf8
}

function Exit-WithVerdict {
    param(
        [Parameter(Mandatory)][ValidateSet("PASS", "CHANGES_REQUESTED", "UNAVAILABLE")][string]$Verdict,
        [Parameter(Mandatory)][string]$Summary,
        [Parameter(Mandatory)][string]$Reason
    )

    Write-ReviewReport -Verdict $Verdict -Summary $Summary -Reason $Reason
    if ($Verdict -eq "PASS") {
        Write-Output "Claude review: PASS ($Round)."
        exit 0
    }
    if ($Verdict -eq "CHANGES_REQUESTED") {
        Write-Output "Claude review: CHANGES_REQUESTED ($Round)."
        exit 20
    }
    Write-Output "Claude review: UNAVAILABLE ($Reason)"
    exit 10
}

function Invoke-SelfTest {
    if ((Get-ClaudeVerdict -Output "VERDICT: PASS") -ne "PASS") {
        throw "PASS verdict parsing regression failed."
    }
    if ((Get-ClaudeVerdict -Output "Finding`nVERDICT: CHANGES_REQUESTED") -ne "CHANGES_REQUESTED") {
        throw "CHANGES_REQUESTED verdict parsing regression failed."
    }
    if ((Get-ClaudeVerdict -Output "VERDICT: PASS`nVERDICT: CHANGES_REQUESTED") -ne "UNAVAILABLE") {
        throw "Ambiguous verdict must be unavailable."
    }
    if ((Get-ClaudeVerdict -Output "No machine-readable verdict") -ne "UNAVAILABLE") {
        throw "Missing verdict must be unavailable."
    }
    $bounded = Get-BoundedText -Text ('x' * 5000) -Limit 512
    if ($bounded.Length -gt 515) {
        throw "Bounded review output regression failed."
    }
    Write-Output "Claude review parser self-test passed."
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

try {
    $resolvedWorktree = (Resolve-Path -LiteralPath $WorktreePath).Path
    $resolvedTestResult = (Resolve-Path -LiteralPath $TestResultPath).Path
    $outputParent = Split-Path -Parent $ReviewOutputPath
    if (-not (Test-Path -LiteralPath $outputParent -PathType Container)) {
        New-Item -ItemType Directory -Path $outputParent -Force | Out-Null
    }

    $claudePath = Resolve-OptionalCommand -Names @("claude.cmd", "claude.exe", "claude")
    if ($null -eq $claudePath) {
        Exit-WithVerdict -Verdict "UNAVAILABLE" -Summary "Claude Code command was not found." -Reason "command-not-found"
    }

    $diff = & git -C $resolvedWorktree diff --cached --no-ext-diff --unified=80 $BaseBranch
    if ($LASTEXITCODE -ne 0) {
        throw "Could not read the staged diff for review."
    }
    $testSummary = Get-Content -LiteralPath $resolvedTestResult -Raw
    $reviewPrompt = @"
You are an independent read-only senior code reviewer performing the $Round review round.
Review only the supplied staged diff and test summary. Do not run commands or attempt edits, Git operations,
deployment, ordering, notifications, or secret access. Focus on correctness, regressions, safety boundaries,
and whether the stated tests support the change.

Your response MUST contain exactly one machine-readable verdict line, by itself, in one of these forms:
VERDICT: PASS
VERDICT: CHANGES_REQUESTED

Use CHANGES_REQUESTED only for a concrete blocking defect. Keep the entire response concise. After the verdict,
you may include short findings with severity, file path, and rationale. Never include secrets or local paths.

TEST SUMMARY
$testSummary

STAGED DIFF
$diff
"@

    $tempPrompt = New-TemporaryFile
    $rawOutputPath = [System.IO.Path]::GetTempFileName()
    try {
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
            Exit-WithVerdict -Verdict "UNAVAILABLE" -Summary "Claude Code did not complete the read-only review." -Reason "cli-unavailable-or-unauthenticated"
        }

        $rawOutput = Get-Content -LiteralPath $rawOutputPath -Raw -ErrorAction SilentlyContinue
        $verdict = Get-ClaudeVerdict -Output $rawOutput
        $boundedSummary = Get-BoundedText -Text $rawOutput -Limit $MaxOutputChars
        if ($verdict -eq "UNAVAILABLE") {
            Exit-WithVerdict -Verdict "UNAVAILABLE" -Summary $boundedSummary -Reason "missing-or-ambiguous-verdict"
        }
        Exit-WithVerdict -Verdict $verdict -Summary $boundedSummary -Reason "completed-read-only"
    }
    finally {
        Remove-Item -LiteralPath $tempPrompt.FullName -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $rawOutputPath -Force -ErrorAction SilentlyContinue
    }
}
catch {
    Exit-WithVerdict -Verdict "UNAVAILABLE" -Summary "Claude review could not start safely." -Reason "safe-start-failure"
}
