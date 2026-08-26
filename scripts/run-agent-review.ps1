[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$WorktreePath,

    [Parameter(Mandatory)]
    [string]$TestResultPath,

    [Parameter(Mandatory)]
    [string]$ReviewOutputPath,

    [string]$BaseBranch = "main"
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

function Write-SkipReport {
    param([Parameter(Mandatory)][string]$Reason)

    $report = @"
reviewer: Claude Code
status: SKIP
reason: $Reason
"@
    Set-Content -LiteralPath $ReviewOutputPath -Value $report -Encoding utf8
    Write-Output "Claude review: SKIP ($Reason)"
    exit 10
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
        Write-SkipReport -Reason "Claude Code command was not found."
    }

    $diff = & git -C $resolvedWorktree diff --cached --no-ext-diff --unified=80 $BaseBranch
    if ($LASTEXITCODE -ne 0) {
        throw "Could not read the staged diff for review."
    }
    $testSummary = Get-Content -LiteralPath $resolvedTestResult -Raw
    $reviewPrompt = @"
You are a read-only code reviewer. Review only the supplied staged diff and test summary.
Do not suggest or attempt commands, edits, Git operations, deployment, ordering, notifications, or secret access.
Return concise findings with severity, file path, and rationale. If no blocking finding exists, say so.

TEST SUMMARY
$testSummary

STAGED DIFF
$diff
"@

    $tempPrompt = New-TemporaryFile
    try {
        Set-Content -LiteralPath $tempPrompt.FullName -Value $reviewPrompt -Encoding utf8
        # Plan mode prohibits file edits and shell commands. Running outside the worktree limits
        # the CLI's ambient filesystem context to the supplied diff and test summary.
        Push-Location -LiteralPath $tempPrompt.DirectoryName
        try {
            Get-Content -LiteralPath $tempPrompt.FullName -Raw |
                & $claudePath -p --permission-mode plan --max-turns 1 --output-format text --disallowedTools "Edit" "Write" "Bash" 1> $ReviewOutputPath 2> $null
            $claudeExitCode = $LASTEXITCODE
        }
        finally {
            Pop-Location
        }
    }
    finally {
        Remove-Item -LiteralPath $tempPrompt.FullName -Force -ErrorAction SilentlyContinue
    }

    if ($claudeExitCode -ne 0) {
        Write-SkipReport -Reason "Claude Code is unavailable, unauthenticated, or rejected the read-only review."
    }

    if (-not (Test-Path -LiteralPath $ReviewOutputPath -PathType Leaf)) {
        Write-SkipReport -Reason "Claude Code produced no review output."
    }

    Write-Output "Claude review: completed (read-only)."
    exit 0
}
catch {
    Write-SkipReport -Reason "Claude review could not start safely."
}
