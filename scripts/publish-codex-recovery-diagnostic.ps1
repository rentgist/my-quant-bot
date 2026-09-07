[CmdletBinding()]
param(
    [string]$Repository = "rentgist/my-quant-bot",
    [string]$RecoveryLogPath,
    [string]$WorktreeRoot,
    [switch]$SelfTest
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
        [AllowNull()][string]$Text,
        [string[]]$PrivateRoots,
        [int]$MaxLength = 600
    )

    if ([string]::IsNullOrWhiteSpace($Text)) {
        return "not recorded"
    }

    $safe = $Text -replace "`r", " " -replace "`n", " "
    foreach ($root in @($PrivateRoots)) {
        if (-not [string]::IsNullOrWhiteSpace($root)) {
            $safe = $safe.Replace($root, "<local-path>")
        }
    }

    $safe = [regex]::Replace($safe, '(?i)github_pat_[A-Za-z0-9_]+', '<redacted-token>')
    $safe = [regex]::Replace($safe, '(?i)gh[pousr]_[A-Za-z0-9]+', '<redacted-token>')
    $safe = [regex]::Replace($safe, '(?i)Bearer\s+\S+', 'Bearer <redacted-token>')
    $safe = [regex]::Replace($safe, '(?i)sk-[A-Za-z0-9_-]{12,}', '<redacted-token>')
    $safe = [regex]::Replace($safe, '(?i)[A-Z]:\\Users\\[^\\\s]+(?:\\[^\s|;]+)*', '<local-path>')
    $safe = [regex]::Replace($safe, '\s+', ' ').Trim()

    if ($safe.Length -gt $MaxLength) {
        $safe = $safe.Substring(0, $MaxLength) + "..."
    }
    return $safe
}

function Get-ZeroChangeIssueNumber {
    param([Parameter(Mandatory)][string]$LifecycleDirectory)

    if (-not (Test-Path -LiteralPath $LifecycleDirectory -PathType Container)) {
        return $null
    }

    $stateFile = Get-ChildItem -LiteralPath $LifecycleDirectory -Filter "issue-*.json" -File |
        Sort-Object LastWriteTimeUtc -Descending |
        Where-Object {
            try {
                $candidate = Get-Content -LiteralPath $_.FullName -Raw | ConvertFrom-Json
                $candidate.failureReason -like "*Codex made no changes*"
            }
            catch {
                $false
            }
        } |
        Select-Object -First 1

    if ($null -eq $stateFile) {
        return $null
    }

    try {
        $state = Get-Content -LiteralPath $stateFile.FullName -Raw | ConvertFrom-Json
        if ($null -eq $state.issueNumber) {
            return $null
        }
        return [int]$state.issueNumber
    }
    catch {
        return $null
    }
}

function Invoke-SelfTest {
    $sample = 'failure at C:\Users\Alice\repo\worktree\file.txt using ghp_ABC123XYZ and Bearer secret-value ' + ('x' * 900)
    $safe = ConvertTo-SafeDiagnosticText -Text $sample -PrivateRoots @('C:\Users\Alice', 'C:\Users\Alice\repo') -MaxLength 120

    if ($safe -match 'Alice' -or $safe -match 'ghp_' -or $safe -match 'secret-value') {
        throw 'Recovery diagnostic sanitizer leaked private or token-like text.'
    }
    if ($safe -notmatch '<local-path>' -or $safe -notmatch '<redacted-token>') {
        throw 'Recovery diagnostic sanitizer did not emit expected redaction markers.'
    }
    if ($safe.Length -gt 123) {
        throw 'Recovery diagnostic sanitizer did not bound output length.'
    }

    Write-Output 'Recovery diagnostic sanitizer self-test passed.'
}

if ($SelfTest) {
    Invoke-SelfTest
    exit 0
}

if ([string]::IsNullOrWhiteSpace($RecoveryLogPath) -or -not (Test-Path -LiteralPath $RecoveryLogPath -PathType Leaf)) {
    exit 0
}

$repositoryRoot = Split-Path -Parent $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($WorktreeRoot)) {
    $repositoryParent = Split-Path -Parent $repositoryRoot
    $repositoryName = Split-Path -Leaf $repositoryRoot
    $WorktreeRoot = Join-Path $repositoryParent "$repositoryName-agent-worktrees"
}
$WorktreeRoot = [System.IO.Path]::GetFullPath($WorktreeRoot)
$lifecycleDirectory = Join-Path $WorktreeRoot "lifecycle"
$issueNumber = Get-ZeroChangeIssueNumber -LifecycleDirectory $lifecycleDirectory
if ($null -eq $issueNumber) {
    exit 0
}

$raw = Get-Content -LiteralPath $RecoveryLogPath -Raw
$privateRoots = @($env:USERPROFILE, $repositoryRoot, $WorktreeRoot)
$safeFailure = ConvertTo-SafeDiagnosticText -Text $raw -PrivateRoots $privateRoots -MaxLength 600
$body = @"
<!-- codex-recovery-diagnostic -->
Control-plane recovery diagnostic (sanitized)

- failure: $safeFailure
- next: management can diagnose this recovery failure from GitHub; no local log copy/paste is required

Local paths, user-home details, and token-like values are redacted before publishing. Raw recovery output remains local and temporary.
"@

$ghPath = Resolve-RequiredCommand -Names @("gh.exe", "gh") -DisplayName "GitHub CLI"
$previousErrorActionPreference = $ErrorActionPreference
try {
    $ErrorActionPreference = "Continue"
    & $ghPath issue comment $issueNumber --repo $Repository --body $body 1> $null 2> $null
}
finally {
    $ErrorActionPreference = $previousErrorActionPreference
}

exit 0
