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

    throw "$DisplayName command was not found."
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

function Assert-SafePatchPath {
    param([Parameter(Mandatory)][string]$Path)

    $normalized = $Path.Replace("\", "/")
    if ($normalized -notmatch "^[A-Za-z0-9._/-]+$" -or $normalized.StartsWith("/") -or $normalized.Contains("//")) {
        throw "Patch contains an invalid repository-relative path."
    }
    $segments = $normalized.Split("/")
    if ($segments.Count -eq 0 -or $segments -contains "." -or $segments -contains "..") {
        throw "Patch contains path traversal."
    }
    return $normalized
}

function Get-PatchPaths {
    param([Parameter(Mandatory)][string]$PatchText)

    if ([string]::IsNullOrWhiteSpace($PatchText)) {
        throw "Codex returned an empty patch."
    }
    if ($PatchText -match "(?m)^```" ) {
        throw "Codex patch output contained Markdown fences instead of a raw unified diff."
    }
    if ($PatchText -match "(?m)^(rename|copy) (from|to) ") {
        throw "Patch rename/copy operations are not allowed."
    }
    if ($PatchText -match "(?m)^(GIT binary patch|Binary files )") {
        throw "Binary patches are not allowed."
    }
    if ($PatchText -match "(?m)^(new file mode|old file mode) (120000|160000)$") {
        throw "Symlink and submodule patches are not allowed."
    }

    $paths = @()
    foreach ($line in ($PatchText -split "`r?`n")) {
        if ($line -match "^diff --git a/(?<old>[A-Za-z0-9._/-]+) b/(?<new>[A-Za-z0-9._/-]+)$") {
            $oldPath = Assert-SafePatchPath -Path $matches.old
            $newPath = Assert-SafePatchPath -Path $matches.new
            if ($oldPath -ne $newPath) {
                throw "Patch path changes are not allowed; use in-place edits or create/delete at one path."
            }
            $paths += $newPath
            continue
        }
        if ($line -match "^diff --git ") {
            throw "Patch contains an unsupported or ambiguous diff path."
        }
        if ($line -match "^(---|\+\+\+) (?<target>.+)$") {
            $target = $matches.target.Trim()
            if ($target -eq "/dev/null") {
                continue
            }
            if ($target -notmatch "^[ab]/(?<path>[A-Za-z0-9._/-]+)$") {
                throw "Patch header contains an unsupported path."
            }
            [void](Assert-SafePatchPath -Path $matches.path)
        }
    }

    $uniquePaths = @($paths | Select-Object -Unique)
    if ($uniquePaths.Count -eq 0) {
        throw "Codex returned no actionable unified diff."
    }
    return $uniquePaths
}

function Assert-PatchPathsAllowed {
    param(
        [Parameter(Mandatory)][string[]]$PatchPaths,
        [Parameter(Mandatory)][string[]]$AllowedPaths,
        [Parameter(Mandatory)][string[]]$ForbiddenPaths
    )

    foreach ($patchPath in $PatchPaths) {
        if ($ForbiddenPaths | Where-Object { Test-PathRuleMatch -Path $patchPath -Rule $_ }) {
            throw "Patch attempted to change a forbidden path."
        }
        if (-not ($AllowedPaths | Where-Object { Test-PathRuleMatch -Path $patchPath -Rule $_ })) {
            throw "Patch attempted to change a path outside the allow-list."
        }
    }
}

function Get-BoundedSummary {
    param(
        [AllowNull()][string]$Text,
        [ValidateRange(80, 1200)][int]$MaxLength = 500
    )

    if ([string]::IsNullOrWhiteSpace($Text)) {
        return "(empty output)"
    }
    $normalized = (($Text -replace "`0", "") -replace "\s+", " ").Trim()
    if ($normalized.Length -le $MaxLength) {
        return $normalized
    }
    return ($normalized.Substring(0, $MaxLength) + "...")
}

function Invoke-CodexReadOnlyPatch {
    param(
        [Parameter(Mandatory)][string]$CodexPath,
        [Parameter(Mandatory)][string]$PromptPath,
        [Parameter(Mandatory)][string]$WorktreePath,
        [Parameter(Mandatory)][string]$OutputPath
    )

    $outputDirectory = Split-Path -Parent $OutputPath
    New-Item -ItemType Directory -Path $outputDirectory -Force | Out-Null
    Remove-Item -LiteralPath $OutputPath -Force -ErrorAction SilentlyContinue

    $codexExitCode = -1
    $previousErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        Get-Content -LiteralPath $PromptPath -Raw |
            & $CodexPath exec --cd $WorktreePath --sandbox read-only --output-last-message $OutputPath - 1> $null 2> $null
        $codexExitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }

    if ($codexExitCode -ne 0) {
        throw "Read-only Codex patch generation failed with exit code $codexExitCode."
    }
    if (-not (Test-Path -LiteralPath $OutputPath -PathType Leaf)) {
        throw "Read-only Codex completed without producing the requested patch output file."
    }
}

