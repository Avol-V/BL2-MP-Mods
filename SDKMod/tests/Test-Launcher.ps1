# Offline Windows launcher checks. The real Start-Process command is never called.
$ErrorActionPreference = 'Stop'
$sdkRoot = Split-Path $PSScriptRoot -Parent
$fixtureRoot = Join-Path $PSScriptRoot ('.launcher-fixture-' + [guid]::NewGuid().ToString('N'))
$gameRoot = Join-Path $fixtureRoot 'Game with spaces'
New-Item -ItemType Directory -Path (Join-Path $gameRoot 'Binaries\Win32\Plugins'), (Join-Path $gameRoot 'sdk_mods\settings') -Force | Out-Null
foreach ($relative in @('Binaries\Win32\Borderlands2.exe','Binaries\Win32\ddraw.dll','Binaries\Win32\Plugins\unrealsdk.dll','Binaries\Win32\Plugins\pyunrealsdk.dll')) {
    Set-Content -LiteralPath (Join-Path $gameRoot $relative) -Value 'offline fixture'
}
Set-Content -LiteralPath (Join-Path $gameRoot 'sdk_mods\settings\unlimited_coop.json') -Value '{"enabled":true}'
function Get-Process { param($Name, $ErrorAction) }
function Start-Process {
    param($FilePath, $WorkingDirectory, $ArgumentList, $WindowStyle)
    $global:UnlimitedCoopLauncherProbe.Value = @{File=$FilePath;Arguments=$ArgumentList;WorkingDirectory=$WorkingDirectory;WindowStyle=$WindowStyle}
}
try {
    $launcher = Join-Path $sdkRoot 'tools\Start-Game.ps1'
    $tokens = $null; $errors = $null
    [System.Management.Automation.Language.Parser]::ParseFile($launcher, [ref]$tokens, [ref]$errors) | Out-Null
    if ($errors.Count) { throw 'Invalid PowerShell syntax' }
    $global:UnlimitedCoopLauncherProbe = [pscustomobject]@{Value=$null}
    & $launcher -GameDirectory $gameRoot -AllowUntestedBuild
    if ($null -ne $global:UnlimitedCoopLauncherProbe.Value) { throw 'Dry run started a process' }
    $rejected = $false
    try { & $launcher -GameDirectory $gameRoot } catch { $rejected = $true }
    if (-not $rejected) { throw 'Untested EXE was accepted by default' }
    & $launcher -GameDirectory $gameRoot -AllowUntestedBuild -Launch
    if (($global:UnlimitedCoopLauncherProbe.Value.Arguments -join ' ') -ne '-fullscreen') { throw 'Normal launch has unwanted flags' }
    if ($global:UnlimitedCoopLauncherProbe.Value.File -ne (Join-Path $gameRoot 'Binaries\Win32\Borderlands2.exe')) { throw 'Wrong game path' }
    $logRoot = Join-Path $fixtureRoot 'Logs with spaces'
    & $launcher -GameDirectory $gameRoot -AllowUntestedBuild -Language rus -Diagnostic -LogDirectory $logRoot -Launch
    $joined = $global:UnlimitedCoopLauncherProbe.Value.Arguments -join ' '
    if ($joined -notmatch '-ABSLOG="[^"]*Logs with spaces[^"]*"' -or $joined -notmatch '-languageforcooking=rus') { throw 'Diagnostic quoting/language failed' }
    'Launcher checks passed; no game process was started.'
} finally {
    Remove-Variable UnlimitedCoopLauncherProbe -Scope Global -ErrorAction SilentlyContinue
    $resolvedFixture = [IO.Path]::GetFullPath($fixtureRoot)
    $allowedRoot = [IO.Path]::GetFullPath($PSScriptRoot) + [IO.Path]::DirectorySeparatorChar
    if (-not $resolvedFixture.StartsWith($allowedRoot, [StringComparison]::OrdinalIgnoreCase) -or (Split-Path $resolvedFixture -Leaf) -notlike '.launcher-fixture-*') {
        throw 'Refusing cleanup outside the fixture directory'
    }
    Remove-Item -LiteralPath $resolvedFixture -Recurse -Force
}
