[CmdletBinding()]
param(
    [ValidateSet("initial", "final")]
    [string]$Round = "initial",

    [ValidateSet("NONE", "PASS", "CHANGES_REQUESTED", "UNAVAILABLE")]
    [string]$PriorVerdict = "NONE",

    [string]$ClaudeOutputPath,

    [string]$StatePath,

    [switch]$SelfTest
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-ClaudeVerdict {
    [CmdletBinding()]
    param(
        [AllowNull()]
        [string]$Output
    )

    if ([string]::IsNullOrWhiteSpace($Output)) {
        return "UNAVAILABLE"
    }

    $matches = [regex]::Matches(
        $Output,
        "(?im)^\s*(?:reviewer_)?verdict\s*:\s*(PASS|CHANGES_REQUESTED)\s*$"
    )

    if ($matches.Count -ne 1) {
        return "UNAVAILABLE"
    }

    return $matches[0].Groups[1].Value.ToUpperInvariant()
}

function Get-NextAction {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [ValidateSet("initial", "final")]
        [string]$ReviewRound,

        [Parameter(Mandatory = $true)]
        [ValidateSet("PASS", "CHANGES_REQUESTED", "UNAVAILABLE")]
        [string]$Verdict
    )

    if ($Verdict -eq "UNAVAILABLE") {
        return "CODEX_SELF_REVIEW_REQUIRED"
    }

    if ($ReviewRound -eq "initial") {
        if ($Verdict -eq "PASS") {
            return "CREATE_DRAFT_PR"
        }

        return "APPLY_MINIMAL_FIX_AND_FINAL_REVIEW"
    }

    if ($Verdict -eq "PASS") {
        return "CREATE_DRAFT_PR"
    }

    return "BLOCK_DRAFT_PR"
}

function New-ReviewState {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [ValidateSet("initial", "final")]
        [string]$ReviewRound,

        [Parameter(Mandatory = $true)]
        [ValidateSet("NONE", "PASS", "CHANGES_REQUESTED", "UNAVAILABLE")]
        [string]$PreviousVerdict,

        [Parameter(Mandatory = $true)]
        [ValidateSet("PASS", "CHANGES_REQUESTED", "UNAVAILABLE")]
        [string]$Verdict
    )

    if ($ReviewRound -eq "initial" -and $PreviousVerdict -ne "NONE") {
        throw "Initial review must not have a prior verdict."
    }

    if ($ReviewRound -eq "final" -and $PreviousVerdict -ne "CHANGES_REQUESTED") {
        throw "Final review is allowed only after an initial CHANGES_REQUESTED verdict."
    }

    [ordered]@{
        reviewer = "claude"
        round = $ReviewRound
        verdict = $Verdict
        next_action = Get-NextAction -ReviewRound $ReviewRound -Verdict $Verdict
    }
}

function Invoke-SelfTest {
    [CmdletBinding()]
    param()

    $passOutput = "VERDICT: PASS"
    $changesOutput = "reviewer_verdict: CHANGES_REQUESTED"
    $ambiguousOutput = "VERDICT: PASS`nVERDICT: CHANGES_REQUESTED"
    $missingOutput = "Please consider adding a test."

    if ((Get-ClaudeVerdict -Output $passOutput) -ne "PASS") {
        throw "PASS verdict parsing failed."
    }

    if ((Get-ClaudeVerdict -Output $changesOutput) -ne "CHANGES_REQUESTED") {
        throw "CHANGES_REQUESTED verdict parsing failed."
    }

    if ((Get-ClaudeVerdict -Output $ambiguousOutput) -ne "UNAVAILABLE") {
        throw "Ambiguous verdict parsing failed."
    }

    if ((Get-ClaudeVerdict -Output $missingOutput) -ne "UNAVAILABLE") {
        throw "Missing verdict parsing failed."
    }

    $initialPass = New-ReviewState -ReviewRound "initial" -PreviousVerdict "NONE" -Verdict "PASS"
    if ($initialPass.next_action -ne "CREATE_DRAFT_PR") {
        throw "Initial PASS must create a draft PR without a final review."
    }

    $initialChanges = New-ReviewState -ReviewRound "initial" -PreviousVerdict "NONE" -Verdict "CHANGES_REQUESTED"
    if ($initialChanges.next_action -ne "APPLY_MINIMAL_FIX_AND_FINAL_REVIEW") {
        throw "Initial changes must permit exactly one final review."
    }

    $finalPass = New-ReviewState -ReviewRound "final" -PreviousVerdict "CHANGES_REQUESTED" -Verdict "PASS"
    if ($finalPass.next_action -ne "CREATE_DRAFT_PR") {
        throw "Final PASS must create a draft PR."
    }

    $finalChanges = New-ReviewState -ReviewRound "final" -PreviousVerdict "CHANGES_REQUESTED" -Verdict "CHANGES_REQUESTED"
    if ($finalChanges.next_action -ne "BLOCK_DRAFT_PR") {
        throw "Final changes must block a draft PR."
    }

    $fallback = New-ReviewState -ReviewRound "initial" -PreviousVerdict "NONE" -Verdict "UNAVAILABLE"
    if ($fallback.next_action -ne "CODEX_SELF_REVIEW_REQUIRED") {
        throw "Unavailable Claude must use Codex self-review fallback."
    }
}

if ($SelfTest) {
    Invoke-SelfTest
    exit 0
}

$claudeOutput = $null
if (-not [string]::IsNullOrWhiteSpace($ClaudeOutputPath)) {
    if (-not (Test-Path -LiteralPath $ClaudeOutputPath -PathType Leaf)) {
        throw "Claude output file does not exist."
    }

    $claudeOutput = [System.IO.File]::ReadAllText($ClaudeOutputPath)
}

$verdict = Get-ClaudeVerdict -Output $claudeOutput
$state = New-ReviewState -ReviewRound $Round -PreviousVerdict $PriorVerdict -Verdict $verdict
$json = $state | ConvertTo-Json -Compress

if (-not [string]::IsNullOrWhiteSpace($StatePath)) {
    [System.IO.File]::WriteAllText(
        $StatePath,
        $json + [Environment]::NewLine,
