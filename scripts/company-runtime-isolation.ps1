# Shared validation only. The existing queue worker remains the execution engine.
function Get-IsolatedRuntimePath {
    param([Parameter(Mandatory)][string]$Path)
    if (-not [System.IO.Path]::IsPathRooted($Path)) { throw 'Runtime paths must be absolute.' }
    $full = [System.IO.Path]::GetFullPath($Path).TrimEnd('\', '/')
    $cursor = $full
    while (-not [string]::IsNullOrWhiteSpace($cursor)) {
        if (Test-Path -LiteralPath $cursor) {
            if ((Get-Item -LiteralPath $cursor -Force).Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
                throw 'Runtime paths must not contain junctions or symbolic links.'
            }
        }
        $cursor = Split-Path -Parent $cursor
    }
    return $full
}

function Test-RuntimePathOverlap {
    param([string]$Left, [string]$Right)
    $a = $Left.Replace('\', '/').TrimEnd('/') + '/'
    $b = $Right.Replace('\', '/').TrimEnd('/') + '/'
    return $a.StartsWith($b, [StringComparison]::OrdinalIgnoreCase) -or $b.StartsWith($a, [StringComparison]::OrdinalIgnoreCase)
}

function Assert-CompanyAQueueLabels {
    param([AllowEmptyCollection()][string[]]$Labels)
    foreach ($label in $Labels) {
        if ($label -match '^(company-b:|company:b$)') {
            $errorRecord = New-Object System.InvalidOperationException('Company B or mixed-company Issue rejected before lifecycle mutation.')
            $errorRecord.Data['CompanyIsolation'] = $true
            throw $errorRecord
        }
    }
}

function Get-CompanyRuntimeBinding {
    param(
        [Parameter(Mandatory)][string]$RepositoryRoot,
        [string]$RuntimeConfigPath,
        [string]$Company = 'A',
        [string]$Repository = 'rentgist/my-quant-bot',
        [string]$BaseBranch = 'main',
        [string]$QueueLabel = 'agent:queued',
        [string]$WorktreeRoot
    )
    if ($Company -cne 'A') { throw 'Company B execution is disabled pending a separately validated activation.' }
    if ($QueueLabel -match '^company-b:') { throw 'Company B queue cannot be used by Company A.' }
    if ([string]::IsNullOrWhiteSpace($RuntimeConfigPath)) {
        $configured = @(& git -C $RepositoryRoot config --local --get company.runtimeConfigPath)
        if ($LASTEXITCODE -notin @(0, 1)) { throw 'Could not read the local runtime binding.' }
        if ($LASTEXITCODE -eq 0) { $RuntimeConfigPath = $configured -join '' }
    }
    # Existing installations retain their configuration until explicitly migrated.
    if ([string]::IsNullOrWhiteSpace($RuntimeConfigPath)) { return $null }
    $configPath = Get-IsolatedRuntimePath $RuntimeConfigPath
    $config = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
    if ($config.schemaVersion -ne 1 -or $config.companyBEnabled -isnot [bool] -or $config.companyBEnabled) { throw 'Unsupported runtime configuration or premature B activation.' }
    if ($Repository -cne 'rentgist/my-quant-bot' -or $BaseBranch -cne 'main' -or $QueueLabel -cne 'agent:queued') {
        throw 'Company A repository, base, and queue are fixed by the isolated runtime contract.'
    }
    $paths = @{}
    foreach ($name in @('aPrimaryRoot', 'aWorktreeRoot', 'aLogRoot', 'bPrimaryRoot', 'bWorktreeRoot', 'bStateRoot', 'bLogRoot')) {
        $paths[$name] = Get-IsolatedRuntimePath ([string]$config.$name)
    }
    $names = @($paths.Keys)
    for ($i = 0; $i -lt $names.Count; $i++) {
        for ($j = $i + 1; $j -lt $names.Count; $j++) {
            if (Test-RuntimePathOverlap $paths[$names[$i]] $paths[$names[$j]]) { throw 'Runtime roots must be disjoint and non-nested.' }
        }
    }
    $actualRoot = Get-IsolatedRuntimePath $RepositoryRoot
    if (-not $actualRoot.Equals($paths.aPrimaryRoot, [StringComparison]::OrdinalIgnoreCase)) { throw 'Wrong primary root for Company A.' }
    if (-not [string]::IsNullOrWhiteSpace($WorktreeRoot)) {
        if (-not (Get-IsolatedRuntimePath $WorktreeRoot).Equals($paths.aWorktreeRoot, [StringComparison]::OrdinalIgnoreCase)) { throw 'Wrong Company A worktree/state root.' }
    }
    foreach ($name in @('aPrimaryRoot', 'bPrimaryRoot')) {
        $root = $paths[$name]
        $dotGit = Join-Path $root '.git'
        if (-not (Test-Path -LiteralPath $dotGit -PathType Container)) { throw 'Primary runtimes must be independent full clones, not linked worktrees.' }
        [void](Get-IsolatedRuntimePath $dotGit)
        # Git's absolute output can be misdecoded under Windows Scheduled Task S4U
        # when the user profile path contains non-ASCII characters. The relative
        # result is ASCII for a primary full clone and must be exactly .git.
        $common = @(& git -C $root rev-parse --path-format=relative --git-common-dir)
        if ($LASTEXITCODE -ne 0 -or $common.Count -ne 1) { throw 'Cannot resolve primary Git common directory.' }
        if ($common[0] -cne '.git') { throw 'Shared Git common directory is forbidden.' }
        if (Test-Path -LiteralPath (Join-Path $dotGit 'objects/info/alternates')) { throw 'Shared alternate Git object stores are forbidden.' }
    }
    $branch = @(& git -C $actualRoot branch --show-current)
    if ($LASTEXITCODE -ne 0 -or ($branch -join '') -cne 'main') { throw 'Company A primary must remain on main.' }
    return [pscustomobject]@{ ConfigPath = $configPath; WorktreeRoot = $paths.aWorktreeRoot; LogRoot = $paths.aLogRoot }
}
