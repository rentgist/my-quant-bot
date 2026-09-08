[CmdletBinding()]
param(
    [string]$Repository = "rentgist/my-quant-bot",
    [string]$WorktreeRoot,
    [string]$QueueLabel = "agent:queued",
    [string]$RunningLabel = "agent:running",
    [string]$BlockedLabel = "agent:blocked",
    [switch]$SelfTest
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$BuiltInForbiddenPaths = @(
    "final.py", "signals.py", "regime_playbook.py", "hedging.py",
    "fix_ai.py", "fix_fallback.py", "fix_final4.py", "fix_signals4.py"
)

function Resolve-RequiredCommand {
    param([string[]]$Names, [string]$DisplayName)

    foreach ($name in $Names) {
        $command = Get-Command $name -ErrorAction SilentlyContinue
        if ($null -ne $command) { return $command.Source }
    }

    foreach ($base in @($env:APPDATA, $env:LOCALAPPDATA)) {
        if ([string]::IsNullOrWhiteSpace($base)) { continue }
        foreach ($name in $Names) {
            $candidate = Join-Path $base "npm\$name"
            if (Test-Path -LiteralPath $candidate -PathType Leaf) { return $candidate }
        }
    }

    throw "$DisplayName command was not found."
}

function Get-IssueField {
    param([string]$Body, [string]$Label)

    $pattern = '(?ms)^###\s+' + [regex]::Escape($Label) + '\s*\r?\n(?<value>.*?)(?=^###\s+|\z)'
    $matchesForField = [regex]::Matches($Body, $pattern)
    if ($matchesForField.Count -ne 1) { throw "Issue must contain exactly one '$Label' field." }

    $value = $matchesForField[0].Groups['value'].Value.Trim()
    if ([string]::IsNullOrWhiteSpace($value)) { throw "Issue field '$Label' is empty." }
    return $value
}

function ConvertTo-ValidatedPathList {
    param([string]$Value, [string]$FieldName)

    $paths = @()
    foreach ($line in ($Value -split "`r?`n")) {
        $path = $line.Trim().Replace('\', '/')
        if ([string]::IsNullOrWhiteSpace($path)) { continue }
        if ($path -notmatch '^[A-Za-z0-9._/-]+$' -or $path.StartsWith('/') -or $path.Contains('//')) {
            throw "Issue field '$FieldName' contains an invalid repository-relative path."
        }
        $segments = $path.TrimEnd('/').Split('/')
        if ($segments -contains '.' -or $segments -contains '..') {
            throw "Issue field '$FieldName' contains path traversal."
        }
        $paths += $path
    }

    if ($paths.Count -eq 0) { throw "Issue field '$FieldName' has no valid paths." }
    return @($paths | Select-Object -Unique)
}

function Test-PathRuleMatch {
    param([string]$Path, [string]$Rule)

    $normalizedPath = $Path.Replace('\', '/')
    $normalizedRule = $Rule.Replace('\', '/')
    if ($normalizedRule.EndsWith('/')) {
        return $normalizedPath.StartsWith($normalizedRule, [System.StringComparison]::OrdinalIgnoreCase)
    }
    return $normalizedPath.Equals($normalizedRule, [System.StringComparison]::OrdinalIgnoreCase)
}

function Assert-SafeRepositoryPath {
    param([string]$Path)

    $normalized = $Path.Replace('\', '/')
    if ($normalized -notmatch '^[A-Za-z0-9._/-]+$' -or $normalized.StartsWith('/') -or $normalized.Contains('//')) {
        throw 'Edit plan contains an invalid repository-relative path.'
    }
    $segments = $normalized.Split('/')
    if ($segments -contains '.' -or $segments -contains '..') {
        throw 'Edit plan contains path traversal.'
    }
    return $normalized
}

function Assert-PathsAllowed {
    param([string[]]$Paths, [string[]]$AllowedPaths, [string[]]$ForbiddenPaths)

    foreach ($path in $Paths) {
        if ($ForbiddenPaths | Where-Object { Test-PathRuleMatch -Path $path -Rule $_ }) {
            throw "Edit plan attempted to change a forbidden path: $path"
        }
        if (-not ($AllowedPaths | Where-Object { Test-PathRuleMatch -Path $path -Rule $_ })) {
            throw "Edit plan attempted to change a path outside the allow-list: $path"
        }
    }
}

function Get-ChangedPaths {
    param([string]$Path)

    $changed = @()
    $commands = @(
        ,@('-C', $Path, 'diff', '--name-only', '--no-ext-diff'),
        ,@('-C', $Path, 'diff', '--cached', '--name-only', '--no-ext-diff'),
        ,@('-C', $Path, 'ls-files', '--others', '--exclude-standard')
    )
    foreach ($arguments in $commands) {
        $result = & git @arguments
        if ($LASTEXITCODE -ne 0) { throw 'Could not inspect changes after recovery.' }
        $changed += $result | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
    }
    return @($changed | ForEach-Object { $_.Replace('\', '/') } | Select-Object -Unique)
}

function Get-SubstringCount {
    param([string]$Text, [string]$Needle)

    if ([string]::IsNullOrEmpty($Needle)) { return 0 }
    $count = 0
    $offset = 0
    while ($true) {
        $index = $Text.IndexOf($Needle, $offset, [System.StringComparison]::Ordinal)
        if ($index -lt 0) { break }
        $count++
        $offset = $index + $Needle.Length
    }
    return $count
}

function ConvertFrom-StrictEditPlan {
    param([string]$JsonText)

    if ([string]::IsNullOrWhiteSpace($JsonText)) { throw 'Codex returned an empty edit plan.' }
    if ($JsonText -match '(?m)^\s*```') { throw 'Codex edit plan contained Markdown fences.' }

    try {
        $plan = $JsonText | ConvertFrom-Json
    }
    catch {
        throw 'Codex edit plan was not valid JSON.'
    }

    if ($null -eq $plan -or $null -eq $plan.edits) { throw 'Codex edit plan did not contain an edits array.' }
    $edits = @($plan.edits)
    if ($edits.Count -lt 1 -or $edits.Count -gt 20) { throw 'Codex edit plan must contain between 1 and 20 edits.' }

    $validated = @()
    foreach ($edit in $edits) {
        if ($null -eq $edit.path -or $null -eq $edit.old_text -or $null -eq $edit.new_text) {
            throw 'Each edit must contain path, old_text, and new_text.'
        }

        $path = Assert-SafeRepositoryPath -Path ([string]$edit.path)
        $validated += [pscustomobject]@{
            path = $path
            old_text = [string]$edit.old_text
            new_text = [string]$edit.new_text
        }
    }

    return @($validated)
}

function Apply-ValidatedEditPlan {
    param(
        [string]$Root,
        [object[]]$Edits,
        [string[]]$AllowedPaths,
        [string[]]$ForbiddenPaths
    )

    $paths = @($Edits | ForEach-Object { $_.path } | Select-Object -Unique)
    Assert-PathsAllowed -Paths $paths -AllowedPaths $AllowedPaths -ForbiddenPaths $ForbiddenPaths

    $contentByPath = @{}
    foreach ($edit in $Edits) {
        $relativePath = [string]$edit.path
        $targetPath = Join-Path $Root ($relativePath.Replace('/', [System.IO.Path]::DirectorySeparatorChar))

        if (-not $contentByPath.ContainsKey($relativePath)) {
            if (Test-Path -LiteralPath $targetPath -PathType Leaf) {
                $contentByPath[$relativePath] = [System.IO.File]::ReadAllText($targetPath, [System.Text.Encoding]::UTF8)
            }
            else {
                $contentByPath[$relativePath] = $null
            }
        }

        $current = $contentByPath[$relativePath]
        $oldText = [string]$edit.old_text
        $newText = [string]$edit.new_text

        if ($null -eq $current) {
            if (-not [string]::IsNullOrEmpty($oldText)) {
                throw "Cannot create '$relativePath' because old_text is not empty."
            }
            $contentByPath[$relativePath] = $newText
            continue
        }

        if ([string]::IsNullOrEmpty($oldText)) {
            throw "Cannot modify existing file '$relativePath' with an empty old_text anchor."
        }

        $occurrences = Get-SubstringCount -Text $current -Needle $oldText
        if ($occurrences -ne 1) {
            throw "Edit anchor for '$relativePath' matched $occurrences times; exactly one match is required."
        }
        $contentByPath[$relativePath] = $current.Replace($oldText, $newText)
    }

    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    foreach ($relativePath in $contentByPath.Keys) {
        $targetPath = Join-Path $Root ($relativePath.Replace('/', [System.IO.Path]::DirectorySeparatorChar))
        $parent = Split-Path -Parent $targetPath
        if (-not (Test-Path -LiteralPath $parent -PathType Container)) {
            New-Item -ItemType Directory -Path $parent -Force | Out-Null
        }
        [System.IO.File]::WriteAllText($targetPath, [string]$contentByPath[$relativePath], $utf8NoBom)
    }
}

function Test-IssueEligibleForRecovery {
    param([string]$State, [string[]]$Labels)

    if ([string]::IsNullOrWhiteSpace($State) -or $State.ToLowerInvariant() -ne 'open') { return $false }
    return ($Labels -contains $QueueLabel) -or ($Labels -contains $BlockedLabel)
}

function Invoke-CodexReadOnlyEditPlan {
    param([string]$CodexPath, [string]$PromptPath, [string]$WorktreePath, [string]$OutputPath)

    $outputParent = Split-Path -Parent $OutputPath
    if (-not (Test-Path -LiteralPath $outputParent -PathType Container)) {
        New-Item -ItemType Directory -Path $outputParent -Force | Out-Null
    }
    Remove-Item -LiteralPath $OutputPath -Force -ErrorAction SilentlyContinue

    $previousErrorActionPreference = $ErrorActionPreference
    $exitCode = -1
    try {
        $ErrorActionPreference = 'Continue'
        Get-Content -LiteralPath $PromptPath -Raw -Encoding UTF8 |
            & $CodexPath exec --cd $WorktreePath --sandbox read-only --output-last-message $OutputPath - 1> $null 2> $null
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }

    if ($exitCode -ne 0) { throw "Read-only Codex edit-plan generation failed with exit code $exitCode." }
    if (-not (Test-Path -LiteralPath $OutputPath -PathType Leaf)) { throw 'Codex did not produce an edit-plan output file.' }
}

function Invoke-SelfTest {
    $allowed = @('scripts/', 'mini_projects/test/')
    $forbidden = @('final.py')

    if (-not (Test-IssueEligibleForRecovery -State 'OPEN' -Labels @('agent:queued'))) {
        throw 'Open queued Issue eligibility regression failed.'
    }
    if (Test-IssueEligibleForRecovery -State 'CLOSED' -Labels @('agent:queued')) {
        throw 'Closed Issue must never be eligible for recovery.'
    }

    $planText = @'
{"edits":[{"path":"scripts/sample.ps1","old_text":"old","new_text":"새값"}]}
'@
    $edits = @(ConvertFrom-StrictEditPlan -JsonText $planText)
    Assert-PathsAllowed -Paths @($edits[0].path) -AllowedPaths $allowed -ForbiddenPaths $forbidden

    $tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("codex-recovery-selftest-" + [guid]::NewGuid().ToString('N'))
    $scriptDir = Join-Path $tempRoot 'scripts'
    try {
        New-Item -ItemType Directory -Path $scriptDir -Force | Out-Null
        $samplePath = Join-Path $scriptDir 'sample.ps1'
        [System.IO.File]::WriteAllText($samplePath, 'prefix old 최준희 suffix', (New-Object System.Text.UTF8Encoding($false)))
        $unicodePlan = @(
            [pscustomobject]@{ path = 'scripts/sample.ps1'; old_text = 'old'; new_text = '새값' }
        )
        Apply-ValidatedEditPlan -Root $tempRoot -Edits $unicodePlan -AllowedPaths $allowed -ForbiddenPaths $forbidden
        $roundTrip = [System.IO.File]::ReadAllText($samplePath, [System.Text.Encoding]::UTF8)
        if ($roundTrip -ne 'prefix 새값 최준희 suffix') {
            throw 'UTF-8 edit-plan round-trip regression failed.'
        }
    }
    finally {
        Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
    }

    $rejected = $false
    try { [void](ConvertFrom-StrictEditPlan -JsonText '{"edits":[{"path":"../final.py","old_text":"x","new_text":"y"}]}') }
    catch { $rejected = $true }
    if (-not $rejected) { throw 'Unsafe path regression was not rejected.' }

    Write-Output 'Zero-change edit-plan recovery self-test passed.'
}

if ($SelfTest) {
    Invoke-SelfTest
    exit 0
}

$promptPath = $null
$outputPath = $null
$issueNumber = $null

try {
    $repositoryRoot = (Resolve-Path -LiteralPath (Split-Path -Parent $PSScriptRoot)).Path
    if ([string]::IsNullOrWhiteSpace($WorktreeRoot)) {
        $repositoryParent = Split-Path -Parent $repositoryRoot
        $repositoryName = Split-Path -Leaf $repositoryRoot
        $WorktreeRoot = Join-Path $repositoryParent "$repositoryName-agent-worktrees"
    }
    $WorktreeRoot = [System.IO.Path]::GetFullPath($WorktreeRoot)
    $lifecycleDirectory = Join-Path $WorktreeRoot 'lifecycle'
    if (-not (Test-Path -LiteralPath $lifecycleDirectory -PathType Container)) { exit 2 }

    $ghPath = Resolve-RequiredCommand -Names @('gh.exe', 'gh') -DisplayName 'GitHub CLI'
    $codexPath = Resolve-RequiredCommand -Names @('codex.exe', 'codex.cmd', 'codex') -DisplayName 'Codex'

    $stateFile = $null
    $state = $null
    $issue = $null

    $candidateFiles = @(Get-ChildItem -LiteralPath $lifecycleDirectory -Filter 'issue-*.json' -File | Sort-Object LastWriteTimeUtc -Descending)
    foreach ($candidateFile in $candidateFiles) {
        try {
            $candidateState = Get-Content -LiteralPath $candidateFile.FullName -Raw -Encoding UTF8 | ConvertFrom-Json
        }
        catch { continue }

        if ([string]$candidateState.failureReason -notlike '*Codex made no changes*') { continue }

        $candidateIssueNumber = [int]$candidateState.issueNumber
        $candidateIssueJson = & $ghPath issue view $candidateIssueNumber --repo $Repository --json number,title,body,url,state,labels 2> $null
        if ($LASTEXITCODE -ne 0) { continue }

        try { $candidateIssue = $candidateIssueJson | ConvertFrom-Json }
        catch { continue }

        $candidateLabels = @($candidateIssue.labels | ForEach-Object { $_.name })
        if (-not (Test-IssueEligibleForRecovery -State ([string]$candidateIssue.state) -Labels $candidateLabels)) {
            continue
        }

        $stateFile = $candidateFile
        $state = $candidateState
        $issue = $candidateIssue
        break
    }

    if ($null -eq $stateFile -or $null -eq $state -or $null -eq $issue) {
        Write-Output 'No open queued/blocked zero-change Issue is eligible for recovery.'
        exit 2
    }

    $issueNumber = [int]$state.issueNumber
    $worktreePath = [string]$state.worktreePath
    if (-not (Test-Path -LiteralPath $worktreePath -PathType Container)) {
        throw 'Dedicated recovery worktree was not found.'
    }

    $allowedPaths = ConvertTo-ValidatedPathList -Value (Get-IssueField -Body $issue.body -Label 'Allowed paths') -FieldName 'Allowed paths'
    $forbiddenPaths = ConvertTo-ValidatedPathList -Value (Get-IssueField -Body $issue.body -Label 'Forbidden paths') -FieldName 'Forbidden paths'
    $effectiveForbiddenPaths = @($BuiltInForbiddenPaths + $forbiddenPaths | Select-Object -Unique)
    $objective = Get-IssueField -Body $issue.body -Label 'Objective'
    $acceptanceCriteria = Get-IssueField -Body $issue.body -Label 'Acceptance criteria'
    $nextAction = Get-IssueField -Body $issue.body -Label 'Next action'

    $promptPath = (New-TemporaryFile).FullName
    Set-Content -LiteralPath $promptPath -Encoding utf8 -Value @"
You are in a read-only recovery turn for a bounded implementation task on Windows.
Inspect the dedicated Git worktree, but do not write files, commit, push, create a PR, deploy, notify, order, or access secrets.

Return ONLY one strict JSON object with this shape:
{"edits":[{"path":"repository/relative/file","old_text":"exact existing text","new_text":"replacement text"}]}

Rules:
- No Markdown fences or commentary.
- Use only repository-relative ASCII paths from the allowed scope.
- Prefer small exact text replacements; old_text for an existing file must match exactly once.
- To create a new text file, use old_text as an empty string and new_text as the complete file content.
- Do not delete files, rename files, emit binary content, symlinks, submodules, absolute paths, or path traversal.
- Keep the plan to at most 20 edits.
- The host validates every path and every old_text anchor before writing anything, then runs normal path enforcement and tests.

Issue #$issueNumber
$($issue.url)

Objective:
$objective

Acceptance criteria:
$acceptanceCriteria

Next action:
$nextAction

Allowed paths:
$($allowedPaths -join "`n")

Forbidden paths:
$($effectiveForbiddenPaths -join "`n")
"@

    $outputPath = Join-Path $WorktreeRoot "$issueNumber-zero-change-recovery.json"
    Invoke-CodexReadOnlyEditPlan -CodexPath $codexPath -PromptPath $promptPath -WorktreePath $worktreePath -OutputPath $outputPath

    $planText = [System.IO.File]::ReadAllText($outputPath, [System.Text.Encoding]::UTF8)
    $edits = @(ConvertFrom-StrictEditPlan -JsonText $planText)
    Apply-ValidatedEditPlan -Root $worktreePath -Edits $edits -AllowedPaths $allowedPaths -ForbiddenPaths $effectiveForbiddenPaths

    $changedPaths = @(Get-ChangedPaths -Path $worktreePath)
    if ($changedPaths.Count -eq 0) { throw 'Validated edit plan produced no worktree changes.' }
    Assert-PathsAllowed -Paths $changedPaths -AllowedPaths $allowedPaths -ForbiddenPaths $effectiveForbiddenPaths

    $issueLabels = @($issue.labels | ForEach-Object { $_.name })
    if ($issueLabels -contains $BlockedLabel) {
        & $ghPath issue edit $issueNumber --repo $Repository --remove-label $BlockedLabel --add-label $QueueLabel 1> $null 2> $null
        if ($LASTEXITCODE -ne 0) { throw 'Validated changes were applied, but the Issue could not be requeued.' }
    }
    elseif (-not ($issueLabels -contains $QueueLabel)) {
        & $ghPath issue edit $issueNumber --repo $Repository --add-label $QueueLabel 1> $null 2> $null
        if ($LASTEXITCODE -ne 0) { throw 'Validated changes were applied, but the Issue could not be queued.' }
    }

    & $ghPath issue comment $issueNumber --repo $Repository --body 'Control-plane zero-change recovery applied a validated exact-text edit plan inside the dedicated worktree and requeued the Issue. Closed Issues are never eligible for recovery.' 1> $null 2> $null

    Write-Output "Recovered Issue #$issueNumber with a validated exact-text edit plan."
    exit 0
}
catch {
    if ($null -ne $issueNumber) {
        try {
            $ghForComment = Resolve-RequiredCommand -Names @('gh.exe', 'gh') -DisplayName 'GitHub CLI'
            & $ghForComment issue comment $issueNumber --repo $Repository --body 'Control-plane edit-plan recovery did not apply an unvalidated change. Recovery remains bounded and requires another safe attempt or management review.' 1> $null 2> $null
        }
        catch { }
    }
    Write-Error $_.Exception.Message
    exit 1
}
finally {
    if ($null -ne $promptPath) {
        Remove-Item -LiteralPath $promptPath -Force -ErrorAction SilentlyContinue
    }
}
