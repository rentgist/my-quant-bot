[CmdletBinding()]
param(
    [string]$Repository = "rentgist/my-quant-bot",
    [ValidateRange(1, 2147483647)]
    [int]$HealthIssueNumber = 35,
    [string]$RepositoryRoot,
    [string]$BaseBranch = "main",
    [string]$SyncStatus = "unknown",
    [int]$WorkerExitCode = -1,
    [ValidateRange(1, 1440)]
    [int]$ScheduleIntervalMinutes = 15,
    [switch]$SelfTest
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Resolve-RequiredCommand {
    param(
        [Parameter(Mandatory)][string[]]$Names,
        [Parameter(Mandatory)][string]$DisplayName
    )

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

function ConvertTo-SafeValue {
    param(
        [AllowNull()][string]$Text,
        [int]$MaxLength = 120
    )

    if ([string]::IsNullOrWhiteSpace($Text)) {
        return "unknown"
    }

    $safe = $Text -replace "`r", " " -replace "`n", " "
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

function Invoke-GitText {
    param(
        [Parameter(Mandatory)][string]$Root,
        [Parameter(Mandatory)][string[]]$Arguments
    )

    $previousErrorActionPreference = $ErrorActionPreference
    $exitCode = -1
    $output = $null
    try {
        $ErrorActionPreference = "Continue"
        $output = & git -C $Root @Arguments 2> $null
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }

    if ($exitCode -ne 0) {
        return $null
    }
    return ((@($output) | ForEach-Object { [string]$_ }) -join "`n").Trim()
}

function Get-GitDirtyState {
    param(
        [Parameter(Mandatory)][string]$Root,
        [switch]$Staged
    )

    $arguments = @("diff")
    if ($Staged) {
        $arguments += "--cached"
    }
    $arguments += @("--quiet", "--no-ext-diff")

    $previousErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        & git -C $Root @arguments 1> $null 2> $null
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }

    if ($exitCode -eq 0) { return "false" }
    if ($exitCode -eq 1) { return "true" }
    return "unknown"
}

function Get-ShortSha {
    param([AllowNull()][string]$Sha)

    if ([string]::IsNullOrWhiteSpace($Sha)) {
        return "unknown"
    }
    $value = $Sha.Trim()
    if ($value.Length -le 12) {
        return $value
    }
    return $value.Substring(0, 12)
}

function New-HeartbeatBody {
    param(
        [string]$Status,
        [string]$ObservedAtUtc,
        [string]$ObservedAtLocal,
        [string]$SyncStatusValue,
        [string]$BaseBranchValue,
        [string]$LocalBranch,
        [string]$LocalHead,
        [string]$OriginHead,
        [string]$Synchronized,
        [string]$TrackedDirty,
        [string]$StagedDirty,
        [int]$WorkerCode,
        [int]$IntervalMinutes
    )

    return @"
<!-- codex-worker-heartbeat -->
Local worker heartbeat

- status: $Status
- observed_at_utc: $ObservedAtUtc
- observed_at_local: $ObservedAtLocal
- sync_status: $SyncStatusValue
- base_branch: $BaseBranchValue
- local_branch: $LocalBranch
- local_head: $LocalHead
- origin_main_head: $OriginHead
- synchronized: $Synchronized
- tracked_dirty: $TrackedDirty
- staged_dirty: $StagedDirty
- worker_exit_code: $WorkerCode
- schedule_interval_minutes: $IntervalMinutes

This issue is machine-managed by the scheduled local worker. It intentionally publishes only bounded operational state: no local usernames, machine names, repository paths, secrets, or raw agent output.
"@
}

function Invoke-SelfTest {
    $safe = ConvertTo-SafeValue -Text 'C:\Users\Alice\repo\file.txt ghp_ABC123XYZ Bearer secret-value' -MaxLength 120
    if ($safe -match 'Alice' -or $safe -match 'ghp_' -or $safe -match 'secret-value') {
        throw 'Heartbeat sanitizer leaked private or token-like text.'
    }
    if ($safe -notmatch '<local-path>' -or $safe -notmatch '<redacted-token>') {
        throw 'Heartbeat sanitizer did not emit expected redaction markers.'
    }

    $body = New-HeartbeatBody -Status 'healthy' -ObservedAtUtc '2026-01-01T00:00:00.0000000Z' -ObservedAtLocal '2026-01-01T09:00:00.0000000+09:00' -SyncStatusValue 'synced' -BaseBranchValue 'main' -LocalBranch 'main' -LocalHead '0123456789ab' -OriginHead '0123456789ab' -Synchronized 'true' -TrackedDirty 'false' -StagedDirty 'false' -WorkerCode 0 -IntervalMinutes 15
    if ($body -notmatch 'synchronized: true' -or $body -notmatch 'worker_exit_code: 0') {
        throw 'Heartbeat body regression failed.'
    }

    Write-Output 'Local worker heartbeat self-test passed.'
}

if ($SelfTest) {
    Invoke-SelfTest
    exit 0
}

if ([string]::IsNullOrWhiteSpace($RepositoryRoot)) {
    $RepositoryRoot = Split-Path -Parent $PSScriptRoot
}
$RepositoryRoot = [System.IO.Path]::GetFullPath($RepositoryRoot)

$localBranchRaw = Invoke-GitText -Root $RepositoryRoot -Arguments @("branch", "--show-current")
if ([string]::IsNullOrWhiteSpace($localBranchRaw)) {
    $localBranchRaw = "detached-or-unknown"
}
$localHeadRaw = Invoke-GitText -Root $RepositoryRoot -Arguments @("rev-parse", "HEAD")
$originHeadRaw = Invoke-GitText -Root $RepositoryRoot -Arguments @("rev-parse", "origin/$BaseBranch")
$trackedDirty = Get-GitDirtyState -Root $RepositoryRoot
$stagedDirty = Get-GitDirtyState -Root $RepositoryRoot -Staged

$localBranch = ConvertTo-SafeValue -Text $localBranchRaw
$baseBranchSafe = ConvertTo-SafeValue -Text $BaseBranch
$syncStatusSafe = ConvertTo-SafeValue -Text $SyncStatus
$localHead = Get-ShortSha -Sha $localHeadRaw
$originHead = Get-ShortSha -Sha $originHeadRaw
$synchronized = if (-not [string]::IsNullOrWhiteSpace($localHeadRaw) -and -not [string]::IsNullOrWhiteSpace($originHeadRaw) -and $localHeadRaw.Trim() -eq $originHeadRaw.Trim()) { "true" } else { "false" }

$healthy = ($syncStatusSafe -eq "synced") -and ($localBranch -eq $baseBranchSafe) -and ($synchronized -eq "true") -and ($trackedDirty -eq "false") -and ($stagedDirty -eq "false") -and ($WorkerExitCode -eq 0)
$status = if ($healthy) { "healthy" } else { "degraded" }
$observedAtUtc = [DateTime]::UtcNow.ToString("o")
$observedAtLocal = (Get-Date).ToString("o")

$body = New-HeartbeatBody -Status $status -ObservedAtUtc $observedAtUtc -ObservedAtLocal $observedAtLocal -SyncStatusValue $syncStatusSafe -BaseBranchValue $baseBranchSafe -LocalBranch $localBranch -LocalHead $localHead -OriginHead $originHead -Synchronized $synchronized -TrackedDirty $trackedDirty -StagedDirty $stagedDirty -WorkerCode $WorkerExitCode -IntervalMinutes $ScheduleIntervalMinutes

$ghPath = Resolve-RequiredCommand -Names @("gh.exe", "gh") -DisplayName "GitHub CLI"
$previousErrorActionPreference = $ErrorActionPreference
try {
    $ErrorActionPreference = "Continue"
    & $ghPath issue edit $HealthIssueNumber --repo $Repository --body $body 1> $null 2> $null
    $exitCode = $LASTEXITCODE
}
finally {
    $ErrorActionPreference = $previousErrorActionPreference
}

if ($exitCode -ne 0) {
    throw "Could not publish local worker heartbeat to Issue #$HealthIssueNumber."
}

exit 0
