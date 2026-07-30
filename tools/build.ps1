[CmdletBinding()]
param(
    [string]$RepoRoot
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression

if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    $RepoRoot = Split-Path -Parent $PSScriptRoot
}

function Remove-PackageResidue {
    param([string]$Root)

    Get-ChildItem -LiteralPath $Root -Directory -Filter '__pycache__' -Recurse -Force |
        Sort-Object FullName -Descending |
        ForEach-Object { Remove-Item -LiteralPath $_.FullName -Recurse -Force }

    Get-ChildItem -LiteralPath $Root -File -Recurse -Force |
        Where-Object { $_.Extension -in @('.pyc', '.pyo', '.tmp', '.bak') } |
        ForEach-Object { Remove-Item -LiteralPath $_.FullName -Force }
}

function New-DeterministicZip {
    param(
        [string]$SourceRoot,
        [string]$DestinationPath
    )

    $resolvedSource = (Resolve-Path -LiteralPath $SourceRoot).Path
    $sourcePrefix = $resolvedSource.TrimEnd(
        [System.IO.Path]::DirectorySeparatorChar,
        [System.IO.Path]::AltDirectorySeparatorChar
    ) + [System.IO.Path]::DirectorySeparatorChar
    $fixedTimestamp = New-Object System.DateTimeOffset 2000, 1, 1, 0, 0, 0, ([System.TimeSpan]::Zero)
    $files = @(
        Get-ChildItem -LiteralPath $resolvedSource -Recurse -File |
            ForEach-Object {
                if (-not $_.FullName.StartsWith($sourcePrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
                    throw "Refusing to archive a file outside the source root: $($_.FullName)"
                }
                [pscustomobject]@{
                    FullName = $_.FullName
                    EntryName = $_.FullName.Substring($sourcePrefix.Length).Replace('\', '/')
                }
            } |
            Sort-Object EntryName
    )
    if ($files.Count -eq 0) {
        throw "Refusing to create an empty package: $DestinationPath"
    }

    $outputStream = [System.IO.File]::Open(
        $DestinationPath,
        [System.IO.FileMode]::CreateNew,
        [System.IO.FileAccess]::Write,
        [System.IO.FileShare]::None
    )
    $archive = $null
    try {
        $archive = New-Object System.IO.Compression.ZipArchive (
            $outputStream,
            [System.IO.Compression.ZipArchiveMode]::Create,
            $true
        )
        foreach ($file in $files) {
            # Stored entries avoid runtime-specific compression differences.
            # Fixed order and timestamps make identical source trees byte-identical.
            $entry = $archive.CreateEntry(
                $file.EntryName,
                [System.IO.Compression.CompressionLevel]::NoCompression
            )
            $entry.LastWriteTime = $fixedTimestamp
            $entry.ExternalAttributes = 0

            $inputStream = [System.IO.File]::Open(
                $file.FullName,
                [System.IO.FileMode]::Open,
                [System.IO.FileAccess]::Read,
                [System.IO.FileShare]::Read
            )
            $entryStream = $null
            try {
                $entryStream = $entry.Open()
                $inputStream.CopyTo($entryStream)
            }
            finally {
                if ($null -ne $entryStream) {
                    $entryStream.Dispose()
                }
                $inputStream.Dispose()
            }
        }
    }
    finally {
        if ($null -ne $archive) {
            $archive.Dispose()
        }
        $outputStream.Dispose()
    }
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
    [void][System.IO.Directory]::CreateDirectory($destinationSkill)

    Copy-Item -LiteralPath (Join-Path $SourceSkill 'SKILL.md') -Destination $destinationSkill
    foreach ($directoryName in @('agents', 'references', 'scripts', 'assets')) {
        $sourceDirectory = Join-Path $SourceSkill $directoryName
        if (Test-Path -LiteralPath $sourceDirectory -PathType Container) {
            Copy-Item -LiteralPath $sourceDirectory -Destination $destinationSkill -Recurse
        }
    }

    $evalRunner = Join-Path $SourceSkill 'scripts\run_eval.py'
    $fixtureSource = Join-Path $SourceSkill 'tests\fixtures'
    if (Test-Path -LiteralPath $evalRunner -PathType Leaf) {
        if (-not (Test-Path -LiteralPath $fixtureSource -PathType Container)) {
            throw "Eval runner has no fixtures: $SourceSkill"
        }
        $testsDestination = Join-Path $destinationSkill 'tests'
        [void][System.IO.Directory]::CreateDirectory($testsDestination)
        Copy-Item -LiteralPath $fixtureSource -Destination $testsDestination -Recurse
    }

    if ($IncludeLicense) {
        Copy-Item -LiteralPath $LicensePath -Destination (Join-Path $destinationSkill 'LICENSE.txt')
    }

    # Runtime imports may create caches in the source tree. Packages must remain
    # reproducible and never inherit those machine-local development artifacts.
    Remove-PackageResidue -Root $destinationSkill
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
$skillDirs = @(
    Get-ChildItem -LiteralPath $skillsRoot -Directory |
        Where-Object {
            Test-Path -LiteralPath (Join-Path $_.FullName 'SKILL.md') -PathType Leaf
        } |
        Sort-Object Name
)
if ($skillDirs.Count -eq 0) {
    throw 'No skills/*/SKILL.md entries were found.'
}

$expectedDistPath = [System.IO.Path]::GetFullPath((Join-Path $resolvedRoot 'dist'))
if ([System.IO.Path]::GetFullPath($distPath) -ne $expectedDistPath) {
    throw 'Resolved dist path is outside the repository.'
}
if (Test-Path -LiteralPath $distPath) {
    Remove-Item -LiteralPath $distPath -Recurse -Force
}
[void][System.IO.Directory]::CreateDirectory($distPath)

$stagingRoot = Join-Path ([System.IO.Path]::GetTempPath()) ('aibp-build-' + [guid]::NewGuid().ToString('N'))
try {
    $bundleStage = Join-Path $stagingRoot 'bundle'
    [void][System.IO.Directory]::CreateDirectory($bundleStage)
    Copy-Item -LiteralPath $licensePath -Destination (Join-Path $bundleStage 'LICENSE.txt')

    foreach ($skillDir in $skillDirs) {
        Copy-RuntimeSkill -SourceSkill $skillDir.FullName -DestinationRoot $bundleStage -LicensePath $licensePath

        $singleStage = Join-Path $stagingRoot ("single-" + $skillDir.Name)
        [void][System.IO.Directory]::CreateDirectory($singleStage)
        Copy-RuntimeSkill -SourceSkill $skillDir.FullName -DestinationRoot $singleStage -LicensePath $licensePath -IncludeLicense

        $singleZip = Join-Path $distPath ("{0}-{1}.zip" -f $skillDir.Name, $version)
        New-DeterministicZip -SourceRoot $singleStage -DestinationPath $singleZip
    }

    $bundleZip = Join-Path $distPath ("aibp-{0}.zip" -f $version)
    New-DeterministicZip -SourceRoot $bundleStage -DestinationPath $bundleZip

    $zipFiles = @(Get-ChildItem -LiteralPath $distPath -Filter '*.zip' -File | Sort-Object Name)
    $checksumLines = foreach ($zipFile in $zipFiles) {
        $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $zipFile.FullName).Hash
        '{0}  {1}' -f $hash, $zipFile.Name
    }
    [System.IO.File]::WriteAllLines(
        (Join-Path $distPath 'SHA256SUMS.txt'),
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

Write-Output "BUILD PASS: created $($skillDirs.Count) individual package(s), one AIBP package, and SHA256SUMS.txt."
