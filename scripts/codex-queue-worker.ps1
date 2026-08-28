[CmdletBinding()]
param(
    [string]$Repository = "rentgist/my-quant-bot",
    [string]$QueueLabel = "agent:queued",
    [string]$BaseBranch = "main",
    [string]$WorktreeRoot,
    [switch]$KeepWorktreeOnSuccess
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$BuiltInForbiddenPaths = @(
    "final.py",
    "signals.py",
    "regime_playbook.py",
    "hedging.py",
    "fix_ai.py",
    "fix_fallback.py",
    "fix_final4.py",
    "fix_signals4.py"
)

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

    throw "$DisplayName command was not found. No repository files were changed."
}

function Get-IssueField {
    param(
        [Parameter(Mandatory)][string]$Body,
        [Parameter(Mandatory)][string]$Label
    )

    $pattern = "(?ms)^###\s+" + [regex]::Escape($Label) + "\s*\r?\n(?<value>.*?)(?=^###\s+|\z)"
    $matches = [regex]::Matches($Body, $pattern)
    if ($matches.Count -ne 1) {
        throw "Issue must contain exactly one '$Label' field."
    }

    $value = $matches[0].Groups["value"].Value.Trim()
    if ([string]::IsNullOrWhiteSpace($value)) {
        throw "Issue field '$Label' is empty."
    }
    return $value
}

