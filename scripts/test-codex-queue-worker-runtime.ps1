[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$workerPath = Join-Path $PSScriptRoot "codex-queue-worker.ps1"
$source = Get-Content -LiteralPath $workerPath -Raw
$tokens = $null
$errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseInput(
    $source,
    [ref]$tokens,
    [ref]$errors
)

if ($errors.Count -gt 0) {
    throw "Worker source did not parse."
}

foreach ($functionName in @("Test-PathRuleMatch", "Assert-ChangedPathsAllowed", "Get-AgentModelRoute")) {
    $functionAst = $ast.Find(
        {
            param($node)
            $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
                $node.Name -eq $functionName
        },
        $true
    )
    if ($null -eq $functionAst) {
        throw "Could not find function '$functionName' in worker source."
    }
    Invoke-Expression $functionAst.Extent.Text
}

$expected = "Codex made no changes; Draft PR creation was skipped."
foreach ($case in @($null, @())) {
    $caught = $null
    try {
        Assert-ChangedPathsAllowed -ChangedPaths $case -AllowedPaths @("scripts/") -ForbiddenPaths @("final.py")
    }
    catch {
        $caught = $_.Exception.Message
    }

    if ($caught -ne $expected) {
        throw "Empty ChangedPaths regression failed. Expected '$expected' but got '$caught'."
    }
}

Assert-ChangedPathsAllowed -ChangedPaths @("scripts/example.ps1") -AllowedPaths @("scripts/") -ForbiddenPaths @("final.py")

if ((Get-AgentModelRoute -RiskTier "low" -DefaultModel "gpt-5.6-terra" -ElevatedModel "gpt-5.6-sol") -ne "gpt-5.6-terra") {
    throw "Low-risk Codex routing regression failed."
}
if ((Get-AgentModelRoute -RiskTier "medium" -DefaultModel "claude-sonnet-5" -ElevatedModel "claude-opus-5") -ne "claude-sonnet-5") {
    throw "Medium-risk Claude routing regression failed."
}
if ((Get-AgentModelRoute -RiskTier "high" -DefaultModel "gpt-5.6-terra" -ElevatedModel "gpt-5.6-sol") -ne "gpt-5.6-sol") {
    throw "High-risk Codex routing regression failed."
}
if ((Get-AgentModelRoute -RiskTier "critical" -DefaultModel "claude-sonnet-5" -ElevatedModel "claude-opus-5") -ne "claude-opus-5") {
    throw "Critical-risk Claude routing regression failed."
}
if ($source -notmatch [regex]::Escape('exec --model $Model')) {
    throw "Codex invocation is not explicitly wired to the selected model."
}
if ($source -notmatch [regex]::Escape('-PreferredModel $selectedClaudeModel -FallbackModel $claudeFallbackModel')) {
    throw "Claude invocation is not explicitly wired to the selected/fallback models."
}

Write-Output "ChangedPaths and model-routing runtime regressions passed."
