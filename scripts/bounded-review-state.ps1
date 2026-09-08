[CmdletBinding()]
param(
    [ValidateSet("initial", "final")]
    [string]$Round = "initial",

    [ValidateSet("PASS", "CHANGES_REQUESTED", "UNAVAILABLE")]
    [string]$Verdict = "UNAVAILABLE",

    [switch]$SelfTest
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-BoundedReviewAction {
    param(
        [Parameter(Mandatory)][ValidateSet("initial", "final")][string]$ReviewRound,
        [Parameter(Mandatory)][ValidateSet("PASS", "CHANGES_REQUESTED", "UNAVAILABLE")][string]$ReviewVerdict
    )

    if ($ReviewVerdict -eq "UNAVAILABLE") {
        return "CODEX_SELF_REVIEW"
    }

    if ($ReviewRound -eq "initial") {
        if ($ReviewVerdict -eq "PASS") {
            return "PROCEED"
        }
        return "RESOLVE_AND_FINAL_REVIEW"
    }

    if ($ReviewVerdict -eq "PASS") {
        return "PROCEED"
    }

    return "BLOCK"
}

function Invoke-SelfTest {
    if ((Get-BoundedReviewAction -ReviewRound "initial" -ReviewVerdict "PASS") -ne "PROCEED") {
        throw "Initial PASS state regression failed."
    }
    if ((Get-BoundedReviewAction -ReviewRound "initial" -ReviewVerdict "CHANGES_REQUESTED") -ne "RESOLVE_AND_FINAL_REVIEW") {
        throw "Initial CHANGES_REQUESTED state regression failed."
    }
    if ((Get-BoundedReviewAction -ReviewRound "final" -ReviewVerdict "PASS") -ne "PROCEED") {
        throw "Final PASS state regression failed."
    }
    if ((Get-BoundedReviewAction -ReviewRound "final" -ReviewVerdict "CHANGES_REQUESTED") -ne "BLOCK") {
        throw "Final CHANGES_REQUESTED state regression failed."
    }
    if ((Get-BoundedReviewAction -ReviewRound "initial" -ReviewVerdict "UNAVAILABLE") -ne "CODEX_SELF_REVIEW") {
        throw "Initial unavailable fallback regression failed."
    }
    if ((Get-BoundedReviewAction -ReviewRound "final" -ReviewVerdict "UNAVAILABLE") -ne "CODEX_SELF_REVIEW") {
        throw "Final unavailable fallback regression failed."
    }
    Write-Output "Bounded review state self-test passed."
}

if ($SelfTest) {
    Invoke-SelfTest
    exit 0
}

Write-Output (Get-BoundedReviewAction -ReviewRound $Round -ReviewVerdict $Verdict)