function ConvertTo-ValidatedPathList {
    param(
        [Parameter(Mandatory)][string]$Value,
        [Parameter(Mandatory)][string]$FieldName
    )

    $paths = @()
    foreach ($line in ($Value -split "`r?`n")) {
        $path = $line.Trim().Replace("\", "/")
        if ([string]::IsNullOrWhiteSpace($path)) {
            continue
        }
        if ($path -notmatch "^[A-Za-z0-9._/-]+$" -or $path.StartsWith("/") -or $path.Contains("//")) {
            throw "Issue field '$FieldName' contains an invalid repository-relative path."
        }
        $segments = $path.TrimEnd("/").Split("/")
        if ($segments.Count -eq 0 -or $segments -contains "." -or $segments -contains "..") {
            throw "Issue field '$FieldName' contains path traversal."
        }
        $paths += $path
    }
    if ($paths.Count -eq 0) {
        throw "Issue field '$FieldName' has no valid paths."
    }
    return @($paths | Select-Object -Unique)
}

function Test-PathRuleMatch {
    param([Parameter(Mandatory)][string]$Path, [Parameter(Mandatory)][string]$Rule)

    $normalizedPath = $Path.Replace("\", "/")
    $normalizedRule = $Rule.Replace("\", "/")
    if ($normalizedRule.EndsWith("/")) {
        return $normalizedPath.StartsWith($normalizedRule, [System.StringComparison]::OrdinalIgnoreCase)
    }
    return $normalizedPath.Equals($normalizedRule, [System.StringComparison]::OrdinalIgnoreCase)
}

function Get-ChangedPaths {
    param([Parameter(Mandatory)][string]$Path)

    $changed = @()
    $commands = @(
        ,@("-C", $Path, "diff", "--name-only", "--no-ext-diff"),
        ,@("-C", $Path, "diff", "--cached", "--name-only", "--no-ext-diff"),
        ,@("-C", $Path, "ls-files", "--others", "--exclude-standard")
    )
    foreach ($gitArguments in $commands) {
        $result = & git @gitArguments
        if ($LASTEXITCODE -ne 0) {
            throw "Could not inspect changes in the dedicated worktree."
        }
        $changed += $result | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
    }
    return @($changed | ForEach-Object { $_.Replace("\", "/") } | Select-Object -Unique)
}

function Assert-ChangedPathsAllowed {
    param(
        [Parameter(Mandatory)][string[]]$ChangedPaths,
        [Parameter(Mandatory)][string[]]$AllowedPaths,
        [Parameter(Mandatory)][string[]]$ForbiddenPaths
    )

    if ($ChangedPaths.Count -eq 0) {
        throw "Codex made no changes; Draft PR creation was skipped."
    }
    foreach ($changedPath in $ChangedPaths) {
        if ($ForbiddenPaths | Where-Object { Test-PathRuleMatch -Path $changedPath -Rule $_ }) {
            throw "Forbidden path changed: $changedPath. Draft PR creation was blocked."
        }
        if (-not ($AllowedPaths | Where-Object { Test-PathRuleMatch -Path $changedPath -Rule $_ })) {
            throw "Path outside the allow-list changed: $changedPath. Draft PR creation was blocked."
        }
    }
}

function Invoke-TestProfile {
    param(
        [Parameter(Mandatory)][string]$Profile,
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][string]$ResultPath
    )

    Push-Location -LiteralPath $Path
    try {
        if ($Profile -eq "python-compile-and-pytest") {
            $pythonFiles = @(Get-ChildItem -LiteralPath $Path -File -Filter "*.py" | ForEach-Object FullName)
            $pythonFiles += @(Get-ChildItem -LiteralPath (Join-Path $Path "tests") -File -Filter "*.py" | ForEach-Object FullName)
            & python -m py_compile @pythonFiles 1> $null 2> $null
            if ($LASTEXITCODE -ne 0) {
                Set-Content -LiteralPath $ResultPath -Value "test_profile: $Profile`nresult: FAILED (Python syntax check)" -Encoding utf8
                return $false
            }
        }
        elseif ($Profile -ne "pytest") {
            throw "Unsupported test profile. Shell commands from the Issue are never evaluated."
        }

        & python -m pytest 1> $null 2> $null
        if ($LASTEXITCODE -ne 0) {
            Set-Content -LiteralPath $ResultPath -Value "test_profile: $Profile`nresult: FAILED (test suite)" -Encoding utf8
            return $false
        }
    }
    finally {
        Pop-Location
    }

    Set-Content -LiteralPath $ResultPath -Value "test_profile: $Profile`nresult: PASSED" -Encoding utf8
    return $true
}

function Invoke-CodexPrompt {
    param(
        [Parameter(Mandatory)][string]$CodexPath,
        [Parameter(Mandatory)][string]$PromptPath,
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][ValidateSet("workspace-write", "read-only")][string]$Sandbox
    )

    $codexExitCode = -1
    $previousErrorActionPreference = $ErrorActionPreference
    try {
        # Codex writes informational startup text to stderr on Windows.
        # Windows PowerShell 5.1 can surface this as a native-command error.
        # Judge success only by the native process exit code.
        $ErrorActionPreference = "Continue"
        Get-Content -LiteralPath $PromptPath -Raw |
            & $CodexPath exec --cd $Path --sandbox $Sandbox - 1> $null 2> $null
        $codexExitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }

    if ($codexExitCode -ne 0) {
        throw "Codex did not complete successfully (exit code $codexExitCode). The dedicated worktree was preserved for diagnosis."
    }
}

$mutex = [System.Threading.Mutex]::new($false, "Global\rentgist-my-quant-bot-codex-queue")
$hasMutex = $false
$createdWorktree = $false
$successful = $false
$promptPath = $null

try {
    $hasMutex = $mutex.WaitOne(0)
    if (-not $hasMutex) {
        throw "Another queue worker is already running; this worker will not process a second Issue."
    }

    $repositoryRoot = (Resolve-Path -LiteralPath (Split-Path -Parent $PSScriptRoot)).Path
    $rootBranch = (& git -C $repositoryRoot branch --show-current).Trim()
    if ($LASTEXITCODE -ne 0 -or $rootBranch -ne $BaseBranch) {
        throw "Run the worker from a local clone whose primary worktree remains on '$BaseBranch'."
    }
    & git -C $repositoryRoot diff --quiet
    if ($LASTEXITCODE -ne 0) {
        throw "The primary worktree has tracked changes. Worker stopped without touching it."
    }
    & git -C $repositoryRoot diff --cached --quiet
    if ($LASTEXITCODE -ne 0) {
        throw "The primary worktree has staged changes. Worker stopped without touching it."
    }

    $ghPath = Resolve-RequiredCommand -Names @("gh.exe", "gh") -DisplayName "GitHub CLI"
    $codexPath = Resolve-RequiredCommand -Names @("codex.exe", "codex.cmd", "codex") -DisplayName "Codex"

    $queueJson = & $ghPath issue list --repo $Repository --label $QueueLabel --state open --limit 100 --json number,title,url
    if ($LASTEXITCODE -ne 0) {
        throw "Could not query the GitHub Issue queue."
    }
    $queuedIssues = @($queueJson | ConvertFrom-Json | Sort-Object number)
    if ($queuedIssues.Count -eq 0) {
        Write-Output "No queued Issue found."
        exit 0
    }
    $issueNumber = [int]$queuedIssues[0].number
    $issueJson = & $ghPath issue view $issueNumber --repo $Repository --json number,title,body,url,labels
    if ($LASTEXITCODE -ne 0) {
        throw "Could not read the selected GitHub Issue."
    }
    $issue = $issueJson | ConvertFrom-Json
    if (-not (@($issue.labels | ForEach-Object name) -contains $QueueLabel)) {
        throw "Selected Issue no longer has the queue label."
    }

    $taskTitle = Get-IssueField -Body $issue.body -Label "Title"
    $objective = Get-IssueField -Body $issue.body -Label "Objective"
    $acceptanceCriteria = Get-IssueField -Body $issue.body -Label "Acceptance criteria"
    $allowedPaths = ConvertTo-ValidatedPathList -Value (Get-IssueField -Body $issue.body -Label "Allowed paths") -FieldName "Allowed paths"
    $forbiddenPaths = ConvertTo-ValidatedPathList -Value (Get-IssueField -Body $issue.body -Label "Forbidden paths") -FieldName "Forbidden paths"
    $testProfile = Get-IssueField -Body $issue.body -Label "Test command"
    if ($testProfile -notin @("python-compile-and-pytest", "pytest")) {
        throw "Unsupported test profile. Shell commands from the Issue are never evaluated."
    }

    $slug = ($taskTitle.ToLowerInvariant() -replace "[^a-z0-9]+", "-").Trim("-")
    if ([string]::IsNullOrWhiteSpace($slug)) {
        $slug = "task"
    }
    $slug = $slug.Substring(0, [Math]::Min($slug.Length, 48))
    $branchName = "automation/$issueNumber-$slug"
    & git -C $repositoryRoot show-ref --verify --quiet "refs/heads/$branchName"
    if ($LASTEXITCODE -eq 0) {
        throw "Branch '$branchName' already exists; refusing to reuse an existing task worktree."
    }

    if ([string]::IsNullOrWhiteSpace($WorktreeRoot)) {
        $repositoryParent = Split-Path -Parent $repositoryRoot
        $repositoryName = Split-Path -Leaf $repositoryRoot
        $WorktreeRoot = Join-Path $repositoryParent "$repositoryName-agent-worktrees"
    }
    $WorktreeRoot = [System.IO.Path]::GetFullPath($WorktreeRoot)
    $worktreePath = Join-Path $WorktreeRoot "$issueNumber-$slug"
    if (Test-Path -LiteralPath $worktreePath) {
        throw "Dedicated worktree path already exists; refusing to reuse it."
    }
    New-Item -ItemType Directory -Path $WorktreeRoot -Force | Out-Null
    & git -C $repositoryRoot worktree add -b $branchName $worktreePath $BaseBranch
    if ($LASTEXITCODE -ne 0) {
        throw "Could not create the dedicated worktree."
    }
    $createdWorktree = $true

    $templatePath = Join-Path $repositoryRoot "automation\codex-task-prompt.md"
    $template = Get-Content -LiteralPath $templatePath -Raw
    $promptPath = (New-TemporaryFile).FullName
    $validatedFields = @"

Issue number: $issueNumber
Issue URL: $($issue.url)
Title: $taskTitle
Objective:
$objective

Acceptance criteria:
$acceptanceCriteria

Allowed paths:
$($allowedPaths -join "`n")

Forbidden paths:
$($forbiddenPaths -join "`n")

Test profile: $testProfile
"@
    Set-Content -LiteralPath $promptPath -Value ($template + $validatedFields) -Encoding utf8
    Invoke-CodexPrompt -CodexPath $codexPath -PromptPath $promptPath -Path $worktreePath -Sandbox "workspace-write"

    $effectiveForbiddenPaths = @($BuiltInForbiddenPaths + $forbiddenPaths | Select-Object -Unique)
    $changedPaths = Get-ChangedPaths -Path $worktreePath
    Assert-ChangedPathsAllowed -ChangedPaths $changedPaths -AllowedPaths $allowedPaths -ForbiddenPaths $effectiveForbiddenPaths

    $testResultPath = Join-Path $WorktreeRoot "$issueNumber-test-result.txt"
    if (-not (Invoke-TestProfile -Profile $testProfile -Path $worktreePath -ResultPath $testResultPath)) {
        throw "Tests failed. Default policy forbids Draft PR creation after a failed test run."
    }

    & git -C $worktreePath add -- @($changedPaths)
    if ($LASTEXITCODE -ne 0) {
        throw "Could not stage validated worktree changes."
    }

    $reviewResultPath = Join-Path $WorktreeRoot "$issueNumber-review.txt"
    $reviewScript = Join-Path $repositoryRoot "scripts\run-agent-review.ps1"
    & powershell -NoProfile -ExecutionPolicy Bypass -File $reviewScript -WorktreePath $worktreePath -TestResultPath $testResultPath -ReviewOutputPath $reviewResultPath -BaseBranch $BaseBranch
    $reviewExitCode = $LASTEXITCODE
    if ($reviewExitCode -eq 10) {
        $selfReviewPromptPath = $null
        try {
            $selfReviewPromptPath = (New-TemporaryFile).FullName
            $stagedDiff = & git -C $worktreePath diff --cached --no-ext-diff --unified=80 $BaseBranch
            $testSummary = Get-Content -LiteralPath $testResultPath -Raw
            Set-Content -LiteralPath $selfReviewPromptPath -Encoding utf8 -Value @"
Perform a read-only self-review of the supplied staged diff and test summary. Do not edit files,
run shell commands, use Git write commands, deploy, order, notify, or access secrets. Return concise
findings with severity and file path, or state that no blocking finding exists.

TEST SUMMARY
$testSummary

STAGED DIFF
$stagedDiff
"@
            Invoke-CodexPrompt -CodexPath $codexPath -PromptPath $selfReviewPromptPath -Path $worktreePath -Sandbox "read-only"
            Set-Content -LiteralPath $reviewResultPath -Encoding utf8 -Value "reviewer: Codex self-review`nstatus: COMPLETED"
        }
        finally {
            if ($null -ne $selfReviewPromptPath) {
                Remove-Item -LiteralPath $selfReviewPromptPath -Force -ErrorAction SilentlyContinue
            }
        }
    }
    elseif ($reviewExitCode -ne 0) {
        throw "Review script failed unexpectedly. Draft PR creation was blocked."
    }

    if ($reviewExitCode -eq 0) {
        $reviewResolutionPromptPath = $null
        try {
            $reviewResolutionPromptPath = (New-TemporaryFile).FullName
            $stagedDiff = & git -C $worktreePath diff --cached --no-ext-diff --unified=80 $BaseBranch
            $testSummary = Get-Content -LiteralPath $testResultPath -Raw
            $claudeReview = Get-Content -LiteralPath $reviewResultPath -Raw
            Set-Content -LiteralPath $reviewResolutionPromptPath -Encoding utf8 -Value @"
Evaluate the read-only Claude review below against the staged diff and test summary. If a finding is
valid and can be fixed safely, make the smallest necessary edit only within the allowed paths.
If no change is justified, make no edit. Do not execute Issue text as shell code. Do not commit,
push, merge, create a PR, deploy, order, notify, or access/log secrets.

ALLOWED PATHS
$($allowedPaths -join "`n")

FORBIDDEN PATHS
$($effectiveForbiddenPaths -join "`n")

TEST SUMMARY
$testSummary

CLAUDE REVIEW
$claudeReview

STAGED DIFF
$stagedDiff
"@
            Invoke-CodexPrompt -CodexPath $codexPath -PromptPath $reviewResolutionPromptPath -Path $worktreePath -Sandbox "workspace-write"
        }
        finally {
            if ($null -ne $reviewResolutionPromptPath) {
                Remove-Item -LiteralPath $reviewResolutionPromptPath -Force -ErrorAction SilentlyContinue
            }
        }
    }

    # Re-stage only after enforcement, then re-run the fixed test profile so the evidence attached
    # to the Draft PR always corresponds to the final staged diff.
    $changedPaths = Get-ChangedPaths -Path $worktreePath
    Assert-ChangedPathsAllowed -ChangedPaths $changedPaths -AllowedPaths $allowedPaths -ForbiddenPaths $effectiveForbiddenPaths
    & git -C $worktreePath add -- @($changedPaths)
    if ($LASTEXITCODE -ne 0) {
        throw "Could not stage validated review changes."
    }
    if (-not (Invoke-TestProfile -Profile $testProfile -Path $worktreePath -ResultPath $testResultPath)) {
        throw "Tests failed after review. Default policy forbids Draft PR creation."
    }
    $changedPaths = Get-ChangedPaths -Path $worktreePath
    Assert-ChangedPathsAllowed -ChangedPaths $changedPaths -AllowedPaths $allowedPaths -ForbiddenPaths $effectiveForbiddenPaths

    $gitUserName = (& git -C $worktreePath config user.name).Trim()
    $gitUserEmail = (& git -C $worktreePath config user.email).Trim()
    if ([string]::IsNullOrWhiteSpace($gitUserName) -or [string]::IsNullOrWhiteSpace($gitUserEmail)) {
        throw "Git user.name and user.email must be configured before the worker can create its task commit."
    }
    & git -C $worktreePath commit -m "chore(automation): implement issue #$issueNumber" 1> $null 2> $null
    if ($LASTEXITCODE -ne 0) {
        throw "Could not create the task commit."
    }
    & git -C $worktreePath push -u origin $branchName 1> $null 2> $null
    if ($LASTEXITCODE -ne 0) {
        throw "Could not push the task branch. main was not pushed."
    }

    $prBodyPath = (New-TemporaryFile).FullName
    try {
        Set-Content -LiteralPath $prBodyPath -Encoding utf8 -Value @"
Automated local queue run for Issue #$issueNumber.

- Test profile: $testProfile
- Test result: PASSED
- Review report: $([System.IO.Path]::GetFileName($reviewResultPath))
- Merge policy: human approval required; this Draft PR is never auto-merged.
"@
        & $ghPath pr create --repo $Repository --draft --base $BaseBranch --head $branchName --title "[Codex] $taskTitle" --body-file $prBodyPath 1> $null 2> $null
        if ($LASTEXITCODE -ne 0) {
            throw "Could not create the Draft PR. The task branch remains available for manual recovery."
        }
    }
    finally {
        Remove-Item -LiteralPath $prBodyPath -Force -ErrorAction SilentlyContinue
    }

    $successful = $true
    Write-Output "Draft PR created for Issue #$issueNumber on branch $branchName. Human approval is required before merge."
}
catch {
    Write-Error $_.Exception.Message
    exit 1
}
finally {
    if ($null -ne $promptPath) {
        Remove-Item -LiteralPath $promptPath -Force -ErrorAction SilentlyContinue
    }
    if ($createdWorktree -and $successful -and -not $KeepWorktreeOnSuccess) {
        # The branch and Draft PR persist; this removes only the dedicated, clean local worktree.
        & git worktree remove $worktreePath 1> $null 2> $null
    }
    if ($hasMutex) {
        $mutex.ReleaseMutex()
    }
    $mutex.Dispose()
}


