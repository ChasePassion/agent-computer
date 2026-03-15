param(
    [string]$BindHost = "",
    [string]$AccessHost = "",
    [int]$Port = 0
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $projectRoot "scripts\load_env.ps1")
Import-ProjectEnv -ProjectRoot $projectRoot

if ([string]::IsNullOrWhiteSpace($BindHost)) {
    $BindHost = if ($env:AGENT_COMPUTER_BIND_HOST) { $env:AGENT_COMPUTER_BIND_HOST } elseif ($env:AGENT_COMPUTER_HOST) { $env:AGENT_COMPUTER_HOST } else { "127.0.0.1" }
}
if ([string]::IsNullOrWhiteSpace($AccessHost)) {
    $AccessHost = if ($env:AGENT_COMPUTER_HOST) { $env:AGENT_COMPUTER_HOST } else { "127.0.0.1" }
}
if ($Port -le 0) {
    $Port = if ($env:AGENT_COMPUTER_PORT) { [int]$env:AGENT_COMPUTER_PORT } else { 37688 }
}

Set-Location $projectRoot

Write-Host "Starting agent-computer daemon for observation on $BindHost`:$Port ..."
& .\windows-launcher.ps1 daemon start --bind-host $BindHost --host $AccessHost --port $Port

Write-Host ""
Write-Host "Observation daemon started."
Write-Host ""
& .\windows-launcher.ps1 observation urls --host $AccessHost --port $Port
