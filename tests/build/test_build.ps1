[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$buildPath = Join-Path $repoRoot 'tools\build.ps1'

if (-not (Test-Path -LiteralPath $buildPath -PathType Leaf)) {
    throw "RED: build script not implemented: $buildPath"
}

$probeScriptsDirectory = @(
    Get-ChildItem -LiteralPath (Join-Path $repoRoot 'skills') -Directory |
        ForEach-Object { Join-Path $_.FullName 'scripts' } |
        Where-Object { Test-Path -LiteralPath $_ -PathType Container } |
        Select-Object -First 1
)
if ($probeScriptsDirectory.Count -eq 0) {
    throw 'No Skill scripts directory is available for the package-residue regression probe.'
}
$probeCacheDirectory = Join-Path $probeScriptsDirectory[0] '__pycache__'
$probeCacheDirectoryExisted = Test-Path -LiteralPath $probeCacheDirectory -PathType Container
[void][System.IO.Directory]::CreateDirectory($probeCacheDirectory)
$probeCacheFile = Join-Path $probeCacheDirectory 'package-residue-probe.pyc'
[System.IO.File]::WriteAllBytes($probeCacheFile, [byte[]](0x50, 0x59, 0x43))

try {
    $output = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $buildPath -RepoRoot $repoRoot 2>&1
    $exitCode = $LASTEXITCODE
    $output | ForEach-Object { Write-Output $_ }
    if ($exitCode -ne 0) {
        throw "Build failed with exit code $exitCode."
    }
}
finally {
    if (Test-Path -LiteralPath $probeCacheFile -PathType Leaf) {
        Remove-Item -LiteralPath $probeCacheFile -Force
    }
    if (-not $probeCacheDirectoryExisted -and
        (Test-Path -LiteralPath $probeCacheDirectory -PathType Container) -and
        @(Get-ChildItem -LiteralPath $probeCacheDirectory -Force).Count -eq 0) {
        Remove-Item -LiteralPath $probeCacheDirectory -Force
    }
}

$version = ([System.IO.File]::ReadAllText((Join-Path $repoRoot 'VERSION'), [System.Text.Encoding]::UTF8)).Trim()
if ($version -notmatch '^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$') {
    throw "VERSION is not valid semantic version text: $version"
}

$skillDirs = @(
    Get-ChildItem -LiteralPath (Join-Path $repoRoot 'skills') -Directory |
        Where-Object {
            Test-Path -LiteralPath (Join-Path $_.FullName 'SKILL.md') -PathType Leaf
        } |
        Sort-Object Name
)
if ($skillDirs.Count -eq 0) {
    throw 'No skills/*/SKILL.md entries were discovered.'
}

function Get-ZipFileEntries {
    param([string]$ZipPath)

    $entries = @(& tar.exe -tf $ZipPath)
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to list package contents: $ZipPath"
    }
    return @(
        $entries |
            ForEach-Object { $_.Replace('\', '/') } |
            Where-Object { $_ -and -not $_.EndsWith('/') }
    )
}

function Get-ExpectedSkillEntries {
    param([System.IO.DirectoryInfo]$SkillDir)

    $entries = New-Object 'System.Collections.Generic.List[string]'
    [void]$entries.Add("$($SkillDir.Name)/SKILL.md")
    foreach ($directoryName in @('agents', 'references', 'scripts', 'assets')) {
        $sourceDirectory = Join-Path $SkillDir.FullName $directoryName
        if (Test-Path -LiteralPath $sourceDirectory -PathType Container) {
            foreach ($file in Get-ChildItem -LiteralPath $sourceDirectory -Recurse -File) {
                $relative = $file.FullName.Substring($SkillDir.FullName.Length + 1).Replace('\', '/')
                if ($relative -notmatch '(^|/)__pycache__(/|$)' -and
                    $relative -notmatch '\.(pyc|pyo|tmp|bak)$') {
                    [void]$entries.Add("$($SkillDir.Name)/$relative")
                }
            }
        }
    }

    $runnerPath = Join-Path $SkillDir.FullName 'scripts\run_eval.py'
    if (Test-Path -LiteralPath $runnerPath -PathType Leaf) {
        $fixtureRoot = Join-Path $SkillDir.FullName 'tests\fixtures'
        foreach ($file in Get-ChildItem -LiteralPath $fixtureRoot -Recurse -File) {
            $relative = $file.FullName.Substring($SkillDir.FullName.Length + 1).Replace('\', '/')
            [void]$entries.Add("$($SkillDir.Name)/$relative")
        }
    }
    return @($entries | Sort-Object -Unique)
}

$distPath = Join-Path $repoRoot 'dist'
$bundlePath = Join-Path $distPath "aibp-$version.zip"
$checksumPath = Join-Path $distPath 'SHA256SUMS.txt'
foreach ($requiredPath in @($bundlePath, $checksumPath)) {
    if (-not (Test-Path -LiteralPath $requiredPath -PathType Leaf)) {
        throw "Missing build artifact: $requiredPath"
    }
}

$allEntries = New-Object 'System.Collections.Generic.List[string]'
$expectedBundleEntries = New-Object 'System.Collections.Generic.List[string]'
[void]$expectedBundleEntries.Add('LICENSE.txt')
foreach ($skillDir in $skillDirs) {
    $singleZip = Join-Path $distPath "$($skillDir.Name)-$version.zip"
    if (-not (Test-Path -LiteralPath $singleZip -PathType Leaf)) {
        throw "Missing single-Skill package: $singleZip"
    }

    $expectedRuntimeEntries = @(Get-ExpectedSkillEntries -SkillDir $skillDir)
    $expectedSingleEntries = @($expectedRuntimeEntries + "$($skillDir.Name)/LICENSE.txt" | Sort-Object -Unique)
    $singleEntries = @(Get-ZipFileEntries -ZipPath $singleZip | Sort-Object -Unique)
    if (($singleEntries -join "`n") -ne ($expectedSingleEntries -join "`n")) {
        $missing = @($expectedSingleEntries | Where-Object { $singleEntries -notcontains $_ })
        $extra = @($singleEntries | Where-Object { $expectedSingleEntries -notcontains $_ })
        throw "Package content mismatch for $($skillDir.Name). Missing: $($missing -join ', '); Extra: $($extra -join ', ')"
    }
    foreach ($entry in $singleEntries) {
        [void]$allEntries.Add($entry)
    }
    foreach ($entry in $expectedRuntimeEntries) {
        [void]$expectedBundleEntries.Add($entry)
    }

    $runnerPath = Join-Path $skillDir.FullName 'scripts\run_eval.py'
    if (Test-Path -LiteralPath $runnerPath -PathType Leaf) {
        $fixtureEntries = @($singleEntries | Where-Object { $_ -match '/tests/fixtures/.+/case\.json$' })
        if ($fixtureEntries.Count -eq 0) {
            throw "Eval runner package lacks Golden fixtures: $($skillDir.Name)"
        }
    }
}

$bundleEntries = @(Get-ZipFileEntries -ZipPath $bundlePath | Sort-Object -Unique)
$expectedBundle = @($expectedBundleEntries | Sort-Object -Unique)
if (($bundleEntries -join "`n") -ne ($expectedBundle -join "`n")) {
    $missing = @($expectedBundle | Where-Object { $bundleEntries -notcontains $_ })
    $extra = @($bundleEntries | Where-Object { $expectedBundle -notcontains $_ })
    throw "AIBP package content mismatch. Missing: $($missing -join ', '); Extra: $($extra -join ', ')"
}
foreach ($entry in $bundleEntries) {
    [void]$allEntries.Add($entry)
}

$forbidden = @(
    $allEntries |
        Where-Object {
            $_ -match '(^|/)(README|QUICKREF|CHANGELOG|SKILL\.patch)\.md$' -or
            $_ -match '(^|/)(tools|\.github|\.work|\.git)/' -or
            $_ -match '(^|/)__pycache__(/|$)' -or
            $_ -match '\.(pyc|pyo|tmp|bak)$' -or
            $_ -match '/tests/test_.*\.py$' -or
            $_ -match '/(agents|assets|references|scripts|tests)/\1/'
        }
)
if ($forbidden.Count -gt 0) {
    throw "Development residue or duplicate nesting leaked into packages: $($forbidden -join ', ')"
}

$zipFiles = @(Get-ChildItem -LiteralPath $distPath -Filter '*.zip' -File | Sort-Object Name)
if ($zipFiles.Count -ne ($skillDirs.Count + 1)) {
    throw "Expected one package per Skill plus one AIBP package; found $($zipFiles.Count)."
}
$checksumLines = @(
    [System.IO.File]::ReadAllLines($checksumPath, [System.Text.Encoding]::UTF8) |
        Where-Object { $_.Trim() }
)
if ($checksumLines.Count -ne $zipFiles.Count) {
    throw "SHA256SUMS count $($checksumLines.Count) does not match package count $($zipFiles.Count)."
}
foreach ($zipFile in $zipFiles) {
    $expectedLine = '{0}  {1}' -f (Get-FileHash -Algorithm SHA256 -LiteralPath $zipFile.FullName).Hash, $zipFile.Name
    if ($checksumLines -notcontains $expectedLine) {
        throw "Missing or incorrect SHA256 line for $($zipFile.Name)."
    }
}

$firstBuildChecksums = @($checksumLines)
$secondBuildOutput = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $buildPath -RepoRoot $repoRoot 2>&1
$secondBuildExitCode = $LASTEXITCODE
$secondBuildOutput | ForEach-Object { Write-Output $_ }
if ($secondBuildExitCode -ne 0) {
    throw "Second reproducibility build failed with exit code $secondBuildExitCode."
}
$secondBuildChecksums = @(
    [System.IO.File]::ReadAllLines($checksumPath, [System.Text.Encoding]::UTF8) |
        Where-Object { $_.Trim() }
)
if (($firstBuildChecksums -join "`n") -ne ($secondBuildChecksums -join "`n")) {
    $difference = Compare-Object -ReferenceObject $firstBuildChecksums -DifferenceObject $secondBuildChecksums
    throw "Consecutive builds are not byte-reproducible: $($difference | Out-String)"
}

Write-Output "PASS: dynamically inspected $($skillDirs.Count) single packages, one AIBP package, and $($checksumLines.Count) reproducible SHA256 hashes."
