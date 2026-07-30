[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$validatorPath = Join-Path $repoRoot 'tools\validate.ps1'

if (-not (Test-Path -LiteralPath $validatorPath -PathType Leaf)) {
    throw "RED: validator not implemented: $validatorPath"
}

$output = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $validatorPath -RepoRoot $repoRoot -SelfTest 2>&1
$exitCode = $LASTEXITCODE
$output | ForEach-Object { Write-Output $_ }
if ($exitCode -ne 0) {
    throw "Validator self-test failed with exit code $exitCode."
}

$joined = $output -join "`n"
foreach ($marker in @(
    'FIFTH_SKILL_GREEN PASS',
    'EXPECTED RED: missing SKILL.md',
    'EXPECTED RED: nested Skill directory',
    'EXPECTED RED: bad frontmatter',
    'SELF-TEST PASS'
)) {
    if ($joined -notmatch [regex]::Escape($marker)) {
        throw "Validator self-test did not emit marker: $marker"
    }
}

Write-Output 'PASS: validator proved dynamic fifth-Skill expansion and all required red fixtures.'
