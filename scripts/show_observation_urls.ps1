param(
    [string]$LocalHost = "",
    [int]$LocalPort = 0
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
Set-Location $projectRoot
& .\windows-launcher.ps1 observation urls --host $LocalHost --port $LocalPort
