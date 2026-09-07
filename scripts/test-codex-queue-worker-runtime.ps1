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

foreach ($functionName in @("Test-PathRuleMatch", "Assert-ChangedPathsAllowed")) {
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
Write-Output "ChangedPaths runtime regression passed."
