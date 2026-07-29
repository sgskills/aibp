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

if (($output -join "`n") -notmatch 'SELF-TEST PASS') {
    throw 'Validator self-test did not emit the required success marker.'
}

Write-Output 'PASS: validator self-test detects an intentionally invalid fixture.'

