param(
    [string]$RequestFile = "",
    [string]$RequestJson = ""
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$launcher = Join-Path $projectRoot "windows-launcher.ps1"

if (-not (Test-Path $launcher)) {
    throw "windows-launcher.ps1 not found: $launcher"
}

$status = & $launcher browser-assist-status | Out-String
Write-Output "Browser Assist status:"
Write-Output $status.Trim()

if ([string]::IsNullOrWhiteSpace($RequestFile) -and [string]::IsNullOrWhiteSpace($RequestJson)) {
    Write-Output ""
    Write-Output "No locate request supplied. Pass -RequestFile or -RequestJson to run a locate roundtrip."
    exit 0
}

$locateArgs = @("browser-assist-locate")
if (-not [string]::IsNullOrWhiteSpace($RequestFile)) {
    $locateArgs += @("--input-file", $RequestFile)
} else {
    $locateArgs += @("--input-json", $RequestJson)
}

Write-Output ""
Write-Output "Locate response:"
& $launcher @locateArgs
