[CmdletBinding()]
param(
    [string]$WorktreePath,
    [string]$TestResultPath,
    [string]$ReviewOutputPath,
    [string]$BaseBranch = "main",
    [ValidateSet("initial", "final")]
    [string]$Round = "initial",
    [ValidateRange(256, 8192)]
    [int]$MaxOutputChars = 2048,
    [string]$PreferredModel = "claude-sonnet-5",
    [string]$FallbackModel = "claude-sonnet-5",
    [switch]$SelfTest
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Resolve-OptionalCommand {
    param([Parameter(Mandatory)][string[]]$Names)

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

    return $null
}

function Get-TaskStagedDiffUtf8 {
    param([Parameter(Mandatory)][string]$WorktreePath)

    $resolvedWorktree = (Resolve-Path -LiteralPath $WorktreePath).Path
    $gitPath = Resolve-OptionalCommand -Names @("git.exe", "git")
    if ($null -eq $gitPath) {
        throw "Git command was not found."
    }

    $strictUtf8 = New-Object System.Text.UTF8Encoding($false, $true)
    $startInfo = New-Object System.Diagnostics.ProcessStartInfo
    $startInfo.FileName = $gitPath
    $startInfo.WorkingDirectory = $resolvedWorktree
    $startInfo.Arguments = "-c core.quotepath=false diff --cached --no-ext-diff --unified=80 HEAD --"
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $startInfo.StandardOutputEncoding = $strictUtf8
    $startInfo.StandardErrorEncoding = $strictUtf8

    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $startInfo
    try {
        if (-not $process.Start()) {
            throw "Could not start Git while reading the staged diff for review."
        }
        $standardOutputTask = $process.StandardOutput.ReadToEndAsync()
        $standardErrorTask = $process.StandardError.ReadToEndAsync()
        $process.WaitForExit()
        $diff = $standardOutputTask.GetAwaiter().GetResult()
        $standardError = $standardErrorTask.GetAwaiter().GetResult()
        if ($process.ExitCode -ne 0) {
            throw "Could not read the staged diff for review."
        }
        return $diff
    }
    finally {
        $process.Dispose()
    }
}

function Get-ClaudeVerdict {
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

function Get-BoundedText {
    param([AllowNull()][string]$Text, [int]$Limit)

    if ([string]::IsNullOrWhiteSpace($Text)) {
        return "(empty output)"
    }

    $normalized = (($Text -replace "`0", '') -replace '\r\n', "`n").Trim()
    $normalized = [regex]::Replace($normalized, '(?im)^\s*VERDICT\s*:\s*(PASS|CHANGES_REQUESTED)\s*$', '').Trim()
    if ([string]::IsNullOrWhiteSpace($normalized)) {
        return "(verdict only)"
    }
    if ($normalized.Length -le $Limit) {
        return $normalized
    }
    return $normalized.Substring(0, $Limit) + "..."
}

function Write-ReviewReport {
    param(
        [Parameter(Mandatory)][ValidateSet("PASS", "CHANGES_REQUESTED", "UNAVAILABLE")][string]$Verdict,
        [Parameter(Mandatory)][string]$Summary,
        [Parameter(Mandatory)][string]$Reason,
        [Parameter(Mandatory)][string]$ModelUsed
    )

    $report = @"
reviewer: Claude Code
round: $Round
model: $ModelUsed
VERDICT: $Verdict
reason: $Reason
summary:
$Summary
"@
    Set-Content -LiteralPath $ReviewOutputPath -Value $report -Encoding utf8
}

function Exit-WithVerdict {
    param(
        [Parameter(Mandatory)][ValidateSet("PASS", "CHANGES_REQUESTED", "UNAVAILABLE")][string]$Verdict,
        [Parameter(Mandatory)][string]$Summary,
        [Parameter(Mandatory)][string]$Reason,
        [Parameter(Mandatory)][string]$ModelUsed
    )

    Write-ReviewReport -Verdict $Verdict -Summary $Summary -Reason $Reason -ModelUsed $ModelUsed
    if ($Verdict -eq "PASS") {
        Write-Output "Claude review: PASS ($Round, $ModelUsed)."
        exit 0
    }
    if ($Verdict -eq "CHANGES_REQUESTED") {
        Write-Output "Claude review: CHANGES_REQUESTED ($Round, $ModelUsed)."
        exit 20
    }
    Write-Output "Claude review: UNAVAILABLE ($Reason)"
    exit 10
}

function Invoke-ClaudeReadOnly {
    param(
        [Parameter(Mandatory)][string]$ClaudePath,
        [Parameter(Mandatory)][string]$PromptPath,
        [Parameter(Mandatory)][string]$OutputPath,
        [Parameter(Mandatory)][string]$Model
    )

    Remove-Item -LiteralPath $OutputPath -Force -ErrorAction SilentlyContinue
    $previousErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        Get-Content -LiteralPath $PromptPath -Raw |
            & $ClaudePath -p --model $Model --permission-mode plan --max-turns 1 --output-format text --disallowedTools "Edit" "Write" "Bash" 1> $OutputPath 2> $null
        return $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
}

function Invoke-SelfTest {
    if ((Get-ClaudeVerdict -Output "VERDICT: PASS") -ne "PASS") {
        throw "PASS verdict parsing regression failed."
    }
    if ((Get-ClaudeVerdict -Output "Finding`nVERDICT: CHANGES_REQUESTED") -ne "CHANGES_REQUESTED") {
        throw "CHANGES_REQUESTED verdict parsing regression failed."
    }
    if ((Get-ClaudeVerdict -Output "VERDICT: PASS`nVERDICT: CHANGES_REQUESTED") -ne "UNAVAILABLE") {
        throw "Ambiguous verdict must be unavailable."
    }
    if ((Get-ClaudeVerdict -Output "No machine-readable verdict") -ne "UNAVAILABLE") {
        throw "Missing verdict must be unavailable."
    }
    $bounded = Get-BoundedText -Text ('x' * 5000) -Limit 512
    if ($bounded.Length -gt 515) {
        throw "Bounded review output regression failed."
    }
    $summaryWithoutVerdict = Get-BoundedText -Text "VERDICT: PASS`nNo blocking findings." -Limit 512
    if ($summaryWithoutVerdict -match '(?im)^\s*VERDICT\s*:') {
        throw "Review summary must not duplicate the machine-readable verdict line."
    }
    if ($PreferredModel -ne "claude-sonnet-5" -or $FallbackModel -ne "claude-sonnet-5") {
        throw "Default Claude model routing regression failed."
    }

    $gitPath = Resolve-OptionalCommand -Names @("git.exe", "git")
    if ($null -eq $gitPath) {
        throw "Git is required for the staged-diff self-test."
    }
    $tempRoot = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
    $tempContainer = Join-Path $tempRoot ("codex-review-diff-self-test-" + [Guid]::NewGuid().ToString("N"))
    $tempRepository = Join-Path $tempContainer "repository"
    $taskWorktree = Join-Path $tempContainer "task-worktree"
    $strictUtf8 = New-Object System.Text.UTF8Encoding($false, $true)
    $invokeGit = {
        param([string]$RepositoryPath, [string[]]$Arguments)

        $previousErrorActionPreference = $ErrorActionPreference
        try {
            $ErrorActionPreference = "Continue"
            $nativeOutput = & $gitPath -C $RepositoryPath @Arguments 2> $null
            $nativeExitCode = $LASTEXITCODE
        }
        finally {
            $ErrorActionPreference = $previousErrorActionPreference
        }
        if ($nativeExitCode -ne 0) {
            throw "Git command failed during the staged-diff self-test."
        }
        return ((@($nativeOutput) | ForEach-Object { [string]$_ }) -join "`n")
    }

    New-Item -ItemType Directory -Path $tempRepository -Force | Out-Null
    try {
        & $invokeGit -RepositoryPath $tempRepository -Arguments @("init") | Out-Null
        & $invokeGit -RepositoryPath $tempRepository -Arguments @("branch", "-M", "main") | Out-Null
        & $invokeGit -RepositoryPath $tempRepository -Arguments @("config", "user.name", "Review Diff Self-Test") | Out-Null
        & $invokeGit -RepositoryPath $tempRepository -Arguments @("config", "user.email", "review-diff-self-test@example.invalid") | Out-Null
        [System.IO.File]::WriteAllText((Join-Path $tempRepository "base.txt"), "base`n", $strictUtf8)
        & $invokeGit -RepositoryPath $tempRepository -Arguments @("add", "--", "base.txt") | Out-Null
        & $invokeGit -RepositoryPath $tempRepository -Arguments @("-c", "commit.gpgSign=false", "commit", "--no-verify", "-m", "base") | Out-Null
        & $invokeGit -RepositoryPath $tempRepository -Arguments @("worktree", "add", "-b", "task", $taskWorktree, "main") | Out-Null

        $taskMarker = "검토 입력"
        [System.IO.File]::WriteAllText((Join-Path $taskWorktree "task.txt"), "$taskMarker`n", $strictUtf8)
        & $invokeGit -RepositoryPath $taskWorktree -Arguments @("add", "--", "task.txt") | Out-Null
        $originalTaskHead = (& $invokeGit -RepositoryPath $taskWorktree -Arguments @("rev-parse", "HEAD")).Trim()

        $mainDriftMarker = "unrelated-main-drift"
        [System.IO.File]::WriteAllText((Join-Path $tempRepository "main-only.txt"), "$mainDriftMarker`n", $strictUtf8)
        & $invokeGit -RepositoryPath $tempRepository -Arguments @("add", "--", "main-only.txt") | Out-Null
        & $invokeGit -RepositoryPath $tempRepository -Arguments @("-c", "commit.gpgSign=false", "commit", "--no-verify", "-m", "advance main") | Out-Null
        $advancedMainHead = (& $invokeGit -RepositoryPath $tempRepository -Arguments @("rev-parse", "main")).Trim()
        $currentTaskHead = (& $invokeGit -RepositoryPath $taskWorktree -Arguments @("rev-parse", "HEAD")).Trim()
        if ($advancedMainHead -ceq $originalTaskHead -or $currentTaskHead -cne $originalTaskHead) {
            throw "Base-branch drift self-test setup failed."
        }

        $stagedDiff = Get-TaskStagedDiffUtf8 -WorktreePath $taskWorktree
        if (-not $stagedDiff.Contains($taskMarker)) {
            throw "UTF-8 staged-diff round-trip self-test failed."
        }
        if ($stagedDiff.Contains($mainDriftMarker)) {
            throw "Base-branch drift contaminated the task-relative staged diff."
        }
        if ($stagedDiff.Contains([char]0xfffd) -or $stagedDiff.Contains("????")) {
            throw "Staged-diff capture produced invalid UTF-8 reviewer input."
        }
    }
    finally {
        $resolvedTempContainer = [System.IO.Path]::GetFullPath($tempContainer)
        if (-not $resolvedTempContainer.StartsWith($tempRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "Staged-diff self-test cleanup path escaped the temporary directory."
        }
        Remove-Item -LiteralPath $resolvedTempContainer -Recurse -Force -ErrorAction SilentlyContinue
    }

    Write-Output "Claude review parser/model and staged-diff self-tests passed."
}

if ($SelfTest) {
    Invoke-SelfTest
    exit 0
}

if ([string]::IsNullOrWhiteSpace($WorktreePath) -or
    [string]::IsNullOrWhiteSpace($TestResultPath) -or
    [string]::IsNullOrWhiteSpace($ReviewOutputPath)) {
    throw "WorktreePath, TestResultPath, and ReviewOutputPath are required outside SelfTest mode."
}
if ([string]::IsNullOrWhiteSpace($PreferredModel)) {
    throw "PreferredModel must be explicit and non-empty."
}

try {
    $resolvedWorktree = (Resolve-Path -LiteralPath $WorktreePath).Path
    $resolvedTestResult = (Resolve-Path -LiteralPath $TestResultPath).Path
    $outputParent = Split-Path -Parent $ReviewOutputPath
    if (-not (Test-Path -LiteralPath $outputParent -PathType Container)) {
        New-Item -ItemType Directory -Path $outputParent -Force | Out-Null
    }

    $claudePath = Resolve-OptionalCommand -Names @("claude.cmd", "claude.exe", "claude")
    if ($null -eq $claudePath) {
        Exit-WithVerdict -Verdict "UNAVAILABLE" -Summary "Claude Code command was not found." -Reason "command-not-found" -ModelUsed $PreferredModel
    }

    $diff = Get-TaskStagedDiffUtf8 -WorktreePath $resolvedWorktree
    $testSummary = Get-Content -LiteralPath $resolvedTestResult -Raw
    $reviewPrompt = @"
You are an independent read-only senior code reviewer performing the $Round review round.
Review only the supplied staged diff and test summary. Do not run commands or attempt edits, Git operations,
deployment, ordering, notifications, or secret access. Focus on correctness, regressions, safety boundaries,
and whether the stated tests support the change.

Your response MUST contain exactly one machine-readable verdict line, by itself, in one of these forms:
VERDICT: PASS
VERDICT: CHANGES_REQUESTED

Use CHANGES_REQUESTED only for a concrete blocking defect. Keep the entire response concise. After the verdict,
you may include short findings with severity, file path, and rationale. Never include secrets or local paths.

TEST SUMMARY
$testSummary

STAGED DIFF
$diff
"@

    $tempPrompt = New-TemporaryFile
    $rawOutputPath = [System.IO.Path]::GetTempFileName()
    try {
        Set-Content -LiteralPath $tempPrompt.FullName -Value $reviewPrompt -Encoding utf8
        Push-Location -LiteralPath $tempPrompt.DirectoryName
        try {
            $modelUsed = $PreferredModel
            $claudeExitCode = Invoke-ClaudeReadOnly -ClaudePath $claudePath -PromptPath $tempPrompt.FullName -OutputPath $rawOutputPath -Model $PreferredModel
            if ($claudeExitCode -ne 0 -and
                -not [string]::IsNullOrWhiteSpace($FallbackModel) -and
                $FallbackModel -ne $PreferredModel) {
                $modelUsed = $FallbackModel
                $claudeExitCode = Invoke-ClaudeReadOnly -ClaudePath $claudePath -PromptPath $tempPrompt.FullName -OutputPath $rawOutputPath -Model $FallbackModel
            }
        }
        finally {
            Pop-Location
        }

        if ($claudeExitCode -ne 0) {
            Exit-WithVerdict -Verdict "UNAVAILABLE" -Summary "Claude Code did not complete the read-only review with the configured model route." -Reason "model-unavailable-or-unauthenticated" -ModelUsed $modelUsed
        }

        $rawOutput = Get-Content -LiteralPath $rawOutputPath -Raw -ErrorAction SilentlyContinue
        $verdict = Get-ClaudeVerdict -Output $rawOutput
        $boundedSummary = Get-BoundedText -Text $rawOutput -Limit $MaxOutputChars
        if ($verdict -eq "UNAVAILABLE") {
            Exit-WithVerdict -Verdict "UNAVAILABLE" -Summary $boundedSummary -Reason "missing-or-ambiguous-verdict" -ModelUsed $modelUsed
        }
        Exit-WithVerdict -Verdict $verdict -Summary $boundedSummary -Reason "completed-read-only" -ModelUsed $modelUsed
    }
    finally {
        Remove-Item -LiteralPath $tempPrompt.FullName -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $rawOutputPath -Force -ErrorAction SilentlyContinue
    }
}
catch {
    Exit-WithVerdict -Verdict "UNAVAILABLE" -Summary "Claude review could not start safely." -Reason "safe-start-failure" -ModelUsed $PreferredModel
}
