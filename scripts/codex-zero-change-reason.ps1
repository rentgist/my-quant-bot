[CmdletBinding()]
param(
    [AllowNull()]
    [AllowEmptyString()]
    [string]$Text,
    [switch]$SelfTest
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-CodexZeroChangeReason {
    param(
        [AllowNull()]
        [AllowEmptyString()]
        [string]$Message
    )

    if ([string]::IsNullOrWhiteSpace($Message)) {
        return "EMPTY_LAST_MESSAGE"
    }

    if ($Message -match "(?i)(read-only|write access|cannot (write|edit|modify)|unable to (write|edit|modify)|not permitted|permission denied|policy conflict|forbidden path|outside (the )?allowed paths?|sandbox.*(blocked|denied))") {
        return "WRITE_BLOCKED_OR_POLICY_CONFLICT"
    }
    if ($Message -match "(?i)(missing context|insufficient (context|information)|need (more |additional )?(context|information)|please (provide|clarify)|cannot find|could not find|not found|no such file|missing (file|details?|requirements?))") {
        return "MISSING_CONTEXT"
    }
    if ($Message -match "(?i)(no changes? (?:(?:is|are|was|were) )?(needed|required|necessary)|nothing to change|already (implemented|correct|satisfies|compliant))") {
        return "NO_CHANGE_NEEDED"
    }
    if ($Message -match "(?i)(analysis only|analy[sz](ed|ing|is).*(no (files? )?(were )?(changed|modified|edited)|without (making )?(changes|edits))|reviewed.*(no (files? )?(were )?(changed|modified|edited)|without (making )?(changes|edits)))") {
        return "ANALYSIS_ONLY"
    }

    return "UNKNOWN_ZERO_CHANGE"
}

if ($SelfTest) {
    $cases = @(
        @{ Text = ""; Expected = "EMPTY_LAST_MESSAGE" },
        @{ Text = "The read-only sandbox prevents me from editing files."; Expected = "WRITE_BLOCKED_OR_POLICY_CONFLICT" },
        @{ Text = "I need more context before I can continue."; Expected = "MISSING_CONTEXT" },
        @{ Text = "Analysis only; no files were changed."; Expected = "ANALYSIS_ONLY" },
        @{ Text = "The requested behavior is already implemented; no change is needed."; Expected = "NO_CHANGE_NEEDED" },
        @{ Text = "I stopped before touching the workspace."; Expected = "UNKNOWN_ZERO_CHANGE" }
    )

    foreach ($case in $cases) {
        $actual = Get-CodexZeroChangeReason -Message $case.Text
        if ($actual -ne $case.Expected) {
            throw "Zero-change reason self-test failed: expected $($case.Expected), got $actual."
        }
    }

    Write-Output "Zero-change reason self-tests passed."
    return
}

Write-Output (Get-CodexZeroChangeReason -Message $Text)
