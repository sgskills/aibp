# Generated copies are managed by tools/sync-update-check.ps1.
# PowerShell 5.1; no installation, download of packages, or remote execution.
[CmdletBinding()]
param(
    [string]$NowSeconds = '',
    [string]$CacheRoot = '',
    [string]$ResponseFile = '',
    [string]$TestUrl = ''
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$attemptLock = $null
$client = $null
$response = $null
$cancel = $null
$stream = $null
$tempPath = $null

function Get-StrictVersion([string]$Value) {
    if ($Value.Length -gt 64 -or $Value -cnotmatch '\A(0|[1-9][0-9]{0,9})\.(0|[1-9][0-9]{0,9})\.(0|[1-9][0-9]{0,9})(?:\r?\n)?\z') { return $null }
    $parts = @([long]$Matches[1], [long]$Matches[2], [long]$Matches[3])
    foreach ($part in $parts) { if ($part -gt 2147483647) { return $null } }
    return ($parts -join '.')
}

function Read-SmallAscii([string]$Path) {
    $inputStream = [IO.File]::Open($Path, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
    try {
        if ($inputStream.Length -gt 64) { return $null }
        $bytes = New-Object byte[] 65
        $count = $inputStream.Read($bytes, 0, 65)
        for ($i = 0; $i -lt $count; $i++) { if ($bytes[$i] -gt 127) { return $null } }
        return [Text.Encoding]::ASCII.GetString($bytes, 0, $count)
    } finally { $inputStream.Dispose() }
}

try {
    $localVersion = Get-StrictVersion (Read-SmallAscii (Join-Path $PSScriptRoot 'update-version.txt'))
    if (-not $localVersion) { exit 0 }
    if ($NowSeconds -eq '') { $NowSeconds = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds().ToString([Globalization.CultureInfo]::InvariantCulture) }
    if ($NowSeconds -cnotmatch '\A(0|[1-9][0-9]{0,11})\z') { exit 0 }
    $now = [long]$NowSeconds
    $url = 'https://raw.githubusercontent.com/sgskills/aibp/main/VERSION'
    if ($TestUrl) {
        if ($TestUrl -cnotmatch '\Ahttp://127\.0\.0\.1:([1-9][0-9]{0,4})/[^\s#]*\z' -or [int]$Matches[1] -gt 65535) { exit 0 }
        $url = $TestUrl
    }
    if (-not $CacheRoot) {
        if (-not $env:LOCALAPPDATA) { exit 0 }
        $CacheRoot = Join-Path $env:LOCALAPPDATA 'SGSkills/aibp'
    }
    if (-not [IO.Path]::IsPathRooted($CacheRoot)) { exit 0 }
    $versionCache = Join-Path $CacheRoot $localVersion
    [void][IO.Directory]::CreateDirectory($versionCache)
    # FileShare.None is an atomic, process-owned lock; the OS releases it on exit/crash.
    $attemptLock = [IO.File]::Open((Join-Path $versionCache 'attempt.lock'), [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
    $attemptPath = Join-Path $versionCache 'last-attempt.txt'
    $repair = $false
    if ([IO.File]::Exists($attemptPath)) {
        $previous = Read-SmallAscii $attemptPath
        if ($null -eq $previous -or $previous -cnotmatch '\A(0|[1-9][0-9]{0,11})\z') { $repair = $true }
        elseif ([long]$previous -gt $now) { $repair = $true }
        elseif ($now - [long]$previous -lt 2592000) { exit 0 }
    }
    # Record every attempt before any network I/O, including failed attempts.
    $tempPath = Join-Path $versionCache ('attempt-' + [Guid]::NewGuid().ToString('N') + '.tmp')
    [IO.File]::WriteAllText($tempPath, $NowSeconds, [Text.Encoding]::ASCII)
    if ([IO.File]::Exists($attemptPath)) { [IO.File]::Replace($tempPath, $attemptPath, [System.Management.Automation.Language.NullString]::Value) }
    else { [IO.File]::Move($tempPath, $attemptPath) }
    $tempPath = $null
    $attemptLock.Dispose()
    $attemptLock = $null
    if ($repair) { exit 0 }

    if ($ResponseFile) { $remoteText = Read-SmallAscii $ResponseFile }
    else {
        Add-Type -AssemblyName System.Net.Http
        $handler = New-Object System.Net.Http.HttpClientHandler
        $handler.AllowAutoRedirect = $false
        $handler.UseProxy = $false
        $client = New-Object System.Net.Http.HttpClient($handler)
        $client.Timeout = [TimeSpan]::FromSeconds(5)
        $cancel = New-Object System.Threading.CancellationTokenSource
        $cancel.CancelAfter(5000)
        $watch = [Diagnostics.Stopwatch]::StartNew()
        $request = New-Object System.Net.Http.HttpRequestMessage([System.Net.Http.HttpMethod]::Get, $url)
        $request.Headers.UserAgent.ParseAdd('AIBP-update-check/1')
        $pending = $client.SendAsync($request, [System.Net.Http.HttpCompletionOption]::ResponseHeadersRead, $cancel.Token)
        if (-not $pending.Wait(5000)) { $cancel.Cancel(); exit 0 }
        $response = $pending.Result
        if ([int]$response.StatusCode -ne 200 -or $response.Content.Headers.ContentLength -gt 64) { exit 0 }
        $streamTask = $response.Content.ReadAsStreamAsync()
        $remaining = 5000 - [int]$watch.ElapsedMilliseconds
        if ($remaining -le 0 -or -not $streamTask.Wait($remaining)) { $cancel.Cancel(); exit 0 }
        $stream = $streamTask.Result
        $buffer = New-Object byte[] 65
        $used = 0
        while ($used -lt 65) {
            $remaining = 5000 - [int]$watch.ElapsedMilliseconds
            if ($remaining -le 0) { $cancel.Cancel(); exit 0 }
            $reading = $stream.ReadAsync($buffer, $used, 65 - $used, $cancel.Token)
            if (-not $reading.Wait($remaining)) { $cancel.Cancel(); exit 0 }
            if ($reading.Result -eq 0) { break }
            $used += $reading.Result
        }
        if ($used -gt 64) { exit 0 }
        for ($i = 0; $i -lt $used; $i++) { if ($buffer[$i] -gt 127) { exit 0 } }
        $remoteText = [Text.Encoding]::ASCII.GetString($buffer, 0, $used)
    }
    if ($null -eq $remoteText) { exit 0 }
    $remoteVersion = Get-StrictVersion $remoteText
    if (-not $remoteVersion) { exit 0 }
    $installed = $localVersion.Split('.')
    $available = $remoteVersion.Split('.')
    for ($i = 0; $i -lt 3; $i++) {
        if ([long]$available[$i] -lt [long]$installed[$i]) { exit 0 }
        if ([long]$available[$i] -gt [long]$installed[$i]) {
            # Escape Chinese text so BOM-less generated files also run under Windows PowerShell 5.1.
            $notice = 'AIBP ' + [string][char]0x6E90 + [char]0x7801 + [char]0x6709 + [char]0x65B0 + [char]0x7248 + [char]0x672C + ' v' + $remoteVersion + [char]0xFF08 + [char]0x5F53 + [char]0x524D + ' v' + $localVersion + [char]0xFF09 + [char]0xFF1A + 'https://github.com/sgskills/aibp'
            [Console]::OutputEncoding = New-Object Text.UTF8Encoding($false)
            [Console]::WriteLine($notice)
            break
        }
    }
} catch {
    # The optional check never blocks the Skill's actual task.
} finally {
    if ($attemptLock) { $attemptLock.Dispose() }
    if ($stream) { $stream.Dispose() }
    if ($response) { $response.Dispose() }
    if ($cancel) { $cancel.Dispose() }
    if ($client) { $client.Dispose() }
    if ($tempPath -and [IO.File]::Exists($tempPath)) { try { [IO.File]::Delete($tempPath) } catch {} }
}
exit 0
