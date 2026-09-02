[CmdletBinding()]
param(
    [string]$Repository = "rentgist/my-quant-bot"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ($Repository -notmatch "^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$") {
    throw "Repository must use the owner/repository form."
}

function Resolve-GitHubCli {
    $command = Get-Command "gh.exe", "gh" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -eq $command) {
        throw "GitHub CLI was not found. No repository state was changed."
    }
    return $command.Source
}

function Get-ManagementField {
    param(
        [Parameter(Mandatory)][string]$Body,
        [Parameter(Mandatory)][string]$Label
    )

    $pattern = "(?ms)^###\s+" + [regex]::Escape($Label) + "\s*\r?\n(?<value>.*?)(?=^###\s+|\z)"
    $matches = [regex]::Matches($Body, $pattern)
    if ($matches.Count -ne 1) {
        return "not recorded"
    }
    $value = $matches[0].Groups["value"].Value.Trim()
    if ([string]::IsNullOrWhiteSpace($value)) {
        return "not recorded"
    }
    return (($value -split "`r?`n")[0]).Trim()
}

function Get-LifecycleStatus {
    param([Parameter(Mandatory)]$Issue)

    $labels = @($Issue.labels | ForEach-Object { $_.name })
    foreach ($status in @("queued", "running", "blocked", "done")) {
        if ($labels -contains "agent:$status") {
            return $status
        }
    }
    return $null
}

function Write-IssueGroup {
    param(
        [Parameter(Mandatory)][string]$Status,
        [Parameter(Mandatory)][object[]]$Issues
    )

    Write-Output ("{0}: {1}" -f $Status, $Issues.Count)
    foreach ($issue in $Issues) {
        $priority = Get-ManagementField -Body $issue.body -Label "Priority"
        $risk = Get-ManagementField -Body $issue.body -Label "Risk tier"
        $nextAction = Get-ManagementField -Body $issue.body -Label "Next action"
        Write-Output ("- #{0} [{1}/{2}] {3} | next: {4} | {5}" -f $issue.number, $priority, $risk, $issue.title, $nextAction, $issue.url)
    }
}

$ghPath = Resolve-GitHubCli
$issueJson = & $ghPath issue list --repo $Repository --state open --limit 100 --json number,title,url,labels,body
if ($LASTEXITCODE -ne 0) {
    throw "Could not read GitHub Issues. No repository state was changed."
}
$prJson = & $ghPath pr list --repo $Repository --state open --limit 100 --json number,title,url,isDraft
if ($LASTEXITCODE -ne 0) {
    throw "Could not read GitHub pull requests. No repository state was changed."
}

$issues = @($issueJson | ConvertFrom-Json)
$draftPrs = @($prJson | ConvertFrom-Json | Where-Object { [bool]$_.isDraft })
$managedIssues = @($issues | Where-Object { $null -ne (Get-LifecycleStatus -Issue $_) })

Write-Output "Management summary: $Repository"
foreach ($status in @("queued", "running", "blocked", "done")) {
    $group = @($managedIssues | Where-Object { (Get-LifecycleStatus -Issue $_) -eq $status } | Sort-Object number)
    Write-IssueGroup -Status $status -Issues $group
}

Write-Output ("Open Draft PRs: {0}" -f $draftPrs.Count)
foreach ($pr in ($draftPrs | Sort-Object number)) {
    Write-Output ("- #{0} {1} | {2}" -f $pr.number, $pr.title, $pr.url)
}

$decisionIssues = @($managedIssues | Where-Object {
    $labels = @($_.labels | ForEach-Object { $_.name })
    $status = Get-LifecycleStatus -Issue $_
    $status -eq "blocked" -or ($status -ne "done" -and $labels -contains "agent:approval-required")
} | Sort-Object number)
Write-Output ("User decision required: {0}" -f ($decisionIssues.Count + $draftPrs.Count))
foreach ($issue in $decisionIssues) {
    $nextAction = Get-ManagementField -Body $issue.body -Label "Next action"
    Write-Output ("- Issue #{0}: {1} | next: {2} | {3}" -f $issue.number, $issue.title, $nextAction, $issue.url)
}
foreach ($pr in ($draftPrs | Sort-Object number)) {
    Write-Output ("- Draft PR #{0}: review, explicitly approve where required, then decide whether to merge | {1}" -f $pr.number, $pr.url)
}
