from pathlib import Path

path = Path('scripts/recover-codex-zero-change.ps1')
source = path.read_text(encoding='utf-8')

old_params = '''    [string]$RunningLabel = "agent:running",
    [string]$BlockedLabel = "agent:blocked",
    [switch]$SelfTest
)'''
new_params = '''    [string]$RunningLabel = "agent:running",
    [string]$BlockedLabel = "agent:blocked",
    [string]$RecoveryCodexModel = "gpt-5.6-sol",
    [switch]$SelfTest
)'''
if source.count(old_params) != 1:
    raise SystemExit('recovery parameter marker mismatch')
source = source.replace(old_params, new_params, 1)

old_signature = '''function Invoke-CodexReadOnlyEditPlan {
    param([string]$CodexPath, [string]$PromptPath, [string]$WorktreePath, [string]$OutputPath)
'''
new_signature = '''function Invoke-CodexReadOnlyEditPlan {
    param([string]$CodexPath, [string]$PromptPath, [string]$WorktreePath, [string]$OutputPath, [string]$Model)

    if ([string]::IsNullOrWhiteSpace($Model)) { throw 'Recovery Codex model must be explicit and non-empty.' }
'''
if source.count(old_signature) != 1:
    raise SystemExit('recovery invocation signature marker mismatch')
source = source.replace(old_signature, new_signature, 1)

old_exec = '''            & $CodexPath exec --cd $WorktreePath --sandbox read-only --output-last-message $OutputPath - 1> $null 2> $null
'''
new_exec = '''            & $CodexPath exec --model $Model --cd $WorktreePath --sandbox read-only --output-last-message $OutputPath - 1> $null 2> $null
'''
if source.count(old_exec) != 1:
    raise SystemExit('recovery Codex exec marker mismatch')
source = source.replace(old_exec, new_exec, 1)

old_call = '''    Invoke-CodexReadOnlyEditPlan -CodexPath $codexPath -PromptPath $promptPath -WorktreePath $worktreePath -OutputPath $outputPath
'''
new_call = '''    Invoke-CodexReadOnlyEditPlan -CodexPath $codexPath -PromptPath $promptPath -WorktreePath $worktreePath -OutputPath $outputPath -Model $RecoveryCodexModel
'''
if source.count(old_call) != 1:
    raise SystemExit('recovery Codex call marker mismatch')
source = source.replace(old_call, new_call, 1)

selftest_marker = '''    if (-not $rejected) { throw 'Unsafe path regression was not rejected.' }

    Write-Output 'Zero-change edit-plan recovery self-test passed.'
'''
selftest_replace = '''    if (-not $rejected) { throw 'Unsafe path regression was not rejected.' }
    if ($RecoveryCodexModel -ne 'gpt-5.6-sol') { throw 'Recovery model routing regression failed.' }

    Write-Output 'Zero-change edit-plan recovery self-test passed.'
'''
if source.count(selftest_marker) != 1:
    raise SystemExit('recovery self-test marker mismatch')
source = source.replace(selftest_marker, selftest_replace, 1)

path.write_text(source, encoding='utf-8', newline='\n')
print('explicit recovery model patch applied')
