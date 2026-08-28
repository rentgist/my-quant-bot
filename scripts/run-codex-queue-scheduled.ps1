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

$mutex = [System.Threading.Mutex]::new($false, "Global\rentgist-my-quant-bot-codex-queue-scheduled")
$hasMutex = $false

try {
    $hasMutex = $mutex.WaitOne(0)
    if (-not $hasMutex) {
        Write-Output "A scheduled queue wrapper is already running; this invocation exits without overlap."
        exit 0
    }

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
    exit $LASTEXITCODE
}
finally {
    if ($hasMutex) {
        $mutex.ReleaseMutex()
    }
    $mutex.Dispose()
}
