param(
    [string]$RelayHost = $(if ($env:AGENT_COMPUTER_RELAY_HOST) { $env:AGENT_COMPUTER_RELAY_HOST } else { $null }),
    [string]$RelayUser = $(if ($env:AGENT_COMPUTER_RELAY_USER) { $env:AGENT_COMPUTER_RELAY_USER } else { $null }),
    [string]$RelayPassword = $(if ($env:AGENT_COMPUTER_RELAY_PASSWORD) { $env:AGENT_COMPUTER_RELAY_PASSWORD } else { $null }),
    [int]$SshPort = $(if ($env:AGENT_COMPUTER_RELAY_SSH_PORT) { [int]$env:AGENT_COMPUTER_RELAY_SSH_PORT } else { 22 }),
    [int]$RelayPort = $(if ($env:AGENT_COMPUTER_RELAY_PORT) { [int]$env:AGENT_COMPUTER_RELAY_PORT } else { 43768 }),
    [string]$LocalHost = $(if ($env:AGENT_COMPUTER_LOCAL_HOST) { $env:AGENT_COMPUTER_LOCAL_HOST } else { "127.0.0.1" }),
    [int]$LocalPort = $(if ($env:AGENT_COMPUTER_LOCAL_PORT) { [int]$env:AGENT_COMPUTER_LOCAL_PORT } else { 37688 })
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $projectRoot "scripts\load_env.ps1")
Import-ProjectEnv -ProjectRoot $projectRoot
$statePath = Join-Path $projectRoot ".agent\observation.tunnel.state.json"
$localPythonExe = Join-Path $projectRoot ".conda\python.exe"
$tunnelManagerScript = Join-Path $projectRoot "scripts\tunnel_manager.py"

if (-not $RelayHost) {
    throw "Missing RelayHost. Pass -RelayHost or set AGENT_COMPUTER_RELAY_HOST in .env."
}

if (-not $RelayUser) {
    throw "Missing RelayUser. Pass -RelayUser or set AGENT_COMPUTER_RELAY_USER in .env."
}

$target = "{0}@{1}" -f $RelayUser, $RelayHost

if (-not (Test-Path $localPythonExe)) {
    throw "Local Python environment not found at $localPythonExe. Run scripts/bootstrap.ps1 first."
}

Write-Host "Starting transactional observation tunnel to $target ..."

$pythonArgs = @(
    $tunnelManagerScript
    "--relay-host", $RelayHost
    "--relay-user", $RelayUser
    "--ssh-port", $SshPort
    "--remote-port", $RelayPort
    "--local-host", $LocalHost
    "--local-port", $LocalPort
    "--state-path", $statePath
)

if (-not [string]::IsNullOrWhiteSpace($RelayPassword)) {
    $pythonArgs += @("--relay-password", $RelayPassword)
}

& $localPythonExe @pythonArgs

exit $LASTEXITCODE
