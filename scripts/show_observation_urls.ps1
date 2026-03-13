param(
    [string]$LocalHost = "127.0.0.1",
    [int]$LocalPort = 37688
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$tokenPath = Join-Path $projectRoot ".agent\observation.json"
$remoteConfigPath = Join-Path $projectRoot ".agent\observation.remote.json"

if (-not (Test-Path $tokenPath)) {
    throw "Observation token file not found: $tokenPath. Start the observation daemon first."
}

$tokenPayload = Get-Content $tokenPath -Raw | ConvertFrom-Json
$token = [string]$tokenPayload.token
if ([string]::IsNullOrWhiteSpace($token)) {
    throw "Observation token is missing in $tokenPath."
}

$localBase = "http://{0}:{1}" -f $LocalHost, $LocalPort
$publicBase = $null

if (Test-Path $remoteConfigPath) {
    $remoteConfig = Get-Content $remoteConfigPath -Raw | ConvertFrom-Json
    if ($remoteConfig.public_base_url) {
        $publicBase = ([string]$remoteConfig.public_base_url).TrimEnd("/")
    }
}

$localLive = "{0}/live?token={1}" -f $localBase, $token
$localPreview = "{0}/observation/latest.jpg?token={1}&mode=preview" -f $localBase, $token
$localGrid = "{0}/observation/latest.jpg?token={1}&mode=grid" -f $localBase, $token

Write-Host "Local Live:"
Write-Host $localLive
Write-Host ""
Write-Host "Local Preview Latest:"
Write-Host $localPreview
Write-Host ""
Write-Host "Local Grid Latest:"
Write-Host $localGrid

if ($publicBase) {
    $publicLive = "{0}/live?token={1}" -f $publicBase, $token
    $publicPreview = "{0}/observation/latest.jpg?token={1}&mode=preview" -f $publicBase, $token
    $publicGrid = "{0}/observation/latest.jpg?token={1}&mode=grid" -f $publicBase, $token

    Write-Host ""
    Write-Host "Public Live:"
    Write-Host $publicLive
    Write-Host ""
    Write-Host "Public Preview Latest:"
    Write-Host $publicPreview
    Write-Host ""
    Write-Host "Public Grid Latest:"
    Write-Host $publicGrid
}
