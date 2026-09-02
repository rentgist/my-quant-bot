[CmdletBinding()]
param(
    [string]$TaskName = "MyQuantBot-CodexQueueWorker",
    [ValidateRange(1, 1440)]
    [int]$IntervalMinutes = 15,
    [string]$Repository = "rentgist/my-quant-bot",
    [string]$QueueLabel = "agent:queued",
    [string]$BaseBranch = "main",
    [string]$WorktreeRoot,
    [ValidateRange(1, 10)]
    [int]$MaxTaskAttempts = 3
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($TaskName) -or $TaskName.IndexOfAny([System.IO.Path]::GetInvalidFileNameChars()) -ge 0) {
    throw "TaskName is invalid."
}
if ($Repository -notmatch "^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$") {
    throw "Repository must use the owner/repository form."
}

$wrapperPath = Join-Path $PSScriptRoot "run-codex-queue-scheduled.ps1"
if (-not (Test-Path -LiteralPath $wrapperPath -PathType Leaf)) {
    throw "Scheduled queue wrapper script was not found."
}

$ghCommand = Get-Command "gh.exe", "gh" -ErrorAction SilentlyContinue | Select-Object -First 1
if ($null -eq $ghCommand) {
    throw "GitHub CLI was not found; lifecycle labels were not changed."
}
$labelJson = & $ghCommand.Source label list --repo $Repository --limit 100 --json name 2> $null
if ($LASTEXITCODE -ne 0) {
    throw "Could not verify GitHub lifecycle labels; scheduled task was not installed."
}
$existingLabels = @($labelJson | ConvertFrom-Json | ForEach-Object { $_.name })
$requiredLabels = @(
    @{ Name = $QueueLabel; Color = "1D76DB"; Description = "Queued for the local Codex worker" },
    @{ Name = "agent:running"; Color = "FBCA04"; Description = "Being processed by the local Codex worker" },
    @{ Name = "agent:blocked"; Color = "D93F0B"; Description = "Worker stopped; diagnostics require human review" },
    @{ Name = "agent:done"; Color = "0E8A16"; Description = "Draft PR created; human review and merge required" },
    @{ Name = "agent:approval-required"; Color = "B60205"; Description = "High-risk task requires explicit human approval before merge" }
)
foreach ($label in $requiredLabels) {
    if ($existingLabels -notcontains $label.Name) {
        & $ghCommand.Source label create $label.Name --repo $Repository --color $label.Color --description $label.Description 1> $null 2> $null
        if ($LASTEXITCODE -ne 0) {
            throw "Could not create required GitHub lifecycle label '$($label.Name)'; scheduled task was not installed."
        }
    }
}

$escapedWrapperPath = '"{0}"' -f $wrapperPath.Replace('"', '""')
$arguments = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", $escapedWrapperPath,
    "-Repository", $Repository,
    "-QueueLabel", $QueueLabel,
    "-BaseBranch", $BaseBranch,
    "-MaxTaskAttempts", $MaxTaskAttempts
)
if (-not [string]::IsNullOrWhiteSpace($WorktreeRoot)) {
    $arguments += @("-WorktreeRoot", ('"{0}"' -f $WorktreeRoot.Replace('"', '""')))
}

$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument ($arguments -join " ")
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes) -RepetitionDuration (New-TimeSpan -Days 3650)
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 4)
$userId = "{0}\{1}" -f $env:USERDOMAIN, $env:USERNAME
$principal = New-ScheduledTaskPrincipal -UserId $userId -LogonType S4U -RunLevel Limited
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description "Runs the local Codex GitHub issue queue worker without overlapping scheduled invocations." -Force | Out-Null

Write-Output "Installed scheduled task '$TaskName' every $IntervalMinutes minute(s) for $userId."
