[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$MessagePath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-CodexZeroChangeReasonCode {
    param([string]$Text)

    if ([string]::IsNullOrWhiteSpace($Text)) { return 'EMPTY_LAST_MESSAGE' }

    $normalized = ($Text -replace "`r", ' ' -replace "`n", ' ').ToLowerInvariant()

    if ($normalized -match 'cannot\s+(edit|modify|write)|not\s+allowed\s+to\s+(edit|modify|write)|read[- ]only|permission') {
        return 'WRITE_BLOCKED_OR_POLICY_CONFLICT'
    }
    if ($normalized -match 'need\s+more\s+(context|information)|missing\s+(context|information)|cannot\s+determine') {
        return 'MISSING_CONTEXT'
    }
    if ($normalized -match 'plan|analysis|investigat|reviewed|inspected' -and $normalized -notmatch 'updated|changed|modified|implemented|created') {
        return 'ANALYSIS_ONLY'
    }
    if ($normalized -match 'already\s+(implemented|done|satisfied)|no\s+changes\s+(needed|required)|nothing\s+to\s+change') {
        return 'NO_CHANGE_NEEDED'
    }

    return 'UNKNOWN_ZERO_CHANGE'
}

if (-not (Test-Path -LiteralPath $MessagePath -PathType Leaf)) {
    Write-Output 'MISSING_LAST_MESSAGE_FILE'
    exit 0
}

$text = [System.IO.File]::ReadAllText($MessagePath, [System.Text.Encoding]::UTF8)
Write-Output (Get-CodexZeroChangeReasonCode -Text $text)
