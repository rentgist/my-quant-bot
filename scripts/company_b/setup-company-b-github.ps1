[CmdletBinding()]
param(
    [string]$Repository = "rentgist/my-quant-bot",
    [switch]$SelfTest
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$CompanyBLabels = [ordered]@{
    "company-b:queued" = @{ Color = "0e8a16"; Description = "Company B: queued for the Claude-led queue worker." }
    "company-b:running" = @{ Color = "fbca04"; Description = "Company B: task is currently executing." }
    "company-b:blocked" = @{ Color = "d93f0b"; Description = "Company B: task failed closed; human review required." }
    "company-b:done" = @{ Color = "5319e7"; Description = "Company B: Draft PR and durable evidence published." }
    "company-b:approval-required" = @{ Color = "b60205"; Description = "Company B: elevated risk; explicit human approval required before merge." }
}

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

    throw "$DisplayName command was not found. No repository or GitHub state was changed."
}

function Test-CompanyBLabelSetSelfTest {
    # Offline only: asserts the label set shape without requiring an authenticated repository.
    $names = @($CompanyBLabels.Keys)
    if (@($names).Count -ne 5) {
        throw "Company B label set must contain exactly 5 labels."
    }
    foreach ($name in $names) {
        if ($name -notlike "company-b:*") {
            throw "Company B label '$name' is missing the required 'company-b:' prefix."
        }
        if ($name -like "agent:*") {
            throw "Company B label set must never contain an agent:* label."
        }
    }
    $expected = @("company-b:queued", "company-b:running", "company-b:blocked", "company-b:done", "company-b:approval-required")
    foreach ($label in $expected) {
        if ($names -notcontains $label) {
            throw "Company B label set is missing required label '$label'."
        }
    }
    Write-Output "Company B label self-test passed."
}

if ($SelfTest) {
    Test-CompanyBLabelSetSelfTest
    exit 0
}

$ghPath = Resolve-RequiredCommand -Names @("gh.exe", "gh") -DisplayName "GitHub CLI"

$existingJson = & $ghPath label list --repo $Repository --json name --limit 200
if ($LASTEXITCODE -ne 0) {
    throw "Could not list existing GitHub labels for $Repository."
}
$existingNames = @(($existingJson | ConvertFrom-Json) | ForEach-Object { $_.name })

foreach ($labelName in $CompanyBLabels.Keys) {
    $definition = $CompanyBLabels[$labelName]
    if ($existingNames -contains $labelName) {
        & $ghPath label edit $labelName --repo $Repository --color $definition.Color --description $definition.Description 1> $null 2> $null
        if ($LASTEXITCODE -ne 0) {
            throw "Could not update existing Company B label '$labelName'."
        }
    }
    else {
        & $ghPath label create $labelName --repo $Repository --color $definition.Color --description $definition.Description 1> $null 2> $null
        if ($LASTEXITCODE -ne 0) {
            throw "Could not create Company B label '$labelName'."
        }
    }
}

Write-Output "Company B GitHub labels are ensured: $(($CompanyBLabels.Keys) -join ', ')"
