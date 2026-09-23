[CmdletBinding()]
param(
    [string]$Repository = "rentgist/my-quant-bot",
    [string]$QueueLabel = "company-b:queued",
    [string]$RunningLabel = "company-b:running",
    [string]$BlockedLabel = "company-b:blocked",
    [string]$DoneLabel = "company-b:done",
    [string]$ApprovalRequiredLabel = "company-b:approval-required",
    [string]$BaseRef = "company-b/bootstrap-claude-led-v0.1",
    [switch]$SelfTest
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# This wrapper only discovers, sequences, and publishes evidence for Company B tasks. All
# Claude/Codex planning, implementation, and review logic lives in company-b-worker.ps1 and is
# never duplicated here.

$SupportedRiskTiers = @("low", "medium", "high")
$SupportedTestProfiles = @("company-b-bootstrap", "pytest")
$CompanyBQueueMutexName = "Global\rentgist-my-quant-bot-company-b-queue"

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

function Get-CompanyBRuntimeRoot {
    if (-not [string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) {
        return (Join-Path $env:LOCALAPPDATA "AICompany\company-b\my-quant-bot")
    }
    return (Join-Path ([System.IO.Path]::GetTempPath()) "AICompany\company-b\my-quant-bot")
}

function Get-CompanyBWorkerStatePath {
    param([Parameter(Mandatory)][string]$TaskId)
    return (Join-Path (Join-Path (Get-CompanyBRuntimeRoot) $TaskId) "state.json")
}

function Get-CompanyBQueueIssueDirectory {
    param([Parameter(Mandatory)][int]$IssueNumber)
    return (Join-Path (Join-Path (Get-CompanyBRuntimeRoot) "queue") ("issue-{0}" -f $IssueNumber))
}

function Get-CompanyBTaskSpecJsonText {
    param([Parameter(Mandatory)][string]$Body)

    $startMatches = [regex]::Matches($Body, '(?m)^COMPANY_B_TASK_SPEC_START\s*$')
    $endMatches = [regex]::Matches($Body, '(?m)^COMPANY_B_TASK_SPEC_END\s*$')
    if ($startMatches.Count -ne 1 -or $endMatches.Count -ne 1) {
        throw "Issue body must contain exactly one COMPANY_B_TASK_SPEC_START marker and exactly one COMPANY_B_TASK_SPEC_END marker."
    }

    $startIndex = $startMatches[0].Index + $startMatches[0].Length
    $endIndex = $endMatches[0].Index
    if ($endIndex -le $startIndex) {
        throw "COMPANY_B_TASK_SPEC_END must appear after COMPANY_B_TASK_SPEC_START."
    }

    return $Body.Substring($startIndex, $endIndex - $startIndex).Trim()
}

function Assert-CompanyBPathList {
    param($Values, [Parameter(Mandatory)][string]$FieldName)

    $paths = @()
    foreach ($value in @($Values)) {
        if ($null -eq $value) {
            continue
        }
        $path = ([string]$value).Trim().Replace("\", "/")
        if ([string]::IsNullOrWhiteSpace($path) -or $path.StartsWith("/") -or $path.Contains("//") -or $path -notmatch '^[A-Za-z0-9._/-]+$') {
            throw "Company B task field '$FieldName' has an invalid path."
        }
        $segments = $path.TrimEnd("/").Split("/")
        if ($segments -contains "." -or $segments -contains "..") {
            throw "Company B task field '$FieldName' contains path traversal."
        }
        $paths += $path
    }
    if (@($paths).Count -eq 0) {
        throw "Company B task field '$FieldName' must contain at least one path."
    }
    return @($paths | Select-Object -Unique)
}

function Assert-CompanyBTaskEnvelope {
    # Fail-fast, non-authoritative preflight validation. company-b-worker.ps1 independently
    # re-validates the materialized spec before doing any repository work; this check only
    # avoids invoking the worker for an Issue that is already known to be malformed.
    param([Parameter(Mandatory)]$Task)

    $taskId = [string]$Task.id
    if ($taskId -notmatch '^B-TASK-[0-9]{3,}$') {
        throw "Company B task id must match B-TASK-NNN."
    }
    if ([string]::IsNullOrWhiteSpace([string]$Task.title) -or [string]::IsNullOrWhiteSpace([string]$Task.objective)) {
        throw "Company B task requires a non-empty title and objective."
    }
    if ([string]$Task.risk -notin $SupportedRiskTiers) {
        throw "Company B task risk tier is unsupported."
    }
    if ([string]$Task.test_profile -notin $SupportedTestProfiles) {
        throw "Company B task test profile is unsupported."
    }

    $allowedPaths = @(Assert-CompanyBPathList -Values $Task.allowed_paths -FieldName "allowed_paths")
    $forbiddenPaths = @(Assert-CompanyBPathList -Values $Task.forbidden_paths -FieldName "forbidden_paths")
    foreach ($allowedPath in $allowedPaths) {
        if ($forbiddenPaths -contains $allowedPath) {
            throw "Company B task has overlapping allowed/forbidden path scope."
        }
    }

    return $taskId
}

function Get-ValidatedCompanyBWorkerState {
    param(
        [Parameter(Mandatory)][string]$StatePath,
        [Parameter(Mandatory)][string]$ExpectedTaskId,
        [Parameter(Mandatory)][string]$ExpectedBranch
    )

    if (-not (Test-Path -LiteralPath $StatePath -PathType Leaf)) {
        throw "Company B worker state was not found at '$StatePath'."
    }
    try {
        $state = Get-Content -LiteralPath $StatePath -Raw | ConvertFrom-Json
    }
    catch {
        throw "Company B worker state is not valid JSON."
    }
    foreach ($field in @("taskId", "status", "phase", "baseSha", "branch")) {
        if ([string]::IsNullOrWhiteSpace([string]$state.$field)) {
            throw "Company B worker state is missing required field '$field'."
        }
    }
    if ([string]$state.taskId -ne $ExpectedTaskId) {
        throw "Company B worker state task id does not match the selected task."
    }
    if ([string]$state.branch -ne $ExpectedBranch) {
        throw "Company B worker state branch does not match the expected task branch."
    }
    if ([string]$state.baseSha -notmatch '^[0-9a-f]{40}$') {
        throw "Company B worker state base SHA is not a valid commit SHA."
    }
    return $state
}

function Test-CompanyBWorkerStateIsPublishable {
    param([Parameter(Mandatory)]$State)
    return ([string]$State.status -eq "PASS" -and [string]$State.phase -eq "DONE" -and [string]$State.reviewVerdict -eq "PASS")
}

function Assert-CompanyBTestEvidencePassed {
    param(
        [Parameter(Mandatory)][string]$TestResultPath,
        [Parameter(Mandatory)][string]$ExpectedProfile
    )

    if (-not (Test-Path -LiteralPath $TestResultPath -PathType Leaf)) {
        throw "Company B fixed-test evidence was not found."
    }
    $content = (Get-Content -LiteralPath $TestResultPath -Raw).Replace("`r`n", "`n").Trim()
    $expected = "test_profile: $ExpectedProfile`nresult: PASSED"
    if ($content -cne $expected) {
        throw "Company B fixed-test evidence does not unambiguously report a PASS for '$ExpectedProfile'."
    }
}

function Get-CompanyBSingleReviewVerdict {
    param([Parameter(Mandatory)][string]$Content)

    $matches = [regex]::Matches($Content, '(?im)^\s*VERDICT\s*:\s*(PASS|CHANGES_REQUESTED)\s*$')
    if ($matches.Count -ne 1) {
        throw "Company B durable review evidence must contain exactly one VERDICT line."
    }
    return $matches[0].Groups[1].Value.ToUpperInvariant()
}

function Assert-CompanyBReviewEvidencePassed {
    param([Parameter(Mandatory)][string]$ReviewPath)

    if (-not (Test-Path -LiteralPath $ReviewPath -PathType Leaf)) {
        throw "Company B independent Codex review evidence was not found."
    }
    $content = Get-Content -LiteralPath $ReviewPath -Raw
    $verdict = Get-CompanyBSingleReviewVerdict -Content $content
    if ($verdict -ne "PASS") {
        throw "Company B independent Codex review evidence is not a PASS verdict."
    }
    return $content
}

function Get-CompanyBTaskHeadSha {
    param(
        [Parameter(Mandatory)][string]$RepositoryRoot,
        [Parameter(Mandatory)][string]$Branch
    )

    $sha = (& git -C $RepositoryRoot rev-parse "refs/heads/$Branch").Trim()
    if ($LASTEXITCODE -ne 0 -or $sha -notmatch '^[0-9a-f]{40}$') {
        throw "Could not resolve the exact Company B task branch head."
    }
    return $sha
}

function Get-CompanyBEvidenceMarker {
    param(
        [Parameter(Mandatory)][int]$IssueNumber,
        [Parameter(Mandatory)][int]$PullRequestNumber,
        [Parameter(Mandatory)][string]$HeadSha
    )

    if ($IssueNumber -le 0 -or $PullRequestNumber -le 0 -or $HeadSha -notmatch '^[0-9a-f]{40}$') {
        throw "Cannot construct a Company B evidence marker from invalid input."
    }
    return "<!-- company-b-queue-evidence:v1 issue=$IssueNumber pr=$PullRequestNumber head=$HeadSha verdict=PASS -->"
}

function New-CompanyBEvidenceBody {
    param(
        [Parameter(Mandatory)][int]$IssueNumber,
        [Parameter(Mandatory)][int]$PullRequestNumber,
        [Parameter(Mandatory)][string]$HeadSha,
        [Parameter(Mandatory)][string]$TestProfile,
        [Parameter(Mandatory)][string]$ReviewText
    )

    $marker = Get-CompanyBEvidenceMarker -IssueNumber $IssueNumber -PullRequestNumber $PullRequestNumber -HeadSha $HeadSha
    # Only the verdict line is republished (never the raw agent transcript), so a published
    # comment can never leak local paths or other incidental agent output.
    $verdictLines = @($ReviewText -split "`r?`n" | Where-Object { $_ -match '^\s*VERDICT\s*:\s*(PASS|CHANGES_REQUESTED)\s*$' })
    $verdictLine = ($verdictLines | Select-Object -First 1).Trim()
    return @"
$marker
Company B durable reviewer evidence

- Task head SHA: ``$HeadSha``
- Fixed tests: PASSED (test_profile: $TestProfile)
- Independent Codex final review: $verdictLine
- Merge policy: this Draft PR is never auto-merged by Company B; human/PM review decides the merge.
"@
}

function Publish-CompanyBEvidence {
    param(
        [Parameter(Mandatory)][string]$GhPath,
        [Parameter(Mandatory)][string]$Repository,
        [Parameter(Mandatory)][int]$IssueNumber,
        [Parameter(Mandatory)][int]$PullRequestNumber,
        [Parameter(Mandatory)][string]$HeadSha,
        [Parameter(Mandatory)][string]$TestProfile,
        [Parameter(Mandatory)][string]$ReviewText
    )

    $marker = Get-CompanyBEvidenceMarker -IssueNumber $IssueNumber -PullRequestNumber $PullRequestNumber -HeadSha $HeadSha

    $getMarkerCount = {
        $commentsJson = & $GhPath api --paginate --slurp "repos/$Repository/issues/$PullRequestNumber/comments?per_page=100" 2> $null
        if ($LASTEXITCODE -ne 0) {
            throw "Could not inspect existing Company B durable review evidence."
        }
        try {
            $commentPages = $commentsJson | ConvertFrom-Json
        }
        catch {
            throw "Existing Company B durable review evidence could not be validated."
        }
        $bodies = @($commentPages | ForEach-Object { foreach ($comment in @($_)) { $comment.body } })
        return @($bodies | Where-Object { $null -ne $_ -and $_.Contains($marker) }).Count
    }

    $markerCount = & $getMarkerCount
    if ($markerCount -eq 0) {
        $bodyPath = (New-TemporaryFile).FullName
        try {
            Set-Content -LiteralPath $bodyPath -Value (New-CompanyBEvidenceBody -IssueNumber $IssueNumber -PullRequestNumber $PullRequestNumber -HeadSha $HeadSha -TestProfile $TestProfile -ReviewText $ReviewText) -Encoding utf8
            & $GhPath pr comment $PullRequestNumber --repo $Repository --body-file $bodyPath 1> $null 2> $null
            if ($LASTEXITCODE -ne 0) {
                throw "Could not publish Company B durable review evidence."
            }
        }
        finally {
            Remove-Item -LiteralPath $bodyPath -Force -ErrorAction SilentlyContinue
        }
        $markerCount = & $getMarkerCount
    }

    if ($markerCount -ne 1) {
        throw "Company B durable review evidence is missing or ambiguous after publication."
    }
}

function New-CompanyBBlockedStatusMessage {
    param(
        [Parameter(Mandatory)][string]$Code,
        [Parameter(Mandatory)][string]$NextAction
    )
    return "Company B queue status: BLOCKED | code=$Code | owner=human | next=$NextAction"
}

function Set-CompanyBIssueLifecycle {
    # Lifecycle label/comment transitions are completion-critical: a GitHub failure here must
    # stop the run rather than silently letting local state diverge from the visible Issue.
    param(
        [Parameter(Mandatory)][string]$GhPath,
        [Parameter(Mandatory)][string]$Repository,
        [Parameter(Mandatory)][int]$IssueNumber,
        [Parameter(Mandatory)][string]$FromLabel,
        [Parameter(Mandatory)][string]$ToLabel,
        [Parameter(Mandatory)][string]$StatusMessage
    )

    & $GhPath issue edit $IssueNumber --repo $Repository --remove-label $FromLabel --add-label $ToLabel 1> $null 2> $null
    if ($LASTEXITCODE -ne 0) {
        throw "Could not transition Issue #$IssueNumber from '$FromLabel' to '$ToLabel'."
    }
    & $GhPath issue comment $IssueNumber --repo $Repository --body $StatusMessage 1> $null 2> $null
    if ($LASTEXITCODE -ne 0) {
        throw "Could not publish the Company B lifecycle status comment for Issue #$IssueNumber."
    }
}

function Add-CompanyBApprovalLabel {
    # Supplementary visibility only; the Draft PR / no-auto-merge gate does not depend on it.
    param(
        [Parameter(Mandatory)][string]$GhPath,
        [Parameter(Mandatory)][string]$Repository,
        [Parameter(Mandatory)][int]$IssueNumber,
        [Parameter(Mandatory)][string]$Label
    )

    & $GhPath issue edit $IssueNumber --repo $Repository --add-label $Label 1> $null 2> $null
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Company B approval-required visibility label could not be applied; this is supplementary and does not weaken the Draft PR gate."
    }
}

function Invoke-CompanyBQueueSelfTest {
    $bodyOk = "intro`nCOMPANY_B_TASK_SPEC_START`n{`"id`":`"B-TASK-999`"}`nCOMPANY_B_TASK_SPEC_END`ntrailer"
    if ((Get-CompanyBTaskSpecJsonText -Body $bodyOk) -ne '{"id":"B-TASK-999"}') {
        throw "Company B marker extraction self-test failed."
    }
    foreach ($badBody in @(
        "no markers here",
        "COMPANY_B_TASK_SPEC_START`n{}`nCOMPANY_B_TASK_SPEC_START`n{}`nCOMPANY_B_TASK_SPEC_END",
        "COMPANY_B_TASK_SPEC_END`n{}`nCOMPANY_B_TASK_SPEC_START"
    )) {
        $rejected = $false
        try { Get-CompanyBTaskSpecJsonText -Body $badBody | Out-Null } catch { $rejected = $true }
        if (-not $rejected) { throw "Company B marker cardinality/order self-test failed." }
    }

    $validTask = [pscustomobject]@{
        id = "B-TASK-999"; title = "t"; objective = "o"; risk = "low"; test_profile = "pytest"
        allowed_paths = @("docs/company-b/x.md"); forbidden_paths = @("scripts/codex-queue-worker.ps1")
    }
    if ((Assert-CompanyBTaskEnvelope -Task $validTask) -ne "B-TASK-999") {
        throw "Company B envelope validation self-test failed."
    }
    $overlapTask = [pscustomobject]@{
        id = "B-TASK-999"; title = "t"; objective = "o"; risk = "low"; test_profile = "pytest"
        allowed_paths = @("docs/company-b/x.md"); forbidden_paths = @("docs/company-b/x.md")
    }
    $rejected = $false
    try { Assert-CompanyBTaskEnvelope -Task $overlapTask | Out-Null } catch { $rejected = $true }
    if (-not $rejected) { throw "Company B overlapping allowed/forbidden path self-test failed." }

    $tempTestResult = (New-TemporaryFile).FullName
    try {
        Set-Content -LiteralPath $tempTestResult -Value "test_profile: pytest`nresult: PASSED" -Encoding utf8
        Assert-CompanyBTestEvidencePassed -TestResultPath $tempTestResult -ExpectedProfile "pytest"
        Set-Content -LiteralPath $tempTestResult -Value "test_profile: pytest`nresult: FAILED (test suite)" -Encoding utf8
        $rejected = $false
        try { Assert-CompanyBTestEvidencePassed -TestResultPath $tempTestResult -ExpectedProfile "pytest" } catch { $rejected = $true }
        if (-not $rejected) { throw "Company B test-evidence self-test failed." }
    }
    finally {
        Remove-Item -LiteralPath $tempTestResult -Force -ErrorAction SilentlyContinue
    }

    if ((Get-CompanyBSingleReviewVerdict -Content "notes`nVERDICT: PASS") -ne "PASS") {
        throw "Company B review-verdict parsing self-test failed."
    }
    $rejected = $false
    try { Get-CompanyBSingleReviewVerdict -Content "VERDICT: PASS`nVERDICT: CHANGES_REQUESTED" | Out-Null } catch { $rejected = $true }
    if (-not $rejected) { throw "Company B ambiguous review-verdict self-test failed." }

    $headA = "0123456789abcdef0123456789abcdef01234567"
    $headB = "fedcba9876543210fedcba9876543210fedcba98"
    $markerA = Get-CompanyBEvidenceMarker -IssueNumber 1 -PullRequestNumber 2 -HeadSha $headA
    $markerA2 = Get-CompanyBEvidenceMarker -IssueNumber 1 -PullRequestNumber 2 -HeadSha $headA
    $markerB = Get-CompanyBEvidenceMarker -IssueNumber 1 -PullRequestNumber 2 -HeadSha $headB
    if ($markerA -cne $markerA2 -or $markerA -ceq $markerB) {
        throw "Company B evidence-marker idempotency self-test failed."
    }

    if ($CompanyBQueueMutexName -notlike "Global\rentgist-my-quant-bot-company-b-*") {
        throw "Company B mutex name must use the dedicated Company B mutex namespace."
    }

    Write-Output "Company B queue worker self-test passed."
}

if ($SelfTest) {
    Invoke-CompanyBQueueSelfTest
    exit 0
}

$mutex = [System.Threading.Mutex]::new($false, $CompanyBQueueMutexName)
$hasMutex = $false
$issueNumber = $null
$ghPath = $null

try {
    $hasMutex = $mutex.WaitOne(0)
    if (-not $hasMutex) {
        throw "Another Company B queue worker is already running; this invocation will not process a second Issue."
    }

    $repositoryRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
    $ghPath = Resolve-RequiredCommand -Names @("gh.exe", "gh") -DisplayName "GitHub CLI"

    & git -C $repositoryRoot fetch origin $BaseRef 1> $null 2> $null
    if ($LASTEXITCODE -ne 0) {
        throw "Could not fetch the Company B base ref '$BaseRef' from origin."
    }
    $remoteBaseRef = "origin/$BaseRef"
    & git -C $repositoryRoot rev-parse --verify --quiet $remoteBaseRef 1> $null 2> $null
    if ($LASTEXITCODE -ne 0) {
        throw "Could not resolve the freshly fetched Company B remote base ref '$remoteBaseRef'."
    }

    $runningJson = & $ghPath issue list --repo $Repository --label $RunningLabel --state open --json number --limit 500
    if ($LASTEXITCODE -ne 0) {
        throw "Could not query Company B running Issues."
    }
    $runningIssues = @(($runningJson | ConvertFrom-Json) | Sort-Object number)

    $recoveryIssueNumber = $null
    foreach ($candidate in $runningIssues) {
        $candidateNumber = [int]$candidate.number
        $candidateStatePath = Join-Path (Get-CompanyBQueueIssueDirectory -IssueNumber $candidateNumber) "queue-state.json"
        if (Test-Path -LiteralPath $candidateStatePath -PathType Leaf) {
            $recoveryIssueNumber = $candidateNumber
            break
        }
    }

    if ($null -ne $recoveryIssueNumber) {
        $issueNumber = $recoveryIssueNumber
        Write-Output "Recovering interrupted Company B lifecycle for Issue #$issueNumber."
    }
    elseif ($runningIssues.Count -gt 0) {
        $orphanIssueNumber = [int]$runningIssues[0].number
        Set-CompanyBIssueLifecycle -GhPath $ghPath -Repository $Repository -IssueNumber $orphanIssueNumber -FromLabel $RunningLabel -ToLabel $BlockedLabel -StatusMessage (New-CompanyBBlockedStatusMessage -Code "ORPHANED_RUNNING" -NextAction "no local Company B queue state was found for this running Issue; review manually before relabeling company-b:queued.")
        throw "Issue #$orphanIssueNumber was labeled '$RunningLabel' without local Company B queue state and was blocked safely."
    }
    else {
        $queuedJson = & $ghPath issue list --repo $Repository --label $QueueLabel --state open --json number --limit 500
        if ($LASTEXITCODE -ne 0) {
            throw "Could not query the Company B queued Issue list."
        }
        $queuedIssues = @(($queuedJson | ConvertFrom-Json) | Sort-Object number)
        if ($queuedIssues.Count -eq 0) {
            Write-Output "No Company B queued Issue found."
            exit 0
        }
        $issueNumber = [int]$queuedIssues[0].number
    }

    $issueJson = & $ghPath issue view $issueNumber --repo $Repository --json number,title,body,labels
    if ($LASTEXITCODE -ne 0) {
        throw "Could not read the selected Company B Issue."
    }
    $issue = $issueJson | ConvertFrom-Json
    $issueLabels = @($issue.labels | ForEach-Object { $_.name })
    if (-not ($issueLabels -contains $QueueLabel) -and -not ($issueLabels -contains $RunningLabel)) {
        throw "Selected Company B Issue no longer carries a recognized Company B lifecycle label."
    }

    $issueDirectory = Get-CompanyBQueueIssueDirectory -IssueNumber $issueNumber
    New-Item -ItemType Directory -Path $issueDirectory -Force | Out-Null
    $specPath = Join-Path $issueDirectory "task-spec.json"
    $queueStatePath = Join-Path $issueDirectory "queue-state.json"

    $resuming = $issueLabels -contains $RunningLabel
    if (-not $resuming) {
        $specJsonText = Get-CompanyBTaskSpecJsonText -Body $issue.body
        try {
            $task = $specJsonText | ConvertFrom-Json
        }
        catch {
            Set-CompanyBIssueLifecycle -GhPath $ghPath -Repository $Repository -IssueNumber $issueNumber -FromLabel $QueueLabel -ToLabel $BlockedLabel -StatusMessage (New-CompanyBBlockedStatusMessage -Code "TASK_SPEC_INVALID_JSON" -NextAction "correct the JSON between the COMPANY_B_TASK_SPEC markers and re-add company-b:queued.")
            throw "Company B task spec for Issue #$issueNumber is not valid JSON."
        }
        try {
            $taskId = Assert-CompanyBTaskEnvelope -Task $task
        }
        catch {
            Set-CompanyBIssueLifecycle -GhPath $ghPath -Repository $Repository -IssueNumber $issueNumber -FromLabel $QueueLabel -ToLabel $BlockedLabel -StatusMessage (New-CompanyBBlockedStatusMessage -Code "TASK_SPEC_SCHEMA_INVALID" -NextAction "correct the Company B task spec fields and re-add company-b:queued.")
            throw
        }
        Set-Content -LiteralPath $specPath -Value $specJsonText -Encoding utf8

        $expectedBranch = "company-b/task-" + $taskId.ToLowerInvariant()
        $workerStatePath = Get-CompanyBWorkerStatePath -TaskId $taskId
        if (Test-Path -LiteralPath $workerStatePath -PathType Leaf) {
            Set-CompanyBIssueLifecycle -GhPath $ghPath -Repository $Repository -IssueNumber $issueNumber -FromLabel $QueueLabel -ToLabel $BlockedLabel -StatusMessage (New-CompanyBBlockedStatusMessage -Code "TASK_RUNTIME_ALREADY_EXISTS" -NextAction "a Company B worker runtime already exists for $taskId; inspect it, then either resolve manually or use a new task id.")
            throw "Company B worker runtime already exists for $taskId; the queue worker will not overwrite it."
        }

        $queueState = [ordered]@{
            schemaVersion = 1
            issueNumber = $issueNumber
            taskId = $taskId
            branch = $expectedBranch
        }
        Set-Content -LiteralPath $queueStatePath -Value ($queueState | ConvertTo-Json -Depth 3) -Encoding utf8

        Set-CompanyBIssueLifecycle -GhPath $ghPath -Repository $Repository -IssueNumber $issueNumber -FromLabel $QueueLabel -ToLabel $RunningLabel -StatusMessage "Company B queue status: running ($taskId)."
        if ([string]$task.risk -eq "high") {
            Add-CompanyBApprovalLabel -GhPath $ghPath -Repository $Repository -IssueNumber $issueNumber -Label $ApprovalRequiredLabel
        }

        $workerScript = Join-Path $repositoryRoot "scripts\company_b\company-b-worker.ps1"
        & powershell -NoProfile -ExecutionPolicy Bypass -File $workerScript -TaskSpec $specPath -BaseRef $remoteBaseRef -PushOnPass
        if ($LASTEXITCODE -ne 0) {
            Set-CompanyBIssueLifecycle -GhPath $ghPath -Repository $Repository -IssueNumber $issueNumber -FromLabel $RunningLabel -ToLabel $BlockedLabel -StatusMessage (New-CompanyBBlockedStatusMessage -Code "WORKER_FAILED" -NextAction "inspect the preserved Company B worker runtime for $taskId for diagnostics before requeueing.")
            throw "The Company B worker did not complete successfully for $taskId."
        }
    }
    else {
        if (-not (Test-Path -LiteralPath $queueStatePath -PathType Leaf)) {
            throw "Company B queue recovery state was not found for Issue #$issueNumber."
        }
        $queueState = Get-Content -LiteralPath $queueStatePath -Raw | ConvertFrom-Json
        $taskId = [string]$queueState.taskId
        $expectedBranch = [string]$queueState.branch
        $workerStatePath = Get-CompanyBWorkerStatePath -TaskId $taskId
    }

    $workerState = Get-ValidatedCompanyBWorkerState -StatePath $workerStatePath -ExpectedTaskId $taskId -ExpectedBranch $expectedBranch
    if (-not (Test-CompanyBWorkerStateIsPublishable -State $workerState)) {
        Set-CompanyBIssueLifecycle -GhPath $ghPath -Repository $Repository -IssueNumber $issueNumber -FromLabel $RunningLabel -ToLabel $BlockedLabel -StatusMessage (New-CompanyBBlockedStatusMessage -Code "WORKER_NOT_PASS" -NextAction "the Company B worker runtime for $taskId is not a validated PASS/DONE state; inspect it before requeueing.")
        throw "Company B worker state for $taskId is not a validated PASS/DONE result."
    }

    if (-not (Test-Path -LiteralPath $specPath -PathType Leaf)) {
        throw "Company B materialized task spec was not found for $taskId during evidence validation."
    }
    $expectedProfile = [string]((Get-Content -LiteralPath $specPath -Raw | ConvertFrom-Json).test_profile)

    $taskRuntimeDirectory = Join-Path (Get-CompanyBRuntimeRoot) $taskId
    $testResultPath = Join-Path $taskRuntimeDirectory "test-result.txt"
    $reviewPath = Join-Path $taskRuntimeDirectory "codex-review.txt"
    try {
        Assert-CompanyBTestEvidencePassed -TestResultPath $testResultPath -ExpectedProfile $expectedProfile
        $reviewText = Assert-CompanyBReviewEvidencePassed -ReviewPath $reviewPath
    }
    catch {
        Set-CompanyBIssueLifecycle -GhPath $ghPath -Repository $Repository -IssueNumber $issueNumber -FromLabel $RunningLabel -ToLabel $BlockedLabel -StatusMessage (New-CompanyBBlockedStatusMessage -Code "EVIDENCE_INVALID" -NextAction "the fixed-test or Codex review evidence for $taskId is missing or ambiguous; inspect the preserved runtime before requeueing.")
        throw
    }

    $headSha = Get-CompanyBTaskHeadSha -RepositoryRoot $repositoryRoot -Branch $expectedBranch

    try {
        $lsRemoteOutput = (& git -C $repositoryRoot ls-remote origin "refs/heads/$expectedBranch")
        if ($LASTEXITCODE -ne 0) {
            throw "Could not query the remote Company B task branch for $taskId."
        }
        $remoteHeadSha = $null
        if (-not [string]::IsNullOrWhiteSpace($lsRemoteOutput)) {
            $remoteHeadSha = ($lsRemoteOutput -split "\s+")[0]
        }
        if ($remoteHeadSha -cne $headSha) {
            & git -C $repositoryRoot push origin "${expectedBranch}:refs/heads/$expectedBranch" 1> $null 2> $null
            if ($LASTEXITCODE -ne 0) {
                throw "Could not push the Company B task branch for $taskId to origin."
            }
        }

        $prJson = & $ghPath pr list --repo $Repository --head $expectedBranch --base $BaseRef --state open --json number,isDraft,headRefOid --limit 10
        if ($LASTEXITCODE -ne 0) {
            throw "Could not query existing pull requests for $taskId."
        }
        $prMatches = @($prJson | ConvertFrom-Json)
        if ($prMatches.Count -gt 1) {
            throw "More than one open pull request targets $BaseRef from $expectedBranch; PR state is ambiguous."
        }
        if ($prMatches.Count -eq 1 -and -not [bool]$prMatches[0].isDraft) {
            throw "A non-draft pull request already exists for $expectedBranch; Company B never force-converts it."
        }
        if ($prMatches.Count -eq 0) {
            $prBodyPath = (New-TemporaryFile).FullName
            try {
                Set-Content -LiteralPath $prBodyPath -Encoding utf8 -Value @"
Company B automated queue run for Issue #$issueNumber ($taskId).

- Fixed tests: PASSED
- Independent Codex review: PASS
- Durable evidence: published as a sanitized, head-bound Draft PR comment.
- Merge policy: human/PM review required; this Draft PR is never auto-merged by Company B.
"@
                & $ghPath pr create --repo $Repository --draft --base $BaseRef --head $expectedBranch --title "[Company B] $taskId" --body-file $prBodyPath 1> $null 2> $null
                if ($LASTEXITCODE -ne 0) {
                    throw "Could not create the Company B Draft PR for $taskId."
                }
            }
            finally {
                Remove-Item -LiteralPath $prBodyPath -Force -ErrorAction SilentlyContinue
            }
        }

        $prDetailsJson = & $ghPath pr list --repo $Repository --head $expectedBranch --base $BaseRef --state open --json number,isDraft,headRefOid --limit 10
        if ($LASTEXITCODE -ne 0) {
            throw "Could not resolve the Company B Draft PR for evidence publication."
        }
        $prDetailsList = @($prDetailsJson | ConvertFrom-Json)
        if ($prDetailsList.Count -ne 1 -or -not [bool]$prDetailsList[0].isDraft) {
            throw "Company B evidence publication requires exactly one open Draft PR."
        }
        $prDetails = $prDetailsList[0]
        if ([string]$prDetails.headRefOid -cne $headSha) {
            throw "The Company B Draft PR head moved after the exact-head check; stale evidence was not published."
        }
        $pullRequestNumber = [int]$prDetails.number

        Publish-CompanyBEvidence -GhPath $ghPath -Repository $Repository -IssueNumber $issueNumber -PullRequestNumber $pullRequestNumber -HeadSha $headSha -TestProfile $expectedProfile -ReviewText $reviewText
    }
    catch {
        Set-CompanyBIssueLifecycle -GhPath $ghPath -Repository $Repository -IssueNumber $issueNumber -FromLabel $RunningLabel -ToLabel $BlockedLabel -StatusMessage (New-CompanyBBlockedStatusMessage -Code "PUBLISH_FAILED" -NextAction "PR/evidence publication for $taskId did not complete ($($_.Exception.Message)); rerun the queue worker to resume from the validated worker PASS state.")
        throw
    }

    Set-CompanyBIssueLifecycle -GhPath $ghPath -Repository $Repository -IssueNumber $issueNumber -FromLabel $RunningLabel -ToLabel $DoneLabel -StatusMessage "Company B queue status: done (Draft PR #$pullRequestNumber; human/PM review required before merge)."
    Remove-Item -LiteralPath $queueStatePath -Force -ErrorAction SilentlyContinue
    Write-Output "Company B Draft PR #$pullRequestNumber published for Issue #$issueNumber ($taskId). Head SHA: $headSha. Human/PM review required before merge."
}
catch {
    Write-Error $_.Exception.Message
    exit 1
}
finally {
    if ($hasMutex) {
        $mutex.ReleaseMutex()
    }
    $mutex.Dispose()
}
