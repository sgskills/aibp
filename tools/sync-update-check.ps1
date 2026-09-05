[CmdletBinding()]
param([string]$RepoRoot)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    $RepoRoot = Split-Path -Parent $PSScriptRoot
}
$resolvedRoot = (Resolve-Path -LiteralPath $RepoRoot).Path
$skillsRoot = Join-Path $resolvedRoot 'skills'
$templateRoot = Join-Path $resolvedRoot 'tools\update-check'
$version = [System.IO.File]::ReadAllText((Join-Path $resolvedRoot 'VERSION'), [System.Text.Encoding]::UTF8).Trim()
if ($version -notmatch '^(0|[1-9][0-9]{0,9})\.(0|[1-9][0-9]{0,9})\.(0|[1-9][0-9]{0,9})$' -or
    @($version.Split('.') | Where-Object { [long]$_ -gt 2147483647 }).Count -gt 0) {
    throw 'Update checks require a stable X.Y.Z VERSION with components <= 2147483647.'
}
$startMarker = '<!-- AIBP-UPDATE-CHECK:START -->'
$endMarker = '<!-- AIBP-UPDATE-CHECK:END -->'
$entryTemplate = [System.IO.File]::ReadAllText((Join-Path $templateRoot 'skill-entry.md'), [System.Text.Encoding]::UTF8)
$entryTemplate = $entryTemplate.Replace("`r`n", "`n").TrimEnd("`r", "`n")
if (-not $entryTemplate.StartsWith($startMarker) -or -not $entryTemplate.EndsWith($endMarker)) {
    throw 'The update entry template has invalid boundary markers.'
}
$runtimeFiles = @('check-update.ps1', 'check-update.sh')
foreach ($runtimeFile in $runtimeFiles) {
    if (-not (Test-Path -LiteralPath (Join-Path $templateRoot $runtimeFile) -PathType Leaf)) {
        throw "Missing update runtime template: $runtimeFile"
    }
}

function Assert-NotLink {
    param([string]$Path)
    if (Test-Path -LiteralPath $Path) {
        if (((Get-Item -LiteralPath $Path -Force).Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "Refusing to write through a link: $Path"
        }
    }
}

function Set-ManagedBytes {
    param([string]$Path, [byte[]]$Bytes)
    Assert-NotLink -Path $Path
    if (Test-Path -LiteralPath $Path -PathType Leaf) {
        $currentBytes = [System.IO.File]::ReadAllBytes($Path)
        if ([Convert]::ToBase64String($currentBytes) -eq [Convert]::ToBase64String($Bytes)) {
            return
        }
    }
    [System.IO.File]::WriteAllBytes($Path, $Bytes)
}

function Get-EntryInsertionIndex {
    param([string]$Content)
    $fenceCharacter = ''
    $fenceLength = 0
    $firstSection = -1
    foreach ($line in [regex]::Matches($Content, '(?m)^.*(?:\n|$)')) {
        $text = $line.Value.TrimEnd("`r", "`n")
        if ($fenceCharacter) {
            $closing = '^[ ]{0,3}' + [regex]::Escape($fenceCharacter) + '{' + $fenceLength + ',}[ \t]*$'
            if ($text -match $closing) { $fenceCharacter = '' }
            continue
        }
        $opening = [regex]::Match($text, '^[ ]{0,3}(`{3,}|~{3,})')
        if ($opening.Success) {
            $fenceCharacter = $opening.Groups[1].Value.Substring(0, 1)
            $fenceLength = $opening.Groups[1].Value.Length
            continue
        }
        if ($firstSection -lt 0 -and $text -match '^## ') { $firstSection = $line.Index }
    }
    if ($fenceCharacter) { throw 'Unclosed code fence in SKILL.md; inspect it before syncing.' }
    return $firstSection
}

Assert-NotLink -Path $resolvedRoot
Assert-NotLink -Path $skillsRoot
$skillDirs = @(
    Get-ChildItem -LiteralPath $skillsRoot -Directory |
        Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName 'SKILL.md') -PathType Leaf } |
        Sort-Object Name
)
if ($skillDirs.Count -eq 0) { throw 'No skills/*/SKILL.md entries were found.' }

# Preflight every target before changing any Skill; only the managed block and
# its three runtime files belong to this generator.
foreach ($skillDir in $skillDirs) {
    Assert-NotLink -Path $skillDir.FullName
    Assert-NotLink -Path (Join-Path $skillDir.FullName 'SKILL.md')
    $scriptRoot = Join-Path $skillDir.FullName 'scripts'
    Assert-NotLink -Path $scriptRoot
    foreach ($runtimeFile in @($runtimeFiles + 'update-version.txt')) {
        Assert-NotLink -Path (Join-Path $scriptRoot $runtimeFile)
    }
    $content = [System.IO.File]::ReadAllText((Join-Path $skillDir.FullName 'SKILL.md'), [System.Text.Encoding]::UTF8)
    $startCount = [regex]::Matches($content, [regex]::Escape($startMarker)).Count
    $endCount = [regex]::Matches($content, [regex]::Escape($endMarker)).Count
    if ($startCount -gt 1 -or $endCount -gt 1 -or $startCount -ne $endCount -or
        ($startCount -eq 1 -and $content.IndexOf($startMarker) -gt $content.IndexOf($endMarker))) {
        throw "Ambiguous update entry in $($skillDir.Name); preserve and inspect it before syncing."
    }
    [void](Get-EntryInsertionIndex -Content $content)
}

foreach ($skillDir in $skillDirs) {
    $skillFile = Join-Path $skillDir.FullName 'SKILL.md'
    $originalBytes = [System.IO.File]::ReadAllBytes($skillFile)
    $hasBom = $originalBytes.Length -ge 3 -and $originalBytes[0] -eq 239 -and $originalBytes[1] -eq 187 -and $originalBytes[2] -eq 191
    $content = [System.IO.File]::ReadAllText($skillFile, [System.Text.Encoding]::UTF8)
    $newline = if ($content.Contains("`r`n")) { "`r`n" } else { "`n" }
    $entry = $entryTemplate.Replace("`n", $newline)
    if ($content.Contains($startMarker)) {
        $start = $content.IndexOf($startMarker)
        $end = $content.IndexOf($endMarker) + $endMarker.Length
        $updated = $content.Substring(0, $start) + $entry + $content.Substring($end)
    }
    else {
        $sectionIndex = Get-EntryInsertionIndex -Content $content
        if ($sectionIndex -ge 0) {
            $updated = $content.Insert($sectionIndex, $entry + $newline + $newline)
        }
        else {
            $updated = $content + $newline + $newline + $entry + $newline
        }
    }
    if ($updated -cne $content) {
        $encoding = New-Object System.Text.UTF8Encoding($hasBom)
        [System.IO.File]::WriteAllText($skillFile, $updated, $encoding)
    }
    $scriptRoot = Join-Path $skillDir.FullName 'scripts'
    [void][System.IO.Directory]::CreateDirectory($scriptRoot)
    foreach ($runtimeFile in $runtimeFiles) {
        Set-ManagedBytes -Path (Join-Path $scriptRoot $runtimeFile) -Bytes ([System.IO.File]::ReadAllBytes((Join-Path $templateRoot $runtimeFile)))
    }
    Set-ManagedBytes -Path (Join-Path $scriptRoot 'update-version.txt') -Bytes ([System.Text.Encoding]::UTF8.GetBytes($version + "`n"))
}
Write-Output "UPDATE SYNC PASS: $($skillDirs.Count) Skill(s), version $version."
