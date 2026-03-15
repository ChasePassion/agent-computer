param()

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
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

& $tailscaleExe funnel reset
if ($LASTEXITCODE -ne 0) {
    throw "tailscale funnel reset failed."
}

if (Test-Path $statePath) {
    Remove-Item $statePath -Force
}

Write-Host "Tailscale Funnel disabled."
