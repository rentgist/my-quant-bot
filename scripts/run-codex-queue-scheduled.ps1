[CmdletBinding()]
param(
    [string]$Repository = "rentgist/my-quant-bot",
    [string]$QueueLabel = "agent:queued",
    [string]$BaseBranch = "main",
    [string]$WorktreeRoot,
    [ValidateRange(1, 10)]
    [int]$MaxTaskAttempts = 3,
    [ValidateRange(1, 2147483647)]
    [int]$HealthIssueNumber = 35,
    [ValidateRange(1, 1440)]
    [int]$ScheduleIntervalMinutes = 15
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Invoke-NativeQuiet {
    param(
        [Parameter(Mandatory)][string]$FilePath,
        [Parameter(Mandatory)][string[]]$Arguments
    )

    $previousErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        & $FilePath @Arguments 1> $null 2> $null
        return $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
}

function Sync-BaseBranchIfSafe {
    param(
        [Parameter(Mandatory)][string]$RepositoryRoot,
        [Parameter(Mandatory)][string]$BaseBranch
    )

    $currentBranchOutput = & git -C $RepositoryRoot branch --show-current
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Control-plane self-update skipped because the current branch could not be read."
        return "branch-check-failed"
    }
    $currentBranch = ((@($currentBranchOutput) | ForEach-Object { [string]$_ }) -join "").Trim()
    if ($currentBranch -ne $BaseBranch) {
        Write-Warning "Control-plane self-update skipped because the base repository is not on '$BaseBranch'."
        return "skipped-not-on-base"
    }

    $trackedDirty = (Invoke-NativeQuiet -FilePath "git" -Arguments @("-C", $RepositoryRoot, "diff", "--quiet", "--no-ext-diff")) -ne 0
    $stagedDirty = (Invoke-NativeQuiet -FilePath "git" -Arguments @("-C", $RepositoryRoot, "diff", "--cached", "--quiet", "--no-ext-diff")) -ne 0
    if ($trackedDirty -or $stagedDirty) {
        Write-Warning "Control-plane self-update skipped because tracked or staged local changes exist. Untracked files are not considered dirty."
        return "skipped-dirty"
    }

    if ((Invoke-NativeQuiet -FilePath "git" -Arguments @("-C", $RepositoryRoot, "fetch", "origin", $BaseBranch)) -ne 0) {
        Write-Warning "Control-plane self-update could not fetch origin/$BaseBranch; the installed version will continue for this run."
        return "fetch-failed"
    }

    if ((Invoke-NativeQuiet -FilePath "git" -Arguments @("-C", $RepositoryRoot, "merge", "--ff-only", "origin/$BaseBranch")) -ne 0) {
        Write-Warning "Control-plane self-update could not fast-forward to origin/$BaseBranch; the installed version will continue for this run."
        return "fast-forward-failed"
    }

    return "synced"
}

$repositoryRoot = Split-Path -Parent $PSScriptRoot
$syncStatus = "not-run"
$workerExitCode = -1
$mutex = [System.Threading.Mutex]::new($false, "Global\rentgist-my-quant-bot-codex-queue-scheduled")
$hasMutex = $false

