[CmdletBinding()]
param(
    [string]$RepoRoot
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    $RepoRoot = Split-Path -Parent $PSScriptRoot
}

function Copy-RuntimeSkill {
    param(
        [string]$SourceSkill,
        [string]$DestinationRoot,
        [string]$LicensePath,
        [switch]$IncludeLicense
    )

    $skillName = Split-Path -Leaf $SourceSkill
    $destinationSkill = Join-Path $DestinationRoot $skillName
    New-Item -ItemType Directory -Path $destinationSkill -Force | Out-Null

    Copy-Item -LiteralPath (Join-Path $SourceSkill 'SKILL.md') -Destination $destinationSkill
    foreach ($directoryName in @('agents', 'references', 'scripts', 'assets')) {
        $sourceDirectory = Join-Path $SourceSkill $directoryName
        if (Test-Path -LiteralPath $sourceDirectory -PathType Container) {
            Copy-Item -LiteralPath $sourceDirectory -Destination $destinationSkill -Recurse
        }
    }

    if ($IncludeLicense) {
        Copy-Item -LiteralPath $LicensePath -Destination (Join-Path $destinationSkill 'LICENSE.txt')
    }
}

$resolvedRoot = (Resolve-Path -LiteralPath $RepoRoot).Path
$validatorPath = Join-Path $resolvedRoot 'tools\validate.ps1'
$versionPath = Join-Path $resolvedRoot 'VERSION'
$licensePath = Join-Path $resolvedRoot 'LICENSE'
$skillsRoot = Join-Path $resolvedRoot 'skills'
$distPath = Join-Path $resolvedRoot 'dist'

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $validatorPath -RepoRoot $resolvedRoot
if ($LASTEXITCODE -ne 0) {
    throw 'Repository validation failed; build stopped.'
}

$version = ([System.IO.File]::ReadAllText($versionPath, [System.Text.Encoding]::UTF8)).Trim()
$skillDirs = @(Get-ChildItem -LiteralPath $skillsRoot -Directory | Sort-Object Name)
if ($skillDirs.Count -eq 0) {
    throw 'No skill directories were found.'
}

$expectedDistPath = [System.IO.Path]::GetFullPath((Join-Path $resolvedRoot 'dist'))
if ([System.IO.Path]::GetFullPath($distPath) -ne $expectedDistPath) {
    throw 'Resolved dist path is outside the repository.'
}
if (Test-Path -LiteralPath $distPath) {
    Remove-Item -LiteralPath $distPath -Recurse -Force
}
New-Item -ItemType Directory -Path $distPath -Force | Out-Null

$stagingRoot = Join-Path ([System.IO.Path]::GetTempPath()) ('sgskills-build-' + [guid]::NewGuid().ToString('N'))
try {
    $bundleStage = Join-Path $stagingRoot 'bundle'
    New-Item -ItemType Directory -Path $bundleStage -Force | Out-Null
    Copy-Item -LiteralPath $licensePath -Destination (Join-Path $bundleStage 'LICENSE.txt')

    foreach ($skillDir in $skillDirs) {
        Copy-RuntimeSkill -SourceSkill $skillDir.FullName -DestinationRoot $bundleStage -LicensePath $licensePath

        $singleStage = Join-Path $stagingRoot ("single-" + $skillDir.Name)
        New-Item -ItemType Directory -Path $singleStage -Force | Out-Null
        Copy-RuntimeSkill -SourceSkill $skillDir.FullName -DestinationRoot $singleStage -LicensePath $licensePath -IncludeLicense

        $singleZip = Join-Path $distPath ("{0}-{1}.zip" -f $skillDir.Name, $version)
        Compress-Archive -Path (Join-Path $singleStage $skillDir.Name) -DestinationPath $singleZip -CompressionLevel Optimal
    }

    $bundleZip = Join-Path $distPath ("ecommerce-skills-{0}.zip" -f $version)
    Compress-Archive -Path (Join-Path $bundleStage '*') -DestinationPath $bundleZip -CompressionLevel Optimal

    $zipFiles = @(Get-ChildItem -LiteralPath $distPath -Filter '*.zip' -File | Sort-Object Name)
    $checksumLines = foreach ($zipFile in $zipFiles) {
        $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $zipFile.FullName).Hash
        '{0}  {1}' -f $hash, $zipFile.Name
    }
    $checksumPath = Join-Path $distPath 'SHA256SUMS.txt'
    [System.IO.File]::WriteAllLines(
        $checksumPath,
        [string[]]$checksumLines,
        (New-Object System.Text.UTF8Encoding($false))
    )
}
finally {
    if (Test-Path -LiteralPath $stagingRoot) {
        $tempRoot = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
        $resolvedStaging = [System.IO.Path]::GetFullPath($stagingRoot)
        if (-not $resolvedStaging.StartsWith($tempRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw 'Refusing to remove a staging directory outside the system temp path.'
        }
        Remove-Item -LiteralPath $stagingRoot -Recurse -Force
    }
}

Write-Output "BUILD PASS: created $($skillDirs.Count) individual package(s), one suite package, and SHA256SUMS.txt."
