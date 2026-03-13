param(
    [string]$BindHost = "127.0.0.1",
    [int]$Port = 37688
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

Write-Host "Starting agent-computer daemon for observation on $BindHost`:$Port ..."
& .\run.ps1 daemon start --host $BindHost --port $Port

Write-Host ""
Write-Host "Observation daemon started."
Write-Host "Run .\scripts\show_observation_urls.ps1 to print the live URLs."
