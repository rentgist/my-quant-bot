[CmdletBinding()]
param(
    [string]$TaskSpec = "companies/company-b/tasks/B-TASK-001.json",
    [string]$BaseRef = "company-b/bootstrap-claude-led-v0.1",
    [string]$WorktreeRoot,
    [switch]$KeepWorktree,
    [switch]$PushOnPass,
    [switch]$SelfTest
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$BuiltInForbiddenPaths = @(
    ".ai-company/",
    "scripts/codex-queue-worker.ps1",
    "scripts/run-codex-queue-scheduled.ps1",
    "scripts/publish-codex-worker-heartbeat.ps1",
    "final.py",
    "signals.py",
    "regime_playbook.py",
    "hedging.py",
    "fix_ai.py",
    "fix_fallback.py",
    "fix_final4.py",
    "fix_signals4.py"
)

$SupportedRiskTiers = @("low", "medium", "high")
$SupportedTestProfiles = @("company-b-bootstrap", "pytest")

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

    throw "$DisplayName command was not found. Company B made no repository changes."
}

function Normalize-RepoPath {
    param([Parameter(Mandatory)][string]$Path)

    $normalized = $Path.Trim().Replace("\", "/")
    if ([string]::IsNullOrWhiteSpace($normalized) -or
        $normalized.StartsWith("/") -or
        $normalized.Contains("//") -or
        $normalized -notmatch '^[A-Za-z0-9._/-]+$') {
        throw "Invalid repository-relative path in Company B task spec."
    }

    $segments = $normalized.TrimEnd("/").Split("/")
    if ($segments -contains "." -or $segments -contains "..") {
        throw "Path traversal is not allowed in Company B task specs."
    }

    return $normalized
}

function Test-PathRuleMatch {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][string]$Rule
    )

    $normalizedPath = $Path.Replace("\", "/")
    $normalizedRule = $Rule.Replace("\", "/")
    if ($normalizedRule.EndsWith("/")) {
        return $normalizedPath.StartsWith($normalizedRule, [System.StringComparison]::OrdinalIgnoreCase)
    }
    return $normalizedPath.Equals($normalizedRule, [System.StringComparison]::OrdinalIgnoreCase)
}

function ConvertTo-ValidatedPathArray {
    param(
        [Parameter(Mandatory)]$Values,
        [Parameter(Mandatory)][string]$FieldName
    )

    $paths = @()
    foreach ($value in @($Values)) {
        if ($null -eq $value) {
            continue
        }
        $paths += Normalize-RepoPath -Path ([string]$value)
    }

    if ($paths.Count -eq 0) {
        throw "Company B task field '$FieldName' must contain at least one path."
    }

    return @($paths | Select-Object -Unique)
}

function Get-ChangedPaths {
    param([Parameter(Mandatory)][string]$WorktreePath)

    $changed = @()
    $commands = @(
        ,@("-C", $WorktreePath, "diff", "--name-only", "--no-ext-diff"),
        ,@("-C", $WorktreePath, "diff", "--cached", "--name-only", "--no-ext-diff"),
        ,@("-C", $WorktreePath, "ls-files", "--others", "--exclude-standard")
    )

    foreach ($arguments in $commands) {
        $result = & git @arguments
        if ($LASTEXITCODE -ne 0) {
            throw "Company B could not inspect its isolated worktree."
        }
        $changed += @($result | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    }

    return @($changed | ForEach-Object { $_.Replace("\", "/") } | Select-Object -Unique)
}

function Assert-ChangedPathsAllowed {
    param(
        [Parameter(Mandatory)][string[]]$ChangedPaths,
        [Parameter(Mandatory)][string[]]$AllowedPaths,
        [Parameter(Mandatory)][string[]]$ForbiddenPaths
    )

    if (@($ChangedPaths).Count -eq 0) {
        throw "Claude made no repository changes for the Company B implementation task."
    }

    foreach ($changedPath in $ChangedPaths) {
        if ($ForbiddenPaths | Where-Object { Test-PathRuleMatch -Path $changedPath -Rule $_ }) {
            throw "Company B blocked a forbidden path change: $changedPath"
        }
        if (-not ($AllowedPaths | Where-Object { Test-PathRuleMatch -Path $changedPath -Rule $_ })) {
            throw "Company B blocked a change outside the allow-list: $changedPath"
        }
    }
}

function Get-CompanyBRuntimeRoot {
    if (-not [string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) {
        return (Join-Path $env:LOCALAPPDATA "AICompany\company-b\my-quant-bot")
    }
    return (Join-Path ([System.IO.Path]::GetTempPath()) "AICompany\company-b\my-quant-bot")
}

function Save-CompanyBState {
    param(
        [Parameter(Mandatory)][string]$StatePath,
        [Parameter(Mandatory)][string]$TaskId,
        [Parameter(Mandatory)][string]$Status,
        [Parameter(Mandatory)][string]$Phase,
        [Parameter(Mandatory)][string]$BaseSha,
        [Parameter(Mandatory)][string]$Branch,
        [string]$ReviewVerdict,
        [string]$FailureCode
    )

    $state = [ordered]@{
        schemaVersion = 1
        company = "B"
        leadership = "CLAUDE_LED"
        taskId = $TaskId
        status = $Status
        phase = $Phase
        baseSha = $BaseSha
        branch = $Branch
        reviewVerdict = $ReviewVerdict
        failureCode = $FailureCode
        updatedAtUtc = [DateTime]::UtcNow.ToString("o")
    }

    Set-Content -LiteralPath $StatePath -Value ($state | ConvertTo-Json -Depth 4) -Encoding utf8
}

function Get-CodexVerdict {
    param([AllowNull()][string]$Output)

    if ([string]::IsNullOrWhiteSpace($Output)) {
        return "UNAVAILABLE"
    }

    $matches = [regex]::Matches($Output, '(?im)^\s*VERDICT\s*:\s*(PASS|CHANGES_REQUESTED)\s*$')
    if ($matches.Count -ne 1) {
        return "UNAVAILABLE"
    }
    return $matches[0].Groups[1].Value.ToUpperInvariant()
}

function Invoke-ClaudeReadOnly {
    param(
        [Parameter(Mandatory)][string]$ClaudePath,
        [Parameter(Mandatory)][string]$Model,
        [Parameter(Mandatory)][string]$WorktreePath,
        [Parameter(Mandatory)][string]$PromptPath,
        [Parameter(Mandatory)][string]$OutputPath
    )

    Push-Location -LiteralPath $WorktreePath
    try {
        Get-Content -LiteralPath $PromptPath -Raw |
            & $ClaudePath -p --model $Model --permission-mode plan --max-turns 1 --output-format text --disallowedTools "Edit" "Write" "Bash" 1> $OutputPath 2> $null
        if ($LASTEXITCODE -ne 0) {
            throw "Claude Code could not complete the Company B read-only planning turn."
        }
    }
    finally {
        Pop-Location
    }
}

function Invoke-ClaudeWrite {
    param(
        [Parameter(Mandatory)][string]$ClaudePath,
        [Parameter(Mandatory)][string]$Model,
        [Parameter(Mandatory)][string]$WorktreePath,
        [Parameter(Mandatory)][string]$PromptPath,
        [Parameter(Mandatory)][string]$OutputPath
    )

    Push-Location -LiteralPath $WorktreePath
    try {
        Get-Content -LiteralPath $PromptPath -Raw |
            & $ClaudePath -p --model $Model --permission-mode acceptEdits --max-turns 30 --output-format text --disallowedTools "Bash" 1> $OutputPath 2> $null
        if ($LASTEXITCODE -ne 0) {
            throw "Claude Code could not complete the Company B bounded implementation turn."
        }
    }
    finally {
        Pop-Location
    }
}

function Invoke-CodexReadOnly {
    param(
        [Parameter(Mandatory)][string]$CodexPath,
        [Parameter(Mandatory)][string]$Model,
        [Parameter(Mandatory)][string]$WorktreePath,
        [Parameter(Mandatory)][string]$PromptPath,
        [Parameter(Mandatory)][string]$OutputPath
    )

    Remove-Item -LiteralPath $OutputPath -Force -ErrorAction SilentlyContinue
    Get-Content -LiteralPath $PromptPath -Raw |
        & $CodexPath exec --model $Model --cd $WorktreePath --sandbox read-only --output-last-message $OutputPath - 1> $null 2> $null
    if ($LASTEXITCODE -ne 0) {
        throw "Codex could not complete the Company B read-only challenger/reviewer turn."
    }
}

function Invoke-FixedTestProfile {
    param(
        [Parameter(Mandatory)][string]$Profile,
        [Parameter(Mandatory)][string]$WorktreePath,
        [Parameter(Mandatory)][string]$ResultPath
    )

    if ($Profile -notin $SupportedTestProfiles) {
        throw "Unsupported Company B fixed test profile."
    }

    if ($Profile -eq "company-b-bootstrap") {
        $probePath = Join-Path $WorktreePath "docs\company-b\BOOTSTRAP_PROBE.md"
        if (-not (Test-Path -LiteralPath $probePath -PathType Leaf)) {
            Set-Content -LiteralPath $ResultPath -Value "test_profile: company-b-bootstrap`nresult: FAILED (missing probe)" -Encoding utf8
            return $false
        }
        $content = Get-Content -LiteralPath $probePath -Raw
        $required = @(
            "COMPANY: B",
            "DIRECTOR: Claude Code",
            "REVIEWER: Codex / GPT",
            "STATUS: bootstrap-probe"
        )
        foreach ($marker in $required) {
            if (-not $content.Contains($marker)) {
                Set-Content -LiteralPath $ResultPath -Value "test_profile: company-b-bootstrap`nresult: FAILED (invalid probe)" -Encoding utf8
                return $false
            }
        }
        Set-Content -LiteralPath $ResultPath -Value "test_profile: company-b-bootstrap`nresult: PASSED" -Encoding utf8
        return $true
    }

    Push-Location -LiteralPath $WorktreePath
    try {
        & python -m pytest -q 1> $null 2> $null
        if ($LASTEXITCODE -ne 0) {
            Set-Content -LiteralPath $ResultPath -Value "test_profile: pytest`nresult: FAILED" -Encoding utf8
            return $false
        }
        Set-Content -LiteralPath $ResultPath -Value "test_profile: pytest`nresult: PASSED" -Encoding utf8
        return $true
    }
    finally {
        Pop-Location
    }
}

function Invoke-SelfTest {
    if ((Get-CodexVerdict -Output "VERDICT: PASS") -ne "PASS") {
        throw "Company B PASS verdict parser self-test failed."
    }
    if ((Get-CodexVerdict -Output "Finding`nVERDICT: CHANGES_REQUESTED") -ne "CHANGES_REQUESTED") {
        throw "Company B CHANGES_REQUESTED parser self-test failed."
    }
    if ((Get-CodexVerdict -Output "VERDICT: PASS`nVERDICT: CHANGES_REQUESTED") -ne "UNAVAILABLE") {
        throw "Company B ambiguous verdict must fail closed."
    }
    if (-not (Test-PathRuleMatch -Path "docs/company-b/BOOTSTRAP_PROBE.md" -Rule "docs/company-b/")) {
        throw "Company B path rule self-test failed."
    }
    if (Test-PathRuleMatch -Path "docs/company-b/BOOTSTRAP_PROBE.md" -Rule "docs/company-a/") {
        throw "Company B path isolation self-test failed."
    }
    Write-Output "Company B worker self-test passed."
}

if ($SelfTest) {
    Invoke-SelfTest
    exit 0
}

$repositoryRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$resolvedTaskSpec = if ([System.IO.Path]::IsPathRooted($TaskSpec)) { $TaskSpec } else { Join-Path $repositoryRoot $TaskSpec }
if (-not (Test-Path -LiteralPath $resolvedTaskSpec -PathType Leaf)) {
    throw "Company B task spec was not found."
}

try {
    $task = Get-Content -LiteralPath $resolvedTaskSpec -Raw | ConvertFrom-Json
}
catch {
    throw "Company B task spec is not valid JSON."
}

$taskId = [string]$task.id
if ($taskId -notmatch '^B-TASK-[0-9]{3,}$') {
    throw "Company B task id must match B-TASK-NNN."
}
if ([string]::IsNullOrWhiteSpace([string]$task.title) -or [string]::IsNullOrWhiteSpace([string]$task.objective)) {
    throw "Company B task requires title and objective."
}
if ([string]$task.risk -notin $SupportedRiskTiers) {
    throw "Company B task risk tier is unsupported."
}
if ([string]$task.test_profile -notin $SupportedTestProfiles) {
    throw "Company B task test profile is unsupported."
}

$allowedPaths = ConvertTo-ValidatedPathArray -Values $task.allowed_paths -FieldName "allowed_paths"
$taskForbidden = ConvertTo-ValidatedPathArray -Values $task.forbidden_paths -FieldName "forbidden_paths"
$forbiddenPaths = @($BuiltInForbiddenPaths + $taskForbidden | Select-Object -Unique)

foreach ($allowedPath in $allowedPaths) {
    if ($forbiddenPaths | Where-Object { (Test-PathRuleMatch -Path $allowedPath -Rule $_) -or (Test-PathRuleMatch -Path $_ -Rule $allowedPath) }) {
        throw "Company B task has overlapping allowed/forbidden path scope."
    }
}

$claudePath = Resolve-RequiredCommand -Names @("claude.cmd", "claude.exe", "claude") -DisplayName "Claude Code"
$codexPath = Resolve-RequiredCommand -Names @("codex.exe", "codex.cmd", "codex") -DisplayName "Codex"

$claudeModel = if ([string]::IsNullOrWhiteSpace([string]$task.claude_model)) { "claude-sonnet-5" } else { [string]$task.claude_model }
$codexModel = if ([string]::IsNullOrWhiteSpace([string]$task.codex_model)) { "gpt-5.6-sol" } else { [string]$task.codex_model }

$baseSha = (& git -C $repositoryRoot rev-parse $BaseRef).Trim()
if ($LASTEXITCODE -ne 0 -or $baseSha -notmatch '^[0-9a-f]{40}$') {
    throw "Company B could not resolve the requested base ref."
}

$runtimeRoot = Get-CompanyBRuntimeRoot
$taskRuntime = Join-Path $runtimeRoot $taskId
if (Test-Path -LiteralPath $taskRuntime) {
    throw "Company B runtime already exists for this task id. Use a new task id or clean the isolated Company B runtime deliberately."
}
New-Item -ItemType Directory -Path $taskRuntime -Force | Out-Null

if ([string]::IsNullOrWhiteSpace($WorktreeRoot)) {
    $WorktreeRoot = Join-Path $runtimeRoot "worktrees"
}
New-Item -ItemType Directory -Path $WorktreeRoot -Force | Out-Null

$branchName = "company-b/task-" + $taskId.ToLowerInvariant()
$worktreePath = Join-Path $WorktreeRoot $taskId.ToLowerInvariant()
$statePath = Join-Path $taskRuntime "state.json"
$planPromptPath = Join-Path $taskRuntime "plan-prompt.txt"
$planPath = Join-Path $taskRuntime "claude-plan.txt"
$challengePromptPath = Join-Path $taskRuntime "challenge-prompt.txt"
$challengePath = Join-Path $taskRuntime "codex-challenge.txt"
$implementationPromptPath = Join-Path $taskRuntime "implementation-prompt.txt"
$implementationOutputPath = Join-Path $taskRuntime "claude-implementation.txt"
$testResultPath = Join-Path $taskRuntime "test-result.txt"
$reviewPromptPath = Join-Path $taskRuntime "review-prompt.txt"
$reviewPath = Join-Path $taskRuntime "codex-review.txt"
$correctionPromptPath = Join-Path $taskRuntime "correction-prompt.txt"
$correctionOutputPath = Join-Path $taskRuntime "claude-correction.txt"

$worktreeCreated = $false
$success = $false

try {
    & git -C $repositoryRoot show-ref --verify --quiet "refs/heads/$branchName"
    if ($LASTEXITCODE -eq 0) {
        throw "Company B task branch already exists."
    }
    if (Test-Path -LiteralPath $worktreePath) {
        throw "Company B worktree path already exists."
    }

    & git -C $repositoryRoot branch $branchName $baseSha
    if ($LASTEXITCODE -ne 0) {
        throw "Company B could not create its isolated task branch."
    }
    & git -C $repositoryRoot worktree add $worktreePath $branchName 1> $null
    if ($LASTEXITCODE -ne 0) {
        throw "Company B could not create its isolated task worktree."
    }
    $worktreeCreated = $true

    Save-CompanyBState -StatePath $statePath -TaskId $taskId -Status "RUNNING" -Phase "CLAUDE_PLAN" -BaseSha $baseSha -Branch $branchName

    $acceptanceText = (@($task.acceptance_criteria) | ForEach-Object { "- " + [string]$_ }) -join "`n"
    $allowedText = ($allowedPaths | ForEach-Object { "- $_" }) -join "`n"
    $forbiddenText = ($forbiddenPaths | ForEach-Object { "- $_" }) -join "`n"

    $planPrompt = @"
You are the PRIMARY TECHNICAL DIRECTOR for Company B, an independent Claude-led software company.
This is a read-only planning turn. Do not edit files or run shell commands.

TASK ID: $taskId
TITLE: $($task.title)
OBJECTIVE:
$($task.objective)

ACCEPTANCE CRITERIA:
$acceptanceText

ALLOWED PATHS:
$allowedText

FORBIDDEN PATHS:
$forbiddenText

FIXED TEST PROFILE: $($task.test_profile)
BASE SHA: $baseSha

Produce a concise, repository-grounded implementation plan. Include assumptions, intended files, risks, validation, and stop conditions. Do not claim work was implemented.
"@
    Set-Content -LiteralPath $planPromptPath -Value $planPrompt -Encoding utf8
    Invoke-ClaudeReadOnly -ClaudePath $claudePath -Model $claudeModel -WorktreePath $worktreePath -PromptPath $planPromptPath -OutputPath $planPath

    Save-CompanyBState -StatePath $statePath -TaskId $taskId -Status "RUNNING" -Phase "CODEX_CHALLENGE" -BaseSha $baseSha -Branch $branchName
    $planText = Get-Content -LiteralPath $planPath -Raw
    $challengePrompt = @"
You are the INDEPENDENT CHALLENGER for Company B. Company B is Claude-led; you are Codex/GPT and must remain read-only.
Do not edit files. Challenge the proposed plan for correctness, missing assumptions, unnecessary scope, safety, and test adequacy.
Do not redesign for style alone. Identify concrete blocking issues first, then optional improvements.

TASK OBJECTIVE:
$($task.objective)

CLAUDE PLAN:
$planText
"@
    Set-Content -LiteralPath $challengePromptPath -Value $challengePrompt -Encoding utf8
    Invoke-CodexReadOnly -CodexPath $codexPath -Model $codexModel -WorktreePath $worktreePath -PromptPath $challengePromptPath -OutputPath $challengePath

    Save-CompanyBState -StatePath $statePath -TaskId $taskId -Status "RUNNING" -Phase "CLAUDE_IMPLEMENTATION" -BaseSha $baseSha -Branch $branchName
    $challengeText = Get-Content -LiteralPath $challengePath -Raw
    $implementationPrompt = @"
You are the PRIMARY IMPLEMENTER for Company B. Company B is Claude-led.
Implement the bounded task in the current isolated worktree.

You must first reconcile your plan with the independent Codex challenge. You may reject a challenge only when repository evidence justifies doing so.
Do not run Bash or external commands. Do not perform Git operations. Do not access secrets, trading, deployment, notification, or external side-effect systems.
Edit ONLY the allowed repository paths. The host will independently enforce the path boundary and run fixed tests afterward.

TASK ID: $taskId
OBJECTIVE:
$($task.objective)

ACCEPTANCE CRITERIA:
$acceptanceText

ALLOWED PATHS:
$allowedText

FORBIDDEN PATHS:
$forbiddenText

YOUR ORIGINAL PLAN:
$planText

CODEX CHALLENGE:
$challengeText

Implement now. Keep the change minimal and directly tied to the acceptance criteria.
"@
    Set-Content -LiteralPath $implementationPromptPath -Value $implementationPrompt -Encoding utf8
    Invoke-ClaudeWrite -ClaudePath $claudePath -Model $claudeModel -WorktreePath $worktreePath -PromptPath $implementationPromptPath -OutputPath $implementationOutputPath

    $changedPaths = Get-ChangedPaths -WorktreePath $worktreePath
    Assert-ChangedPathsAllowed -ChangedPaths $changedPaths -AllowedPaths $allowedPaths -ForbiddenPaths $forbiddenPaths

    Save-CompanyBState -StatePath $statePath -TaskId $taskId -Status "RUNNING" -Phase "FIXED_TESTS" -BaseSha $baseSha -Branch $branchName
    if (-not (Invoke-FixedTestProfile -Profile ([string]$task.test_profile) -WorktreePath $worktreePath -ResultPath $testResultPath)) {
        throw "Company B fixed tests failed."
    }

    Save-CompanyBState -StatePath $statePath -TaskId $taskId -Status "RUNNING" -Phase "CODEX_REVIEW" -BaseSha $baseSha -Branch $branchName
    $diff = (& git -C $worktreePath diff --no-ext-diff --unified=60 $baseSha) -join "`n"
    $testSummary = Get-Content -LiteralPath $testResultPath -Raw
    $reviewPrompt = @"
You are the INDEPENDENT FINAL CODE REVIEWER for Company B. Company B is Claude-led; you are Codex/GPT and must remain read-only.
Review only the supplied diff and fixed test result. Focus on correctness, regressions, scope discipline, safety boundaries, and whether tests support the change.

Your response MUST contain exactly one verdict line by itself:
VERDICT: PASS
or
VERDICT: CHANGES_REQUESTED

Use CHANGES_REQUESTED only for a concrete blocking defect. Keep findings concise.

TEST RESULT:
$testSummary

DIFF:
$diff
"@
    Set-Content -LiteralPath $reviewPromptPath -Value $reviewPrompt -Encoding utf8
    Invoke-CodexReadOnly -CodexPath $codexPath -Model $codexModel -WorktreePath $worktreePath -PromptPath $reviewPromptPath -OutputPath $reviewPath
    $reviewText = Get-Content -LiteralPath $reviewPath -Raw
    $verdict = Get-CodexVerdict -Output $reviewText
    if ($verdict -eq "UNAVAILABLE") {
        throw "Company B Codex review did not produce one valid bounded verdict."
    }

    if ($verdict -eq "CHANGES_REQUESTED") {
        Save-CompanyBState -StatePath $statePath -TaskId $taskId -Status "RUNNING" -Phase "CLAUDE_CORRECTION" -BaseSha $baseSha -Branch $branchName -ReviewVerdict $verdict
        $correctionPrompt = @"
You are the PRIMARY IMPLEMENTER for Company B. Apply at most one minimal correction round for the blocking findings below.
Do not run Bash or Git commands. Edit only the original allowed paths. Do not broaden scope.

ORIGINAL OBJECTIVE:
$($task.objective)

ALLOWED PATHS:
$allowedText

BLOCKING CODE REVIEW:
$reviewText

Correct only justified blocking defects now.
"@
        Set-Content -LiteralPath $correctionPromptPath -Value $correctionPrompt -Encoding utf8
        Invoke-ClaudeWrite -ClaudePath $claudePath -Model $claudeModel -WorktreePath $worktreePath -PromptPath $correctionPromptPath -OutputPath $correctionOutputPath

        $changedPaths = Get-ChangedPaths -WorktreePath $worktreePath
        Assert-ChangedPathsAllowed -ChangedPaths $changedPaths -AllowedPaths $allowedPaths -ForbiddenPaths $forbiddenPaths
        if (-not (Invoke-FixedTestProfile -Profile ([string]$task.test_profile) -WorktreePath $worktreePath -ResultPath $testResultPath)) {
            throw "Company B fixed tests failed after the bounded correction round."
        }

        $diff = (& git -C $worktreePath diff --no-ext-diff --unified=60 $baseSha) -join "`n"
        $testSummary = Get-Content -LiteralPath $testResultPath -Raw
        $finalReviewPrompt = @"
You are the INDEPENDENT FINAL CODE REVIEWER for Company B. This is the final review after the one allowed Claude correction round. Remain read-only.

Your response MUST contain exactly one verdict line by itself:
VERDICT: PASS
or
VERDICT: CHANGES_REQUESTED

If a blocking defect remains, return CHANGES_REQUESTED. No further automatic model-to-model correction is allowed.

TEST RESULT:
$testSummary

DIFF:
$diff
"@
        Set-Content -LiteralPath $reviewPromptPath -Value $finalReviewPrompt -Encoding utf8
        Invoke-CodexReadOnly -CodexPath $codexPath -Model $codexModel -WorktreePath $worktreePath -PromptPath $reviewPromptPath -OutputPath $reviewPath
        $reviewText = Get-Content -LiteralPath $reviewPath -Raw
        $verdict = Get-CodexVerdict -Output $reviewText
        if ($verdict -ne "PASS") {
            Save-CompanyBState -StatePath $statePath -TaskId $taskId -Status "BLOCKED" -Phase "FINAL_REVIEW" -BaseSha $baseSha -Branch $branchName -ReviewVerdict $verdict -FailureCode "FINAL_REVIEW_BLOCKED"
            throw "Company B final Codex review did not PASS. Automatic correction is intentionally stopped."
        }
    }

    Save-CompanyBState -StatePath $statePath -TaskId $taskId -Status "RUNNING" -Phase "LOCAL_COMMIT" -BaseSha $baseSha -Branch $branchName -ReviewVerdict "PASS"
    $changedPaths = Get-ChangedPaths -WorktreePath $worktreePath
    Assert-ChangedPathsAllowed -ChangedPaths $changedPaths -AllowedPaths $allowedPaths -ForbiddenPaths $forbiddenPaths
    & git -C $worktreePath add -- @changedPaths
    if ($LASTEXITCODE -ne 0) {
        throw "Company B could not stage its bounded changes."
    }
    & git -C $worktreePath commit -m "company-b: complete $taskId" 1> $null
    if ($LASTEXITCODE -ne 0) {
        throw "Company B could not create its local task commit."
    }

    if ($PushOnPass) {
        & git -C $worktreePath push -u origin $branchName 1> $null
        if ($LASTEXITCODE -ne 0) {
            throw "Company B passed locally but could not push its isolated task branch."
        }
    }

    Save-CompanyBState -StatePath $statePath -TaskId $taskId -Status "PASS" -Phase "DONE" -BaseSha $baseSha -Branch $branchName -ReviewVerdict "PASS"
    $success = $true

    Write-Output "Company B task PASS: $taskId"
    Write-Output "Leadership: Claude Code -> Codex/GPT review"
    Write-Output "Branch: $branchName"
    Write-Output "Base SHA: $baseSha"
    Write-Output "Fixed tests: PASSED"
    Write-Output "Independent Codex review: PASS"
    if ($PushOnPass) {
        Write-Output "Remote branch: pushed"
    }
    else {
        Write-Output "Remote branch: not pushed (bootstrap default)"
    }
}
catch {
    $failureCode = "COMPANY_B_TASK_FAILED"
    try {
        if (Test-Path -LiteralPath $statePath) {
            Save-CompanyBState -StatePath $statePath -TaskId $taskId -Status "BLOCKED" -Phase "FAILED" -BaseSha $baseSha -Branch $branchName -FailureCode $failureCode
        }
    }
    catch { }
    throw
}
finally {
    if ($worktreeCreated -and $success -and -not $KeepWorktree) {
        & git -C $repositoryRoot worktree remove $worktreePath --force 1> $null 2> $null
    }
}