function Get-ChangedPaths {
    param([Parameter(Mandatory)][string]$Path)

    $changed = @()
    foreach ($gitArguments in @(
        ,@("-C", $Path, "diff", "--name-only", "--no-ext-diff"),
        ,@("-C", $Path, "diff", "--cached", "--name-only", "--no-ext-diff"),
        ,@("-C", $Path, "ls-files", "--others", "--exclude-standard")
    )) {
        $result = & git @gitArguments
        if ($LASTEXITCODE -ne 0) {
            throw "Could not inspect changes after patch recovery."
        }
        $changed += $result | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
    }
    return @($changed | ForEach-Object { $_.Replace("\", "/") } | Select-Object -Unique)
}

function Invoke-SelfTest {
    $allowed = @("mini_projects/beam_reducer_calculator/")
    $forbidden = @("scripts/", "final.py")
    $validPatch = @"
diff --git a/mini_projects/beam_reducer_calculator/index.html b/mini_projects/beam_reducer_calculator/index.html
new file mode 100644
index 0000000..1111111
--- /dev/null
+++ b/mini_projects/beam_reducer_calculator/index.html
@@ -0,0 +1 @@
+ok
"@
    $paths = Get-PatchPaths -PatchText $validPatch
    Assert-PatchPathsAllowed -PatchPaths $paths -AllowedPaths $allowed -ForbiddenPaths $forbidden
    if ($paths.Count -ne 1 -or $paths[0] -ne "mini_projects/beam_reducer_calculator/index.html") {
        throw "Valid patch path extraction regression failed."
    }

    foreach ($badPatch in @(
        "diff --git a/../final.py b/../final.py`n--- a/../final.py`n+++ b/../final.py",
        "diff --git a/scripts/evil.ps1 b/scripts/evil.ps1`n--- a/scripts/evil.ps1`n+++ b/scripts/evil.ps1",
        "diff --git a/a.txt b/b.txt`nrename from a.txt`nrename to b.txt",
        "diff --git a/x b/x`nnew file mode 120000`n--- /dev/null`n+++ b/x"
    )) {
        $caught = $false
        try {
            $badPaths = Get-PatchPaths -PatchText $badPatch
            Assert-PatchPathsAllowed -PatchPaths $badPaths -AllowedPaths $allowed -ForbiddenPaths $forbidden
        }
        catch {
            $caught = $true
        }
        if (-not $caught) {
            throw "Unsafe patch regression was not rejected."
        }
    }

    $summary = Get-BoundedSummary -Text ("x" * 900) -MaxLength 120
    if ($summary.Length -gt 123) {
        throw "Bounded diagnostic summary regression failed."
    }
    Write-Output "Zero-change patch recovery self-test passed."
}

if ($SelfTest) {
    Invoke-SelfTest
    exit 0
}

$promptPath = $null
$issueNumber = $null
try {
    $repositoryRoot = (Resolve-Path -LiteralPath (Split-Path -Parent $PSScriptRoot)).Path
    if ([string]::IsNullOrWhiteSpace($WorktreeRoot)) {
        $repositoryParent = Split-Path -Parent $repositoryRoot
        $repositoryName = Split-Path -Leaf $repositoryRoot
        $WorktreeRoot = Join-Path $repositoryParent "$repositoryName-agent-worktrees"
    }
    $WorktreeRoot = [System.IO.Path]::GetFullPath($WorktreeRoot)
    $lifecycleDirectory = Join-Path $WorktreeRoot "lifecycle"
    if (-not (Test-Path -LiteralPath $lifecycleDirectory -PathType Container)) {
        exit 2
    }

    $stateFile = Get-ChildItem -LiteralPath $lifecycleDirectory -Filter "issue-*.json" -File |
        Sort-Object LastWriteTimeUtc -Descending |
        Where-Object {
            try {
                $candidate = Get-Content -LiteralPath $_.FullName -Raw | ConvertFrom-Json
                $candidate.failureReason -like "*Codex made no changes*"
            }
            catch {
                $false
            }
        } |
        Select-Object -First 1
    if ($null -eq $stateFile) {
        exit 2
    }

    $state = Get-Content -LiteralPath $stateFile.FullName -Raw | ConvertFrom-Json
    $issueNumber = [int]$state.issueNumber
    $worktreePath = [string]$state.worktreePath
    if (-not (Test-Path -LiteralPath $worktreePath -PathType Container)) {
        throw "Dedicated worktree for zero-change recovery was not found."
    }

    $ghPath = Resolve-RequiredCommand -Names @("gh.exe", "gh") -DisplayName "GitHub CLI"
    $codexPath = Resolve-RequiredCommand -Names @("codex.exe", "codex.cmd", "codex") -DisplayName "Codex"

    $issueJson = & $ghPath issue view $issueNumber --repo $Repository --json number,title,body,url,labels
    if ($LASTEXITCODE -ne 0) {
        throw "Could not read the Issue for zero-change recovery."
    }
    $issue = $issueJson | ConvertFrom-Json
    $allowedPaths = ConvertTo-ValidatedPathList -Value (Get-IssueField -Body $issue.body -Label "Allowed paths") -FieldName "Allowed paths"
    $forbiddenPaths = ConvertTo-ValidatedPathList -Value (Get-IssueField -Body $issue.body -Label "Forbidden paths") -FieldName "Forbidden paths"
    $effectiveForbiddenPaths = @($BuiltInForbiddenPaths + $forbiddenPaths | Select-Object -Unique)

    $objective = Get-IssueField -Body $issue.body -Label "Objective"
    $acceptanceCriteria = Get-IssueField -Body $issue.body -Label "Acceptance criteria"
    $nextAction = Get-IssueField -Body $issue.body -Label "Next action"

    $promptPath = (New-TemporaryFile).FullName
    Set-Content -LiteralPath $promptPath -Encoding utf8 -Value @"
You are in a read-only recovery turn for a bounded implementation task. Inspect the dedicated Git worktree and return ONLY a raw unified diff that implements the requested task. Do not write files, do not commit, do not push, do not use Markdown fences, and do not include commentary before or after the diff. The host will validate every path and run git apply --check before applying anything.

Use ordinary text-file diffs only. Do not emit renames, copies, binary patches, symlinks, submodules, absolute paths, or path traversal. New files must use /dev/null as the old path. Change only allowed paths and never forbidden paths.

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

    $patchOutputPath = Join-Path $WorktreeRoot "$issueNumber-zero-change-recovery.patch"
    Invoke-CodexReadOnlyPatch -CodexPath $codexPath -PromptPath $promptPath -WorktreePath $worktreePath -OutputPath $patchOutputPath
    $patchText = Get-Content -LiteralPath $patchOutputPath -Raw

    try {
        $patchPaths = Get-PatchPaths -PatchText $patchText
        Assert-PatchPathsAllowed -PatchPaths $patchPaths -AllowedPaths $allowedPaths -ForbiddenPaths $effectiveForbiddenPaths
    }
    catch {
        $summary = Get-BoundedSummary -Text $patchText
        throw "Read-only Codex produced an unsafe or unusable patch. Bounded agent output: $summary"
    }

    & git -C $worktreePath apply --check --whitespace=nowarn $patchOutputPath 1> $null 2> $null
    if ($LASTEXITCODE -ne 0) {
        $summary = Get-BoundedSummary -Text $patchText
        throw "git apply --check rejected the recovery patch. Bounded agent output: $summary"
    }
    & git -C $worktreePath apply --whitespace=nowarn $patchOutputPath 1> $null 2> $null
    if ($LASTEXITCODE -ne 0) {
        throw "git apply failed after a successful check; the dedicated worktree was preserved."
    }

    $changedPaths = @(Get-ChangedPaths -Path $worktreePath)
    Assert-PatchPathsAllowed -PatchPaths $changedPaths -AllowedPaths $allowedPaths -ForbiddenPaths $effectiveForbiddenPaths

    $issueLabels = @($issue.labels | ForEach-Object { $_.name })
    if ($issueLabels -contains $BlockedLabel) {
        & $ghPath issue edit $issueNumber --repo $Repository --remove-label $BlockedLabel --add-label $QueueLabel 1> $null 2> $null
        if ($LASTEXITCODE -ne 0) {
            throw "Recovery patch was applied but the Issue could not be requeued."
        }
    }
    elseif ($issueLabels -contains $RunningLabel) {
        & $ghPath issue edit $issueNumber --repo $Repository --remove-label $RunningLabel --add-label $QueueLabel 1> $null 2> $null
        if ($LASTEXITCODE -ne 0) {
            throw "Recovery patch was applied but the Issue could not be requeued."
        }
    }
    elseif (-not ($issueLabels -contains $QueueLabel)) {
        & $ghPath issue edit $issueNumber --repo $Repository --add-label $QueueLabel 1> $null 2> $null
        if ($LASTEXITCODE -ne 0) {
            throw "Recovery patch was applied but the Issue could not be requeued."
        }
    }

    & $ghPath issue comment $issueNumber --repo $Repository --body "Control-plane recovery: a read-only Codex unified diff was path-validated, passed git apply --check, and was applied only inside the dedicated task worktree. The Issue is queued for the normal worker test/review/Draft-PR pipeline." 1> $null 2> $null
    Write-Output "Validated read-only Codex patch applied for Issue #$issueNumber; normal queue processing can resume."
    exit 0
}
catch {
    if ($null -ne $issueNumber) {
        try {
            $ghPathForComment = Resolve-RequiredCommand -Names @("gh.exe", "gh") -DisplayName "GitHub CLI"
            & $ghPathForComment issue comment $issueNumber --repo $Repository --body "Control-plane patch recovery did not apply any unvalidated change. Recovery remains blocked for management review; local bounded diagnostics were preserved." 1> $null 2> $null
        }
        catch {
            # Keep local failure authoritative if remote reporting is unavailable.
        }
    }
    Write-Error $_.Exception.Message
    exit 1
}
finally {
    if ($null -ne $promptPath) {
        Remove-Item -LiteralPath $promptPath -Force -ErrorAction SilentlyContinue
    }
}
