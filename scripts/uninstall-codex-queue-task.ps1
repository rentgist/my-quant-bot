[CmdletBinding()]
param(
    [string]$TaskName = "MyQuantBot-CodexQueueWorker"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($TaskName) -or $TaskName.IndexOfAny([System.IO.Path]::GetInvalidFileNameChars()) -ge 0) {
    throw "TaskName is invalid."
}

$existingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($null -eq $existingTask) {
    Write-Output "Scheduled task '$TaskName' is not installed."
    exit 0
}

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
Write-Output "Uninstalled scheduled task '$TaskName'. Existing lifecycle diagnostics and task branches were preserved."
