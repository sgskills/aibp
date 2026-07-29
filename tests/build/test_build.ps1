[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$buildPath = Join-Path $repoRoot 'tools\build.ps1'

if (-not (Test-Path -LiteralPath $buildPath -PathType Leaf)) {
    throw "RED: build script not implemented: $buildPath"
}

$output = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $buildPath -RepoRoot $repoRoot 2>&1
$exitCode = $LASTEXITCODE
$output | ForEach-Object { Write-Output $_ }
if ($exitCode -ne 0) {
    throw "Build failed with exit code $exitCode."
}

$version = ([System.IO.File]::ReadAllText((Join-Path $repoRoot 'VERSION'), [System.Text.Encoding]::UTF8)).Trim()
$singleZip = Join-Path $repoRoot "dist\sgs-mece-$version.zip"
$bundleZip = Join-Path $repoRoot "dist\ecommerce-skills-$version.zip"
$checksumPath = Join-Path $repoRoot 'dist\SHA256SUMS.txt'

foreach ($requiredPath in @($singleZip, $bundleZip, $checksumPath)) {
    if (-not (Test-Path -LiteralPath $requiredPath -PathType Leaf)) {
        throw "Missing build artifact: $requiredPath"
    }
}

$singleEntries = @(& tar.exe -tf $singleZip)
$bundleEntries = @(& tar.exe -tf $bundleZip)
if ($LASTEXITCODE -ne 0) {
    throw 'Unable to list package contents with tar.exe.'
}

$requiredSingleEntries = @(
    'sgs-mece/SKILL.md',
    'sgs-mece/agents/openai.yaml',
    'sgs-mece/references/frameworks.md',
    'sgs-mece/references/mece-principles.md',
    'sgs-mece/references/questions.md',
    'sgs-mece/LICENSE.txt'
)
foreach ($entry in $requiredSingleEntries) {
    if ($singleEntries -notcontains $entry) {
        throw "Single-skill package is missing: $entry"
    }
}

$requiredBundleEntries = @(
    'LICENSE.txt',
    'sgs-mece/SKILL.md',
    'sgs-mece/agents/openai.yaml'
)
foreach ($entry in $requiredBundleEntries) {
    if ($bundleEntries -notcontains $entry) {
        throw "Bundle package is missing: $entry"
    }
}

$allEntries = @($singleEntries + $bundleEntries)
$forbidden = @($allEntries | Where-Object {
    $_ -match '(^|/)(README|QUICKREF|CHANGELOG)\.md$' -or
    $_ -match '(^|/)(tests|tools|\.github|\.work)/'
})
if ($forbidden.Count -gt 0) {
    throw ('Development files leaked into packages: ' + ($forbidden -join ', '))
}

$checksumLines = @([System.IO.File]::ReadAllLines($checksumPath, [System.Text.Encoding]::UTF8) | Where-Object { $_.Trim() })
if ($checksumLines.Count -ne 2) {
    throw 'SHA256SUMS.txt must contain exactly two package hashes.'
}

Write-Output 'PASS: build produced clean single-skill and full-suite packages with checksums.'

