[CmdletBinding()]
param([switch]$SkipLiveMutexTests)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'company-runtime-isolation.ps1')
$testRoot = Join-Path ([IO.Path]::GetTempPath()) ('company-isolation-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $testRoot | Out-Null
function Git-Test {
    param([string[]]$Arguments)
    $oldPreference = $ErrorActionPreference
    try { $ErrorActionPreference = 'Continue'; $output = & git @Arguments 2>&1; $code = $LASTEXITCODE }
    finally { $ErrorActionPreference = $oldPreference }
    if ($code -ne 0) { throw ($output -join "`n") }
    return $output
}
function Expect-Rejection {
    param([scriptblock]$Action, [string]$Expected)
    $caught = $null
    try { & $Action | Out-Null } catch { $caught = $_.Exception.Message }
    if ($null -eq $caught -or $caught -notlike "*$Expected*") { throw "Expected rejection '$Expected'; received '$caught'." }
}
$unicodeName = ([string][char]0xD68C) + ([string][char]0xC0AC)
$unicodeRoot = Join-Path $testRoot $unicodeName
New-Item -ItemType Directory -Path $unicodeRoot | Out-Null
$seed = Join-Path $unicodeRoot 'seed'
[void](Git-Test @('init', '-b', 'main', $seed))
Set-Content -LiteralPath (Join-Path $seed 'fixture.txt') -Value 'fixture'
[void](Git-Test @('-C', $seed, 'add', 'fixture.txt'))
[void](Git-Test @('-C', $seed, '-c', 'user.name=Isolation Test', '-c', 'user.email=isolation@example.invalid', 'commit', '-m', 'fixture'))
$a = Join-Path $unicodeRoot 'a'
$b = Join-Path $unicodeRoot 'b'
[void](Git-Test @('clone', '--no-hardlinks', $seed, $a))
[void](Git-Test @('clone', '--no-hardlinks', $seed, $b))
$config = [ordered]@{
    schemaVersion = 1; companyBEnabled = $false
    aPrimaryRoot = $a; aWorktreeRoot = (Join-Path $testRoot 'a-worktrees'); aLogRoot = (Join-Path $testRoot 'a-logs')
    bPrimaryRoot = $b; bWorktreeRoot = (Join-Path $testRoot 'b-worktrees'); bStateRoot = (Join-Path $testRoot 'b-state'); bLogRoot = (Join-Path $testRoot 'b-logs')
}
$configPath = Join-Path $testRoot 'runtime.json'
function Save-TestConfig { $config | ConvertTo-Json | Set-Content -LiteralPath $configPath -Encoding utf8 }
Save-TestConfig
$binding = Get-CompanyRuntimeBinding -RepositoryRoot $a -RuntimeConfigPath $configPath
if ($binding.WorktreeRoot -ne $config.aWorktreeRoot) { throw 'Wrong state/worktree binding.' }
Expect-Rejection { Get-CompanyRuntimeBinding -RepositoryRoot $a -RuntimeConfigPath $configPath -Company B } 'disabled'
Expect-Rejection { Get-CompanyRuntimeBinding -RepositoryRoot $b -RuntimeConfigPath $configPath } 'Wrong primary'
Expect-Rejection { Get-CompanyRuntimeBinding -RepositoryRoot $a -RuntimeConfigPath $configPath -BaseBranch other } 'fixed'
Expect-Rejection { Get-CompanyRuntimeBinding -RepositoryRoot $a -RuntimeConfigPath $configPath -QueueLabel 'company-b:queued' } 'Company B queue'
Expect-Rejection { Get-CompanyRuntimeBinding -RepositoryRoot $a -RuntimeConfigPath $configPath -WorktreeRoot $config.bWorktreeRoot } 'Wrong Company A worktree'
Assert-CompanyAQueueLabels @('agent:queued')
Assert-CompanyAQueueLabels @()
Expect-Rejection { Assert-CompanyAQueueLabels @('company-b:queued') } 'rejected'
Expect-Rejection { Assert-CompanyAQueueLabels @('agent:queued', 'company-b:running') } 'rejected'
$config.bStateRoot = Join-Path $config.aWorktreeRoot 'nested'
Save-TestConfig
Expect-Rejection { Get-CompanyRuntimeBinding -RepositoryRoot $a -RuntimeConfigPath $configPath } 'disjoint'
$config.bStateRoot = Join-Path $testRoot 'b-state'
$config.companyBEnabled = $true
Save-TestConfig
Expect-Rejection { Get-CompanyRuntimeBinding -RepositoryRoot $a -RuntimeConfigPath $configPath } 'premature B'
$config.companyBEnabled = $false
Save-TestConfig
[void](Git-Test @('-C', $a, 'config', '--local', 'company.runtimeConfigPath', $configPath))
if ($null -eq (Get-CompanyRuntimeBinding -RepositoryRoot $a)) { throw 'Local binding was not discovered.' }
[void](Git-Test @('-C', $a, 'switch', '--detach'))
Expect-Rejection { Get-CompanyRuntimeBinding -RepositoryRoot $a -RuntimeConfigPath $configPath } 'remain on main'
[void](Git-Test @('-C', $a, 'switch', 'main'))
$before = Git-Test @('-C', $a, 'rev-parse', 'HEAD')
[void](Git-Test @('-C', $b, 'switch', '-c', 'b-fixture'))
Set-Content -LiteralPath (Join-Path $b 'fixture.txt') -Value 'B changed independently'
[void](Git-Test @('-C', $b, 'add', 'fixture.txt'))
[void](Git-Test @('-C', $b, '-c', 'user.name=Isolation Test', '-c', 'user.email=isolation@example.invalid', 'commit', '-m', 'B fixture'))
if ((Git-Test @('-C', $a, 'rev-parse', 'HEAD')) -ne $before) { throw 'B changed A HEAD.' }
if ((Get-Content -LiteralPath (Join-Path $a 'fixture.txt') -Raw).Trim() -ne 'fixture') { throw 'B changed A worktree.' }
$linked = Join-Path $testRoot 'linked'
[void](Git-Test @('-C', $b, 'worktree', 'add', '--detach', $linked))
$config.bPrimaryRoot = $linked
Save-TestConfig
Expect-Rejection { Get-CompanyRuntimeBinding -RepositoryRoot $a -RuntimeConfigPath $configPath } 'independent full clones'
$config.bPrimaryRoot = $b
Save-TestConfig

# Exercise real entry points while holding their existing process-wide locks.
# The child must exit at the held lock, before state creation or external calls.
$scriptDir = Join-Path $a 'scripts'
New-Item -ItemType Directory -Path $scriptDir | Out-Null
foreach ($file in @('run-codex-queue-scheduled.ps1', 'codex-queue-worker.ps1', 'company-runtime-isolation.ps1')) {
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot $file) -Destination (Join-Path $scriptDir $file)
}
$hostExe = (Get-Process -Id $PID).Path
if (-not $SkipLiveMutexTests) { foreach ($case in @(
    @{ File = 'run-codex-queue-scheduled.ps1'; Mutex = 'Global\rentgist-my-quant-bot-codex-queue-scheduled'; Expected = 0 },
    @{ File = 'codex-queue-worker.ps1'; Mutex = 'Global\rentgist-my-quant-bot-codex-queue'; Expected = 1 }
)) {
    $mutex = New-Object System.Threading.Mutex($false, $case.Mutex)
    if (-not $mutex.WaitOne(0)) { $mutex.Dispose(); throw 'A real worker is active; integration test refused.' }
    try {
        $oldPreference = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        $output = & $hostExe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $scriptDir $case.File) -RuntimeConfigPath $configPath 2>&1
        $code = $LASTEXITCODE
        $ErrorActionPreference = $oldPreference
        if ($code -ne $case.Expected -or ($output -join "`n") -notmatch 'already running') { throw 'Duplicate entry was not rejected by the existing mutex.' }
    } finally { $mutex.ReleaseMutex(); $mutex.Dispose() }
} }
if (Test-Path -LiteralPath $config.aWorktreeRoot) { throw 'Duplicate invocation created state.' }

