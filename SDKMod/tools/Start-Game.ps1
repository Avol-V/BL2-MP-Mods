[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$GameDirectory,
    [ValidatePattern('^[A-Za-z]{3}$')][string]$Language,
    [switch]$Diagnostic,
    [string]$LogDirectory,
    [switch]$AllowUntestedBuild,
    [switch]$Launch
)
$ErrorActionPreference = 'Stop'
$gameRoot = (Resolve-Path -LiteralPath $GameDirectory).Path
$exe = Join-Path $gameRoot 'Binaries\Win32\Borderlands2.exe'
$expected = '1231b384aea791bc51286664627d03e27d6a77ffd4ec3bb5001186c136504c17'
$hash = (Get-FileHash -LiteralPath $exe).Hash.ToLowerInvariant()
if ($hash -ne $expected) {
    if (-not $AllowUntestedBuild) { throw 'Untested game EXE. Inspect the build or explicitly use -AllowUntestedBuild.' }
    Write-Warning 'This game build has not been verified with this mod.'
}
foreach ($relative in @('Binaries\Win32\ddraw.dll', 'Binaries\Win32\Plugins\unrealsdk.dll', 'Binaries\Win32\Plugins\pyunrealsdk.dll')) {
    if (-not (Test-Path -LiteralPath (Join-Path $gameRoot $relative))) { throw 'Install the willow2 PythonSDK mod manager first.' }
}
$settings = Join-Path $gameRoot 'sdk_mods\settings\unlimited_coop.json'
if (-not (Test-Path -LiteralPath $settings) -or -not (Get-Content -LiteralPath $settings -Raw | ConvertFrom-Json).enabled) {
    throw 'Enable Unlimited COOP in the Mods menu first, or install with --enable.'
}
$gameArguments = @('-fullscreen')
if ($Language) { $gameArguments += "-languageforcooking=$Language" }
if ($Diagnostic) {
    if (-not $LogDirectory) { $LogDirectory = Join-Path $gameRoot 'unlimited-coop-logs' }
    $logRoot = [IO.Path]::GetFullPath($LogDirectory)
    $logPath = Join-Path $logRoot ('host-' + (Get-Date -Format 'yyyyMMdd-HHmmss-ffff') + '.log')
    $gameArguments += '-log'
    $gameArguments += ('-ABSLOG="' + $logPath + '"')
}
[pscustomobject]@{Executable=$exe;Arguments=($gameArguments -join ' ');Launch=[bool]$Launch} | Format-List
if (-not $Launch) { return }
if (Get-Process Borderlands2 -ErrorAction SilentlyContinue) { throw 'Close the running Borderlands 2 before starting another copy.' }
if ($Diagnostic) { New-Item -ItemType Directory -Path $logRoot -Force | Out-Null }
# Exit immediately after starting the interactive game; no background helper is left running.
Start-Process -FilePath $exe -WorkingDirectory (Split-Path $exe -Parent) -ArgumentList $gameArguments -WindowStyle Normal
