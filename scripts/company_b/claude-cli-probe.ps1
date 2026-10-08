[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Resolve-ClaudeCommand {
    foreach ($name in @("claude.cmd", "claude.exe", "claude")) {
        $command = Get-Command $name -ErrorAction SilentlyContinue
        if ($null -ne $command) {
            return $command.Source
        }
    }
    foreach ($base in @($env:APPDATA, $env:LOCALAPPDATA)) {
        if ([string]::IsNullOrWhiteSpace($base)) { continue }
        foreach ($name in @("claude.cmd", "claude.exe", "claude")) {
            $candidate = Join-Path $base "npm\$name"
            if (Test-Path -LiteralPath $candidate -PathType Leaf) {
                return $candidate
            }
        }
    }
    throw "Claude Code command not found."
}

function Get-SafeText {
    param([AllowNull()][AllowEmptyString()][string]$Text)
    if ([string]::IsNullOrWhiteSpace($Text)) { return "(empty)" }
    $safe = $Text
    if (-not [string]::IsNullOrWhiteSpace($env:USERPROFILE)) {
        $safe = $safe.Replace($env:USERPROFILE, "<USER_HOME>")
    }
    $safe = [regex]::Replace($safe, '(?i)(sk-ant-[A-Za-z0-9_-]+|ANTHROPIC_API_KEY\s*=\s*\S+|ANTHROPIC_AUTH_TOKEN\s*=\s*\S+)', '<REDACTED>')
    $safe = $safe.Trim()
    if ($safe.Length -gt 1200) { $safe = $safe.Substring(0, 1200) + "..." }
    return $safe
}

function Write-ProbeLine {
    param([Parameter(Mandatory)][AllowEmptyString()][string]$Text)
    [Console]::Out.WriteLine($Text)
}

function Invoke-Probe {
    param(
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][string]$ClaudePath,
        [Parameter(Mandatory)][string[]]$Arguments
    )

    $outPath = [System.IO.Path]::GetTempFileName()
    $errPath = [System.IO.Path]::GetTempFileName()
    try {
        "Reply with exactly: COMPANY_B_CLAUDE_OK" |
            & $ClaudePath @Arguments 1> $outPath 2> $errPath
        $exitCode = $LASTEXITCODE
        $stdout = Get-Content -LiteralPath $outPath -Raw -ErrorAction SilentlyContinue
        $stderr = Get-Content -LiteralPath $errPath -Raw -ErrorAction SilentlyContinue
        Write-ProbeLine "=== $Name ==="
        Write-ProbeLine "exit_code: $exitCode"
        Write-ProbeLine ("stdout: " + (Get-SafeText -Text $stdout))
        Write-ProbeLine ("stderr: " + (Get-SafeText -Text $stderr))
        Write-ProbeLine ""
        return [int]$exitCode
    }
    finally {
        Remove-Item -LiteralPath $outPath, $errPath -Force -ErrorAction SilentlyContinue
    }
}

$claudePath = Resolve-ClaudeCommand
Write-ProbeLine "Claude path: $claudePath"
& $claudePath --version
Write-ProbeLine ""

$basic = Invoke-Probe -Name "BASIC_PRINT" -ClaudePath $claudePath -Arguments @("-p", "--output-format", "text")
$model = Invoke-Probe -Name "SONNET5_PRINT" -ClaudePath $claudePath -Arguments @("-p", "--model", "claude-sonnet-5", "--output-format", "text")
$plan = Invoke-Probe -Name "SONNET5_PLAN_READONLY" -ClaudePath $claudePath -Arguments @("-p", "--model", "claude-sonnet-5", "--permission-mode", "plan", "--max-turns", "4", "--output-format", "text", "--disallowedTools", "Edit", "Write", "Bash")

if ($basic -eq 0 -and $model -eq 0 -and $plan -eq 0) {
    Write-ProbeLine "Company B Claude CLI probe: PASS"
    exit 0
}

Write-ProbeLine "Company B Claude CLI probe: FAIL"
exit 1
