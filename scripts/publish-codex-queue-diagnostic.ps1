[CmdletBinding()]
param(
    [string]$Repository = "rentgist/my-quant-bot",
    [string]$WorktreeRoot,
    [ValidateRange(1, 10)]
    [int]$MaxTaskAttempts = 3
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Resolve-RequiredCommand {
    param([Parameter(Mandatory)][string[]]$Names, [Parameter(Mandatory)][string]$DisplayName)

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

    throw "$DisplayName command was not found."
}

function ConvertTo-SafeDiagnosticText {
    param(
        [string]$Text,
        [string[]]$PrivateRoots
    )

    if ([string]::IsNullOrWhiteSpace($Text)) {
        return "not recorded"
    }

    $safe = $Text -replace "`r", " " -replace "`n", " "
    foreach ($root in $PrivateRoots) {
        if (-not [string]::IsNullOrWhiteSpace($root)) {
            $safe = $safe.Replace($root, "<local-path>")
        }
    }

    $safe = [regex]::Replace($safe, '(?i)github_pat_[A-Za-z0-9_]+', '<redacted-token>')
    $safe = [regex]::Replace($safe, '(?i)gh[pousr]_[A-Za-z0-9]+', '<redacted-token>')
    $safe = [regex]::Replace($safe, '(?i)Bearer\s+\S+', 'Bearer <redacted-token>')
    $safe = [regex]::Replace($safe, '(?i)sk-[A-Za-z0-9_-]{12,}', '<redacted-token>')
    $safe = [regex]::Replace($safe, '(?i)[A-Z]:\\Users\\[^\\\s]+(?:\\[^\s|;]+)*', '<local-path>')

    if ($safe.Length -gt 600) {
        $safe = $safe.Substring(0, 600) + "..."
    }
    return $safe
}

$repositoryRoot = Split-Path -Parent $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($WorktreeRoot)) {
    $repositoryParent = Split-Path -Parent $repositoryRoot
    $repositoryName = Split-Path -Leaf $repositoryRoot
    $WorktreeRoot = Join-Path $repositoryParent "$repositoryName-agent-worktrees"
}
$WorktreeRoot = [System.IO.Path]::GetFullPath($WorktreeRoot)
$lifecycleDirectory = Join-Path $WorktreeRoot "lifecycle"
if (-not (Test-Path -LiteralPath $lifecycleDirectory -PathType Container)) {
    exit 0
}

$stateFile = Get-ChildItem -LiteralPath $lifecycleDirectory -File -Filter "issue-*.json" |
    Sort-Object LastWriteTimeUtc -Descending |
    Select-Object -First 1
if ($null -eq $stateFile) {
    exit 0
}

try {
    $state = Get-Content -LiteralPath $stateFile.FullName -Raw | ConvertFrom-Json
}
catch {
    exit 0
}

if ($null -eq $state.issueNumber) {
    exit 0
}

$ghPath = Resolve-RequiredCommand -Names @("gh.exe", "gh") -DisplayName "GitHub CLI"
$privateRoots = @($env:USERPROFILE, $repositoryRoot, $WorktreeRoot)
$safeFailure = ConvertTo-SafeDiagnosticText -Text ([string]$state.failureReason) -PrivateRoots $privateRoots
$safeBranch = ConvertTo-SafeDiagnosticText -Text ([string]$state.branchName) -PrivateRoots $privateRoots
$attempts = [int]$state.attempts
$phase = ConvertTo-SafeDiagnosticText -Text ([string]$state.phase) -PrivateRoots $privateRoots
$status = ConvertTo-SafeDiagnosticText -Text ([string]$state.status) -PrivateRoots $privateRoots
$next = if ($status -eq "blocked" -or $attempts -ge $MaxTaskAttempts) { "management can diagnose from this GitHub comment; no local log copy/paste is required" } else { "automatic retry remains allowed" }

$body = @"
<!-- codex-queue-diagnostic -->
Codex queue diagnostic (sanitized)

- status: $status
- phase: $phase
- attempt: $attempts of $MaxTaskAttempts
- branch: $safeBranch
- failure: $safeFailure
- next: $next

Local paths, user-home details, and token-like values are redacted before publishing. Full local diagnostics remain private.
"@

$previousErrorActionPreference = $ErrorActionPreference
try {
    $ErrorActionPreference = "Continue"
    & $ghPath issue comment ([int]$state.issueNumber) --repo $Repository --body $body 1> $null 2> $null
}
finally {
    $ErrorActionPreference = $previousErrorActionPreference
}

exit 0
