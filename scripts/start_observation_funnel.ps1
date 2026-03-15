param(
    [string]$LocalHost = "",
    [int]$LocalPort = 0,
    [int]$HttpsPort = 0
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $projectRoot "scripts\load_env.ps1")
Import-ProjectEnv -ProjectRoot $projectRoot
if ([string]::IsNullOrWhiteSpace($LocalHost)) {
    $LocalHost = if ($env:AGENT_COMPUTER_HOST) { $env:AGENT_COMPUTER_HOST } else { "127.0.0.1" }
}
if ($LocalPort -le 0) {
    $LocalPort = if ($env:AGENT_COMPUTER_PORT) { [int]$env:AGENT_COMPUTER_PORT } else { 37688 }
}
if ($HttpsPort -le 0) {
    $HttpsPort = if ($env:AGENT_COMPUTER_FUNNEL_HTTPS_PORT) { [int]$env:AGENT_COMPUTER_FUNNEL_HTTPS_PORT } else { 443 }
}
$statePath = Join-Path $projectRoot ".agent\observation.funnel.json"
$tailscaleCommand = Get-Command "tailscale" -ErrorAction SilentlyContinue
$tailscaleExe = if ($tailscaleCommand) {
    $tailscaleCommand.Source
} elseif (Test-Path "C:\Program Files\Tailscale\tailscale.exe") {
    "C:\Program Files\Tailscale\tailscale.exe"
} else {
    $null
}

if ($null -eq $tailscaleExe) {
    throw "tailscale CLI not found on PATH. Install Tailscale and ensure the tailscale command is available."
}

Set-Location $projectRoot

$target = "{0}:{1}" -f $LocalHost, $LocalPort
Write-Host "Starting Tailscale Funnel to $target on external HTTPS port $HttpsPort ..."
& $tailscaleExe funnel --bg "--https=$HttpsPort" $target
if ($LASTEXITCODE -ne 0) {
    throw "tailscale funnel failed."
}

$statusOutput = & $tailscaleExe funnel status
if ($LASTEXITCODE -ne 0) {
    throw "tailscale funnel status failed."
}

$publicBaseUrl = $null
foreach ($line in $statusOutput) {
    if ($line -match "https://[^\s/]+") {
        $publicBaseUrl = $matches[0].TrimEnd("/")
        break
    }
}

if ([string]::IsNullOrWhiteSpace($publicBaseUrl)) {
    throw "Could not detect Funnel public base URL from 'tailscale funnel status'."
}

$payload = [ordered]@{
    generated_at = (Get-Date).ToString("o")
    source = "tailscale-funnel"
    public_base_url = $publicBaseUrl
    https_port = $HttpsPort
    local_host = $LocalHost
    local_port = $LocalPort
}

$payload | ConvertTo-Json -Depth 8 | Set-Content -Path $statePath -Encoding utf8

Write-Host "Tailscale Funnel enabled."
Write-Host "Public base URL: $publicBaseUrl"
Write-Host "State file: $statePath"
Write-Host ""
& .\scripts\show_observation_urls.ps1 -LocalHost $LocalHost -LocalPort $LocalPort
