[CmdletBinding()]
param([string]$RepoRoot)

$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    $RepoRoot = Join-Path $PSScriptRoot '..\..'
}
$repoRoot = (Resolve-Path -LiteralPath $RepoRoot).Path
$buildPath = Join-Path $repoRoot 'tools\build.ps1'
$buildEpoch = [System.DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
$buildEpoch -= ($buildEpoch % 2)

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
$probeCacheFile = Join-Path $probeCacheDirectory ('package-residue-probe-' + [guid]::NewGuid().ToString('N') + '.pyc')
[System.IO.File]::WriteAllBytes($probeCacheFile, [byte[]](0x50, 0x59, 0x43))

try {
    $output = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $buildPath -RepoRoot $repoRoot -SourceDateEpoch $buildEpoch 2>&1
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

function Assert-StandaloneUpdateRuntime {
    param(
        [string]$ZipPath,
        [System.IO.DirectoryInfo]$SkillDir
    )

    $gateRoot = Join-Path $repoRoot ".work\$version\gate-tests"
    $probeRoot = Join-Path $gateRoot ('package-' + [guid]::NewGuid().ToString('N'))
    $scriptsRoot = Join-Path $probeRoot 'standalone\scripts'
    [void][System.IO.Directory]::CreateDirectory($scriptsRoot)
    try {
        $archive = [System.IO.Compression.ZipFile]::OpenRead($ZipPath)
        try {
            foreach ($fileName in @('check-update.ps1', 'check-update.sh', 'update-version.txt')) {
                $entry = $archive.GetEntry("$($SkillDir.Name)/scripts/$fileName")
                if ($null -eq $entry) { throw "Standalone package is missing $fileName." }
                $stream = $entry.Open()
                $destination = [System.IO.File]::Create((Join-Path $scriptsRoot $fileName))
                try { $stream.CopyTo($destination) }
                finally {
                    $destination.Dispose()
                    $stream.Dispose()
                }
            }
        }
        finally { $archive.Dispose() }

        $remoteVersion = '2147483647.2147483647.2147483647'
        $responsePath = Join-Path $probeRoot 'response.txt'
        [System.IO.File]::WriteAllText($responsePath, $remoteVersion + "`n", (New-Object System.Text.UTF8Encoding($false)))
        Push-Location -LiteralPath $probeRoot
        try {
            $output = @(& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $scriptsRoot 'check-update.ps1') -CacheRoot (Join-Path $probeRoot 'cache') -NowSeconds 1800000000 -ResponseFile $responsePath 2>&1)
            $exitCode = $LASTEXITCODE
        }
        finally { Pop-Location }
        if ($exitCode -ne 0) {
            throw "Standalone packaged updater failed for $($SkillDir.Name): $($output -join ' ')"
        }
        if ($version -eq $remoteVersion) {
            if ($output.Count -ne 0) { throw 'An equal version must not emit an update reminder.' }
        }
        elseif ($output.Count -ne 1 -or
            [string]$output[0] -notmatch [regex]::Escape("v$remoteVersion") -or
            [string]$output[0] -notmatch [regex]::Escape("v$version") -or
            [string]$output[0] -notmatch [regex]::Escape('https://github.com/sgskills/aibp')) {
            throw "Standalone packaged updater did not emit exactly one expected source-version reminder: $($output -join ' ')"
        }
        Write-Output "STANDALONE_UPDATE_CHECK PASS: $($SkillDir.Name); only packaged scripts and local response/cache were available."
    }
    finally {
        if (Test-Path -LiteralPath $probeRoot) {
            $allowedPrefix = [System.IO.Path]::GetFullPath($gateRoot).TrimEnd('\') + '\'
            $resolvedProbe = (Resolve-Path -LiteralPath $probeRoot).Path
            if (-not $resolvedProbe.StartsWith($allowedPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
                throw 'Refusing to remove a package fixture outside repository-local gate-tests.'
            }
            Remove-Item -LiteralPath $resolvedProbe -Recurse -Force
        }
    }
}

function Assert-PackagedUpdateContract {
    param(
        [string]$ZipPath,
        [System.IO.DirectoryInfo]$SkillDir
    )

    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive = [System.IO.Compression.ZipFile]::OpenRead($ZipPath)
    try {
        foreach ($relative in @('SKILL.md', 'scripts/check-update.ps1', 'scripts/check-update.sh', 'scripts/update-version.txt')) {
            $entryName = "$($SkillDir.Name)/$relative"
            $entry = $archive.GetEntry($entryName)
            if ($null -eq $entry) {
                throw "Package update-check contract is incomplete: $entryName"
            }
            $entryStream = $entry.Open()
            $content = New-Object System.IO.MemoryStream
            try {
                $entryStream.CopyTo($content)
                if ($relative -eq 'scripts/check-update.sh' -and $content.ToArray() -contains [byte]13) {
                    throw "Packaged POSIX shell script contains CR bytes: $entryName"
                }
                $sourcePath = Join-Path $SkillDir.FullName $relative.Replace('/', '\')
                $expected = [System.Convert]::ToBase64String([System.IO.File]::ReadAllBytes($sourcePath))
                $actual = [System.Convert]::ToBase64String($content.ToArray())
                if ($actual -cne $expected) {
                    throw "Package update-check entry differs from the validated source: $entryName"
                }
            }
            finally {
                $content.Dispose()
                $entryStream.Dispose()
            }
        }
    }
    finally {
        $archive.Dispose()
    }
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
    Assert-PackagedUpdateContract -ZipPath $singleZip -SkillDir $skillDir
    Assert-PackagedUpdateContract -ZipPath $bundlePath -SkillDir $skillDir
    Assert-StandaloneUpdateRuntime -ZipPath $singleZip -SkillDir $skillDir
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

Add-Type -AssemblyName System.IO.Compression.FileSystem
$expectedArchiveTimestamp = [System.DateTimeOffset]::FromUnixTimeSeconds($buildEpoch)
foreach ($zipFile in $zipFiles) {
    $archive = [System.IO.Compression.ZipFile]::OpenRead($zipFile.FullName)
    try {
        foreach ($entry in $archive.Entries) {
            $actual = $entry.LastWriteTime.ToUniversalTime()
            if ([Math]::Abs(($actual - $expectedArchiveTimestamp).TotalSeconds) -gt 2) {
                throw "Archive timestamp mismatch in $($zipFile.Name): $($entry.FullName) has $actual, expected $expectedArchiveTimestamp"
            }
            if ($actual.Year -le 2000) {
                throw "Archive entry still uses a fake legacy timestamp: $($zipFile.Name) / $($entry.FullName) / $actual"
            }
        }
    }
    finally {
        $archive.Dispose()
    }
}

$firstBuildChecksums = @($checksumLines)
$secondBuildOutput = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $buildPath -RepoRoot $repoRoot -SourceDateEpoch $buildEpoch 2>&1
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
