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
$expectedVersion = '2.0.0'
if ($version -ne $expectedVersion) {
    throw "VERSION must be $expectedVersion for the dual-skill release; found $version."
}

$meceZip = Join-Path $repoRoot "dist\sg-mece-$version.zip"
$ceoVisionZip = Join-Path $repoRoot "dist\sg-ceo-vision-$version.zip"
$bundleZip = Join-Path $repoRoot "dist\ecommerce-skills-$version.zip"
$checksumPath = Join-Path $repoRoot 'dist\SHA256SUMS.txt'

foreach ($requiredPath in @($meceZip, $ceoVisionZip, $bundleZip, $checksumPath)) {
    if (-not (Test-Path -LiteralPath $requiredPath -PathType Leaf)) {
        throw "Missing build artifact: $requiredPath"
    }
}

$meceEntries = @(& tar.exe -tf $meceZip)
$ceoVisionEntries = @(& tar.exe -tf $ceoVisionZip)
$bundleEntries = @(& tar.exe -tf $bundleZip)
if ($LASTEXITCODE -ne 0) {
    throw 'Unable to list package contents with tar.exe.'
}

$requiredMeceEntries = @(
    'sg-mece/SKILL.md',
    'sg-mece/agents/openai.yaml',
    'sg-mece/references/frameworks.md',
    'sg-mece/references/mece-principles.md',
    'sg-mece/references/questions.md',
    'sg-mece/LICENSE.txt'
)
foreach ($entry in $requiredMeceEntries) {
    if ($meceEntries -notcontains $entry) {
        throw "sg-mece package is missing: $entry"
    }
}

$requiredCeoVisionEntries = @(
    'sg-ceo-vision/SKILL.md',
    'sg-ceo-vision/agents/openai.yaml',
    'sg-ceo-vision/references/evidence-and-opportunity-rubric.md',
    'sg-ceo-vision/references/report-content-schema.md',
    'sg-ceo-vision/assets/ceo-vision-report-template.html',
    'sg-ceo-vision/LICENSE.txt'
)
foreach ($entry in $requiredCeoVisionEntries) {
    if ($ceoVisionEntries -notcontains $entry) {
        throw "sg-ceo-vision package is missing: $entry"
    }
}

$requiredBundleEntries = @(
    'LICENSE.txt',
    'sg-mece/SKILL.md',
    'sg-mece/agents/openai.yaml',
    'sg-ceo-vision/SKILL.md',
    'sg-ceo-vision/agents/openai.yaml'
)
foreach ($entry in $requiredBundleEntries) {
    if ($bundleEntries -notcontains $entry) {
        throw "Bundle package is missing: $entry"
    }
}

$allEntries = @($meceEntries + $ceoVisionEntries + $bundleEntries)
$forbidden = @($allEntries | Where-Object {
    $_ -match '(^|/)(README|QUICKREF|CHANGELOG)\.md$' -or
    $_ -match '(^|/)(tests|tools|\.github|\.work)/'
})
if ($forbidden.Count -gt 0) {
    throw ('Development files leaked into packages: ' + ($forbidden -join ', '))
}

$legacyPrefix = 'sg' + 's-'
$legacyEntries = @($allEntries | Where-Object { $_.Contains($legacyPrefix) })
if ($legacyEntries.Count -gt 0) {
    throw ('Legacy skill prefix leaked into packages: ' + ($legacyEntries -join ', '))
}

$checksumLines = @([System.IO.File]::ReadAllLines($checksumPath, [System.Text.Encoding]::UTF8) | Where-Object { $_.Trim() })
if ($checksumLines.Count -ne 3) {
    throw 'SHA256SUMS.txt must contain exactly three package hashes.'
}

Write-Output 'PASS: build produced clean single-skill and full-suite packages with checksums.'