try {
    $hasMutex = $mutex.WaitOne(0)
    if (-not $hasMutex) {
        Write-Output "A scheduled queue wrapper is already running; this invocation exits without overlap."
        exit 0
    }

    $syncStatus = Sync-BaseBranchIfSafe -RepositoryRoot $repositoryRoot -BaseBranch $BaseBranch

    $workerPath = Join-Path $PSScriptRoot "codex-queue-worker.ps1"
    if (-not (Test-Path -LiteralPath $workerPath -PathType Leaf)) {
        throw "Queue worker script was not found."
    }

    $workerArguments = @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", $workerPath,
        "-Repository", $Repository,
        "-QueueLabel", $QueueLabel,
        "-BaseBranch", $BaseBranch,
        "-MaxTaskAttempts", $MaxTaskAttempts
    )
    if (-not [string]::IsNullOrWhiteSpace($WorktreeRoot)) {
        $workerArguments += @("-WorktreeRoot", $WorktreeRoot)
    }

    & powershell @workerArguments
    $workerExitCode = $LASTEXITCODE

    if ($workerExitCode -ne 0) {
        # Publish the worker's sanitized lifecycle diagnostic first, so management has evidence even
        # if the optional zero-change recovery path cannot produce a safe patch.
        $diagnosticPublisherPath = Join-Path $PSScriptRoot "publish-codex-queue-diagnostic.ps1"
        if (Test-Path -LiteralPath $diagnosticPublisherPath -PathType Leaf) {
            $diagnosticArguments = @(
                "-NoProfile",
                "-ExecutionPolicy", "Bypass",
                "-File", $diagnosticPublisherPath,
                "-Repository", $Repository,
                "-MaxTaskAttempts", $MaxTaskAttempts
            )
            if (-not [string]::IsNullOrWhiteSpace($WorktreeRoot)) {
                $diagnosticArguments += @("-WorktreeRoot", $WorktreeRoot)
            }
            & powershell @diagnosticArguments 1> $null 2> $null
        }

        # Native Windows Codex workspace-write can occasionally exit 0 without changing files.
        # Recovery is intentionally narrow: only a lifecycle whose failure says "Codex made no changes"
        # is eligible. Codex then runs read-only, emits a unified diff, and the host validates every
        # path plus git apply --check before applying anything inside the dedicated task worktree.
        $recoveryPath = Join-Path $PSScriptRoot "recover-codex-zero-change.ps1"
        if (Test-Path -LiteralPath $recoveryPath -PathType Leaf) {
            $recoveryArguments = @(
                "-NoProfile",
                "-ExecutionPolicy", "Bypass",
                "-File", $recoveryPath,
                "-Repository", $Repository,
                "-QueueLabel", $QueueLabel
            )
            if (-not [string]::IsNullOrWhiteSpace($WorktreeRoot)) {
                $recoveryArguments += @("-WorktreeRoot", $WorktreeRoot)
            }

            $recoveryLogPath = [System.IO.Path]::GetTempFileName()
            try {
                $previousErrorActionPreference = $ErrorActionPreference
                try {
                    $ErrorActionPreference = "Continue"
                    & powershell @recoveryArguments *> $recoveryLogPath
                    $recoveryExitCode = $LASTEXITCODE
                }
                finally {
                    $ErrorActionPreference = $previousErrorActionPreference
                }

                if ($recoveryExitCode -eq 0) {
                    # A validated patch was applied and the Issue was requeued. Treat this scheduled
                    # wrapper run as successfully recovered; the normal worker resumes on the next tick.
                    $workerExitCode = 0
                }
                else {
                    # Recovery failures must also be remotely diagnosable. Publish only a sanitized,
                    # bounded summary; the temporary raw output is removed before this run exits.
                    $recoveryDiagnosticPublisherPath = Join-Path $PSScriptRoot "publish-codex-recovery-diagnostic.ps1"
                    if (Test-Path -LiteralPath $recoveryDiagnosticPublisherPath -PathType Leaf) {
                        $recoveryDiagnosticArguments = @(
                            "-NoProfile",
                            "-ExecutionPolicy", "Bypass",
                            "-File", $recoveryDiagnosticPublisherPath,
                            "-Repository", $Repository,
                            "-RecoveryLogPath", $recoveryLogPath
                        )
                        if (-not [string]::IsNullOrWhiteSpace($WorktreeRoot)) {
                            $recoveryDiagnosticArguments += @("-WorktreeRoot", $WorktreeRoot)
                        }
                        & powershell @recoveryDiagnosticArguments 1> $null 2> $null
                    }
                }
            }
            finally {
                Remove-Item -LiteralPath $recoveryLogPath -Force -ErrorAction SilentlyContinue
            }
        }
    }

    exit $workerExitCode
}
finally {
    if ($hasMutex) {
        # Publish a bounded heartbeat on every completed scheduled run. This is best-effort and must
        # never turn a successful worker run into a failure merely because telemetry could not publish.
        $heartbeatPath = Join-Path $PSScriptRoot "publish-codex-worker-heartbeat.ps1"
        if (Test-Path -LiteralPath $heartbeatPath -PathType Leaf) {
            $heartbeatArguments = @(
                "-NoProfile",
                "-ExecutionPolicy", "Bypass",
                "-File", $heartbeatPath,
                "-Repository", $Repository,
                "-HealthIssueNumber", $HealthIssueNumber,
                "-RepositoryRoot", $repositoryRoot,
                "-BaseBranch", $BaseBranch,
                "-SyncStatus", $syncStatus,
                "-WorkerExitCode", $workerExitCode,
                "-ScheduleIntervalMinutes", $ScheduleIntervalMinutes
            )
            $previousHeartbeatErrorActionPreference = $ErrorActionPreference
            try {
                $ErrorActionPreference = "Continue"
                & powershell @heartbeatArguments 1> $null 2> $null
            }
            catch { }
            finally {
                $ErrorActionPreference = $previousHeartbeatErrorActionPreference
            }
        }

        $mutex.ReleaseMutex()
    }
    $mutex.Dispose()
}
