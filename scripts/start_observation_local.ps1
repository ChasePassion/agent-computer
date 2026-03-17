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
$daemonBaseUrl = "http://{0}:{1}" -f $AccessHost, $Port

function Test-DaemonHealthy {
    try {
        Invoke-RestMethod -Uri ("{0}/system/health" -f $daemonBaseUrl) -Method Get | Out-Null
        return $true
    } catch {
        return $false
    }
}

if (Test-DaemonHealthy) {
    Write-Host "Stopping existing agent-computer daemon on $BindHost`:$Port ..."
    & .\windows-launcher.ps1 daemon stop --host $AccessHost --port $Port

    $stopDeadline = (Get-Date).AddSeconds(10)
    while ((Get-Date) -lt $stopDeadline) {
        Start-Sleep -Milliseconds 250
        if (-not (Test-DaemonHealthy)) {
            break
        }
    }

    if (Test-DaemonHealthy) {
        throw "Timed out waiting for the existing agent-computer daemon to stop."
    }

    Write-Host ""
}

Write-Host "Starting agent-computer daemon for observation on $BindHost`:$Port ..."
& .\windows-launcher.ps1 daemon start --bind-host $BindHost --host $AccessHost --port $Port

Write-Host ""
Write-Host "Observation daemon started."
Write-Host ""
& .\windows-launcher.ps1 observation urls --host $AccessHost --port $Port
