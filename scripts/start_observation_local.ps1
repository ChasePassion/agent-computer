param(
    [string]$BindHost = "127.0.0.1",
    [int]$Port = 37688
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

Write-Host "Starting agent-computer daemon for observation on $BindHost`:$Port ..."
& .\windows-launcher.ps1 daemon start --host $BindHost --port $Port

Write-Host ""
Write-Host "Observation daemon started."
Write-Host ""
& .\windows-launcher.ps1 observation urls --host $BindHost --port $Port
