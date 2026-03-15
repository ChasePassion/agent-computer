param(
    [ValidateSet("funnel", "relay", "both")]
    [string]$Mode = "both",
    [string]$BindHost = "",
    [string]$AccessHost = "",
    [int]$Port = 0,
    [int]$HttpsPort = 0
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
if ($HttpsPort -le 0) {
    $HttpsPort = if ($env:AGENT_COMPUTER_FUNNEL_HTTPS_PORT) { [int]$env:AGENT_COMPUTER_FUNNEL_HTTPS_PORT } else { 443 }
}
$relayStatePath = Join-Path $projectRoot ".agent\observation.tunnel.state.json"
$relayHost = $env:AGENT_COMPUTER_RELAY_HOST
$relayUser = $env:AGENT_COMPUTER_RELAY_USER
$relayPassword = $env:AGENT_COMPUTER_RELAY_PASSWORD
$relaySshPort = if ($env:AGENT_COMPUTER_RELAY_SSH_PORT) { [int]$env:AGENT_COMPUTER_RELAY_SSH_PORT } else { 22 }
$relayPort = if ($env:AGENT_COMPUTER_RELAY_PORT) { [int]$env:AGENT_COMPUTER_RELAY_PORT } else { 43768 }
$relayPublicBaseUrl = $env:AGENT_COMPUTER_OBSERVATION_PUBLIC_BASE_URL
$relayConfigured = (
    -not [string]::IsNullOrWhiteSpace($relayHost) -and
    -not [string]::IsNullOrWhiteSpace($relayUser) -and
    -not [string]::IsNullOrWhiteSpace($relayPublicBaseUrl)
)
$relayStdoutPath = Join-Path $projectRoot ".agent\observation.tunnel.stdout.log"
$relayStderrPath = Join-Path $projectRoot ".agent\observation.tunnel.stderr.log"
Set-Location $projectRoot

Write-Host "Step 1: start local observation daemon"
& .\scripts\start_observation_local.ps1 -BindHost $BindHost -AccessHost $AccessHost -Port $Port
if ($LASTEXITCODE -ne 0) {
    throw "start_observation_local.ps1 failed."
}

if ($Mode -in @("relay", "both")) {
    if (-not $relayConfigured) {
        if ($Mode -eq "relay") {
            throw "Relay mode requires AGENT_COMPUTER_RELAY_HOST, AGENT_COMPUTER_RELAY_USER, and AGENT_COMPUTER_OBSERVATION_PUBLIC_BASE_URL in .env."
        }
        Write-Warning "Relay config is incomplete in .env. Skipping relay startup and continuing with Funnel only."
    } else {
        Write-Host ""
        Write-Host "Step 2: start relay tunnel in background"
        if (Test-Path $relayStatePath) {
            $existingRelayState = Get-Content $relayStatePath -Raw | ConvertFrom-Json
            if ($existingRelayState.cleanup_pending -eq $true) {
                Remove-Item $relayStatePath -Force
            }
        }
        $localPythonExe = Join-Path $projectRoot ".conda\python.exe"
        $tunnelManagerScript = Join-Path $projectRoot "scripts\tunnel_manager.py"
        $relayArgs = @(
            $tunnelManagerScript
            "--relay-host", $relayHost
            "--relay-user", $relayUser
            "--ssh-port", [string]$relaySshPort
            "--remote-port", [string]$relayPort
            "--local-host", $AccessHost
            "--local-port", [string]$Port
            "--state-path", $relayStatePath
        )
        if (-not [string]::IsNullOrWhiteSpace($relayPassword)) {
            $relayArgs += @("--relay-password", $relayPassword)
        }
        Start-Process -FilePath $localPythonExe `
            -ArgumentList $relayArgs `
            -WorkingDirectory $projectRoot `
            -RedirectStandardOutput $relayStdoutPath `
            -RedirectStandardError $relayStderrPath `
            -WindowStyle Hidden | Out-Null
        $deadline = (Get-Date).AddSeconds(10)
        while ((Get-Date) -lt $deadline) {
            if (Test-Path $relayStatePath) {
                $relayState = Get-Content $relayStatePath -Raw | ConvertFrom-Json
                if ($relayState.cleanup_pending -eq $false) {
                    break
                }
            }
            Start-Sleep -Milliseconds 250
        }
        if (-not (Test-Path $relayStatePath)) {
            throw "Relay tunnel did not create a state file. Check .agent/observation.tunnel.stderr.log"
        }
        $relayState = Get-Content $relayStatePath -Raw | ConvertFrom-Json
        if ($relayState.cleanup_pending -ne $false) {
            throw "Relay tunnel did not become ready. Check .agent/observation.tunnel.stderr.log"
        }
    }
}

if ($Mode -in @("funnel", "both")) {
    Write-Host ""
    Write-Host "Step 3: start Tailscale Funnel"
    & .\scripts\start_observation_funnel.ps1 -LocalHost $AccessHost -LocalPort $Port -HttpsPort $HttpsPort
    if ($LASTEXITCODE -ne 0) {
        throw "start_observation_funnel.ps1 failed."
    }
} else {
    Write-Host ""
    Write-Host "Public URLs:"
    & .\scripts\show_observation_urls.ps1 -LocalHost $AccessHost -LocalPort $Port
    if ($LASTEXITCODE -ne 0) {
        throw "show_observation_urls.ps1 failed."
    }
}
