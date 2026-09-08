from pathlib import Path

path = Path('scripts/codex-queue-worker.ps1')
source = path.read_text(encoding='utf-8')

old_params = '''    [string]$DoneLabel = "agent:done",
    [string]$ApprovalRequiredLabel = "agent:approval-required"
)'''
new_params = '''    [string]$DoneLabel = "agent:done",
    [string]$ApprovalRequiredLabel = "agent:approval-required",
    [string]$DefaultCodexModel = "gpt-5.6-terra",
    [string]$ElevatedCodexModel = "gpt-5.6-sol",
    [string]$DefaultClaudeModel = "claude-sonnet-5",
    [string]$ElevatedClaudeModel = "claude-opus-5"
)'''
if source.count(old_params) != 1:
    raise SystemExit('worker parameter marker mismatch')
source = source.replace(old_params, new_params, 1)

marker = '''function Test-HighRiskPathScope {
'''
route_function = '''function Get-AgentModelRoute {
    param(
        [Parameter(Mandatory)][ValidateSet("low", "medium", "high", "critical")][string]$RiskTier,
        [Parameter(Mandatory)][string]$DefaultModel,
        [Parameter(Mandatory)][string]$ElevatedModel
    )

    if ([string]::IsNullOrWhiteSpace($DefaultModel) -or [string]::IsNullOrWhiteSpace($ElevatedModel)) {
        throw "Model routing requires explicit non-empty model identifiers."
    }
    if ($RiskTier -in @("high", "critical")) {
        return $ElevatedModel
    }
    return $DefaultModel
}

'''
if source.count(marker) != 1:
    raise SystemExit('model route insertion marker mismatch')
source = source.replace(marker, route_function + marker, 1)

old_invoke_signature = '''function Invoke-CodexPrompt {
    param(
        [Parameter(Mandatory)][string]$CodexPath,
        [Parameter(Mandatory)][string]$PromptPath,
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][ValidateSet("workspace-write", "read-only")][string]$Sandbox
    )
'''
new_invoke_signature = '''function Invoke-CodexPrompt {
    param(
        [Parameter(Mandatory)][string]$CodexPath,
        [Parameter(Mandatory)][string]$PromptPath,
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][ValidateSet("workspace-write", "read-only")][string]$Sandbox,
        [Parameter(Mandatory)][string]$Model
    )

    if ([string]::IsNullOrWhiteSpace($Model)) {
        throw "Codex model must be explicit and non-empty."
    }
'''
if source.count(old_invoke_signature) != 1:
    raise SystemExit('Invoke-CodexPrompt signature marker mismatch')
source = source.replace(old_invoke_signature, new_invoke_signature, 1)

old_exec = '''            & $CodexPath exec --cd $Path --sandbox $Sandbox - 1> $null 2> $null
'''
new_exec = '''            & $CodexPath exec --model $Model --cd $Path --sandbox $Sandbox - 1> $null 2> $null
'''
if source.count(old_exec) != 1:
    raise SystemExit('Codex exec marker mismatch')
source = source.replace(old_exec, new_exec, 1)

route_marker = '''    $requiresApproval = $riskTier -in @("high", "critical")
    if ((Test-HighRiskPathScope -AllowedPaths $allowedPaths) -and -not $requiresApproval) {
        throw "High-risk path scope requires a high or critical Risk tier."
    }

'''
route_insert = route_marker + '''    $selectedCodexModel = Get-AgentModelRoute -RiskTier $riskTier -DefaultModel $DefaultCodexModel -ElevatedModel $ElevatedCodexModel
    $selectedClaudeModel = Get-AgentModelRoute -RiskTier $riskTier -DefaultModel $DefaultClaudeModel -ElevatedModel $ElevatedClaudeModel
    $claudeFallbackModel = $DefaultClaudeModel

'''
if source.count(route_marker) != 1:
    raise SystemExit('selected model insertion marker mismatch')
source = source.replace(route_marker, route_insert, 1)

replacements = {
    'Invoke-CodexPrompt -CodexPath $codexPath -PromptPath $promptPath -Path $worktreePath -Sandbox "workspace-write"':
        'Invoke-CodexPrompt -CodexPath $codexPath -PromptPath $promptPath -Path $worktreePath -Sandbox "workspace-write" -Model $selectedCodexModel',
    'Invoke-CodexPrompt -CodexPath $codexPath -PromptPath $selfReviewPromptPath -Path $worktreePath -Sandbox "read-only"':
        'Invoke-CodexPrompt -CodexPath $codexPath -PromptPath $selfReviewPromptPath -Path $worktreePath -Sandbox "read-only" -Model $selectedCodexModel',
    'Invoke-CodexPrompt -CodexPath $codexPath -PromptPath $reviewResolutionPromptPath -Path $worktreePath -Sandbox "workspace-write"':
        'Invoke-CodexPrompt -CodexPath $codexPath -PromptPath $reviewResolutionPromptPath -Path $worktreePath -Sandbox "workspace-write" -Model $selectedCodexModel',
}
for old, new in replacements.items():
    count = source.count(old)
    if old.endswith('$selfReviewPromptPath -Path $worktreePath -Sandbox "read-only"'):
        if count != 2:
            raise SystemExit(f'self-review invocation count was {count}, expected 2')
        source = source.replace(old, new)
    else:
        if count != 1:
            raise SystemExit(f'invocation marker count was {count}, expected 1: {old}')
        source = source.replace(old, new, 1)

old_initial_review = '''        & powershell -NoProfile -ExecutionPolicy Bypass -File $reviewScript -WorktreePath $worktreePath -TestResultPath $testResultPath -ReviewOutputPath $reviewResultPath -BaseBranch $BaseBranch -Round initial
'''
new_initial_review = '''        & powershell -NoProfile -ExecutionPolicy Bypass -File $reviewScript -WorktreePath $worktreePath -TestResultPath $testResultPath -ReviewOutputPath $reviewResultPath -BaseBranch $BaseBranch -Round initial -PreferredModel $selectedClaudeModel -FallbackModel $claudeFallbackModel
'''
if source.count(old_initial_review) != 1:
    raise SystemExit('initial Claude invocation marker mismatch')
source = source.replace(old_initial_review, new_initial_review, 1)

old_final_review = '''            & powershell -NoProfile -ExecutionPolicy Bypass -File $reviewScript -WorktreePath $worktreePath -TestResultPath $testResultPath -ReviewOutputPath $finalReviewResultPath -BaseBranch $BaseBranch -Round final
'''
new_final_review = '''            & powershell -NoProfile -ExecutionPolicy Bypass -File $reviewScript -WorktreePath $worktreePath -TestResultPath $testResultPath -ReviewOutputPath $finalReviewResultPath -BaseBranch $BaseBranch -Round final -PreferredModel $selectedClaudeModel -FallbackModel $claudeFallbackModel
'''
if source.count(old_final_review) != 1:
    raise SystemExit('final Claude invocation marker mismatch')
source = source.replace(old_final_review, new_final_review, 1)

pr_marker = '''- Test result: PASSED
- Review report: $([System.IO.Path]::GetFileName($reviewResultPath))
'''
pr_replace = '''- Test result: PASSED
- Codex model route: $selectedCodexModel
- Claude review model route: $selectedClaudeModel
- Claude fallback model: $claudeFallbackModel
- Review report: $([System.IO.Path]::GetFileName($reviewResultPath))
'''
if source.count(pr_marker) != 1:
    raise SystemExit('PR model metadata marker mismatch')
source = source.replace(pr_marker, pr_replace, 1)

path.write_text(source, encoding='utf-8', newline='\n')
print('model routing worker patch applied')
