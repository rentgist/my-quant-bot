[CmdletBinding()]
param(
    [string]$Repository = "rentgist/my-quant-bot",
    [string]$QueueLabel = "agent:queued",
    [string]$BaseBranch = "main",
    [string]$WorktreeRoot,
    [ValidateRange(1, 10)]
    [int]$MaxTaskAttempts = 3
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

    $currentBranch = (& git -C $RepositoryRoot branch --show-current).Trim()
    if ($LASTEXITCODE -ne 0 -or $currentBranch -ne $BaseBranch) {
        Write-Warning "Control-plane self-update skipped because the base repository is not on '$BaseBranch'."
        return
    }

    $trackedDirty = (Invoke-NativeQuiet -FilePath "git" -Arguments @("-C", $RepositoryRoot, "diff", "--quiet", "--no-ext-diff")) -ne 0
    $stagedDirty = (Invoke-NativeQuiet -FilePath "git" -Arguments @("-C", $RepositoryRoot, "diff", "--cached", "--quiet", "--no-ext-diff")) -ne 0
    if ($trackedDirty -or $stagedDirty) {
        Write-Warning "Control-plane self-update skipped because tracked or staged local changes exist. Untracked files are not considered dirty."
        return
    }

    if ((Invoke-NativeQuiet -FilePath "git" -Arguments @("-C", $RepositoryRoot, "fetch", "origin", $BaseBranch)) -ne 0) {
        Write-Warning "Control-plane self-update could not fetch origin/$BaseBranch; the installed version will continue for this run."
        return
    }

    if ((Invoke-NativeQuiet -FilePath "git" -Arguments @("-C", $RepositoryRoot, "merge", "--ff-only", "origin/$BaseBranch")) -ne 0) {
        Write-Warning "Control-plane self-update could not fast-forward to origin/$BaseBranch; the installed version will continue for this run."
        return
    }
}

$mutex = [System.Threading.Mutex]::new($false, "Global\rentgist-my-quant-bot-codex-queue-scheduled")
$hasMutex = $false

try {
    $hasMutex = $mutex.WaitOne(0)
    if (-not $hasMutex) {
        Write-Output "A scheduled queue wrapper is already running; this invocation exits without overlap."
        exit 0
    }

    $repositoryRoot = Split-Path -Parent $PSScriptRoot
    Sync-BaseBranchIfSafe -RepositoryRoot $repositoryRoot -BaseBranch $BaseBranch

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
    }

    exit $workerExitCode
}
finally {
    if ($hasMutex) {
        $mutex.ReleaseMutex()
    }
    $mutex.Dispose()
}