# Native offline CLI fixture: verify the real worker never mutates a B Issue,
# including a mixed label introduced between listing and the final issue read.
$fakeBin = Join-Path $testRoot 'bin'
if (-not $SkipLiveMutexTests) {
New-Item -ItemType Directory -Path $fakeBin | Out-Null
$fakeSource = @'
using System;
using System.IO;
public class IsolationFakeCli {
    public static int Main(string[] args) {
        string command = String.Join(" ", args);
        File.AppendAllText(Environment.GetEnvironmentVariable("ISOLATION_TEST_CALLS"), command + "\n");
        string testCase = Environment.GetEnvironmentVariable("ISOLATION_TEST_CASE");
        string a = "{\"name\":\"agent:queued\"}";
        string b = "{\"name\":\"company-b:queued\"}";
        if (command.StartsWith("issue list")) {
            bool running = command.Contains("--label agent:running");
            if (running && testCase != "running") { Console.WriteLine("[]"); return 0; }
            if (!running && testCase == "running") { Console.WriteLine("[]"); return 0; }
            Console.WriteLine("[{\"number\":99999,\"title\":\"offline\",\"url\":\"https://example.invalid\",\"labels\":[" + a + (testCase == "view" ? "" : "," + b) + "]}]");
            return 0;
        }
        if (command.StartsWith("issue view")) {
            Console.WriteLine("{\"number\":99999,\"title\":\"offline\",\"body\":\"\",\"url\":\"https://example.invalid\",\"labels\":[" + a + "," + b + "]}");
            return 0;
        }
        return 99;
    }
}
'@
Add-Type -TypeDefinition $fakeSource -OutputAssembly (Join-Path $fakeBin 'gh.exe') -OutputType ConsoleApplication
Copy-Item -LiteralPath (Join-Path $fakeBin 'gh.exe') -Destination (Join-Path $fakeBin 'codex.exe')
$previousPath = $env:PATH
$previousCalls = $env:ISOLATION_TEST_CALLS
$previousCase = $env:ISOLATION_TEST_CASE
try {
    $env:PATH = $fakeBin + [IO.Path]::PathSeparator + $env:PATH
    foreach ($testCase in @('queue', 'running', 'view')) {
        $env:ISOLATION_TEST_CASE = $testCase
        $env:ISOLATION_TEST_CALLS = Join-Path $testRoot ("calls-$testCase.txt")
        $output = & $hostExe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $scriptDir 'codex-queue-worker.ps1') -RuntimeConfigPath $configPath 2>&1
        if ($LASTEXITCODE -ne 4) { throw "Mixed-company $testCase did not fail closed: $output" }
        foreach ($call in @(Get-Content -LiteralPath $env:ISOLATION_TEST_CALLS)) {
            if ($call -notmatch '^issue (list|view) ') { throw 'Mixed-company validation executed a mutating CLI call.' }
        }
    }
} finally {
    $env:PATH = $previousPath
    $env:ISOLATION_TEST_CALLS = $previousCalls
    $env:ISOLATION_TEST_CASE = $previousCase
}
if (@(Get-ChildItem -LiteralPath $config.aWorktreeRoot -File -Recurse).Count -ne 0) { throw 'Mixed-company validation wrote lifecycle state.' }

if (-not $SkipLiveMutexTests) {
    # The actual wrapper must not call diagnostics/recovery after rejection.
    Set-Content -LiteralPath (Join-Path $scriptDir 'codex-queue-worker.ps1') -Value 'exit 4'
    foreach ($file in @('publish-codex-queue-diagnostic.ps1', 'recover-codex-zero-change.ps1', 'publish-codex-recovery-diagnostic.ps1')) {
        Set-Content -LiteralPath (Join-Path $scriptDir $file) -Value 'Set-Content -LiteralPath (Join-Path $PSScriptRoot "unexpected-recovery.txt") -Value "called"'
    }
    Set-Content -LiteralPath (Join-Path $scriptDir 'publish-codex-worker-heartbeat.ps1') -Value 'exit 0'
    $output = & $hostExe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $scriptDir 'run-codex-queue-scheduled.ps1') -RuntimeConfigPath $configPath 2>&1
    if ($LASTEXITCODE -ne 4 -or (Test-Path -LiteralPath (Join-Path $scriptDir 'unexpected-recovery.txt'))) { throw 'Wrapper recovery was not suppressed after isolation rejection.' }
}
}
Write-Output "Company isolation passed: independent clones/HEAD, root/base/queue rejection, B disabled, distinct state roots; live mutex checks skipped=$SkipLiveMutexTests. Fixtures retained for inspection."
exit 0
