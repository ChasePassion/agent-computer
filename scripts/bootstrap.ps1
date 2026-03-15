param(
    [string]$BindHost = $(if ($env:AGENT_COMPUTER_BIND_HOST) { $env:AGENT_COMPUTER_BIND_HOST } elseif ($env:AGENT_COMPUTER_HOST) { $env:AGENT_COMPUTER_HOST } else { "127.0.0.1" }),
    [string]$AccessHost = $(if ($env:AGENT_COMPUTER_HOST) { $env:AGENT_COMPUTER_HOST } else { "127.0.0.1" }),
    [int]$Port = 37688,
    [switch]$Json
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$projectRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $projectRoot "scripts\load_env.ps1")
Import-ProjectEnv -ProjectRoot $projectRoot
$agentDir = Join-Path $projectRoot ".agent"
$localEnvRoot = Join-Path $projectRoot ".conda"
$localPythonExe = Join-Path $localEnvRoot "python.exe"
$localPipExe = Join-Path $localEnvRoot "Scripts\\pip.exe"
$statusPath = Join-Path $agentDir "bootstrap.status.json"
$windowsLauncher = Join-Path $projectRoot "windows-launcher.ps1"

Set-Location $projectRoot

function Ensure-Directory {
    param(
        [string]$PathValue
    )

    if (-not (Test-Path $PathValue)) {
        New-Item -ItemType Directory -Path $PathValue -Force | Out-Null
    }
}

function Resolve-AbsolutePath {
    param(
        [string]$PathValue
    )

    return [IO.Path]::GetFullPath($PathValue)
}

function Invoke-Conda {
    param(
        [string[]]$Arguments
    )

    $condaCommand = Get-Command conda -ErrorAction SilentlyContinue
    if ($null -eq $condaCommand) {
        throw "conda is not installed or not on PATH. Install Miniforge/Conda first, then rerun scripts/bootstrap.ps1."
    }

    & $condaCommand.Source @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "conda $($Arguments -join ' ') failed with exit code $LASTEXITCODE."
    }
}

function Ensure-CondaEnvironment {
    if (Test-Path $localPythonExe) {
        return "existing"
    }

    if (Test-Path $localEnvRoot) {
        Invoke-Conda -Arguments @("env", "update", "-p", $localEnvRoot, "-f", "environment.yml", "--prune")
    } else {
        Invoke-Conda -Arguments @("env", "create", "-p", $localEnvRoot, "-f", "environment.yml")
    }

    if (-not (Test-Path $localPythonExe)) {
        throw "Bootstrap expected Python at $localPythonExe after conda setup, but it was not found."
    }

    return "created"
}

function Install-EditablePackage {
    if (Test-Path $localPipExe) {
        & $localPipExe install -e .
    } else {
        & $localPythonExe -m pip install -e .
    }

    if ($LASTEXITCODE -ne 0) {
        throw "Editable install failed."
    }
}

function Start-And-CheckDaemon {
    & $windowsLauncher daemon start --bind-host $BindHost --host $AccessHost --port $Port | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to start daemon."
    }

    $urlsJson = & $windowsLauncher observation urls --host $AccessHost --port $Port --json
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to generate observation URLs."
    }

    return $urlsJson | ConvertFrom-Json
}

function Get-RemoteConfigStatusFromEnv {
    $relayHost = $env:AGENT_COMPUTER_RELAY_HOST
    $relayUser = $env:AGENT_COMPUTER_RELAY_USER
    $relayPort = $env:AGENT_COMPUTER_RELAY_PORT
    $publicBaseUrl = $env:AGENT_COMPUTER_OBSERVATION_PUBLIC_BASE_URL

    return [ordered]@{
        configured = (
            -not [string]::IsNullOrWhiteSpace($relayHost) -and
            -not [string]::IsNullOrWhiteSpace($relayUser) -and
            -not [string]::IsNullOrWhiteSpace($relayPort) -and
            -not [string]::IsNullOrWhiteSpace($publicBaseUrl)
        )
        relay_password_present = -not [string]::IsNullOrWhiteSpace($env:AGENT_COMPUTER_RELAY_PASSWORD)
        ssh_port = $(if ($env:AGENT_COMPUTER_RELAY_SSH_PORT) { [int]$env:AGENT_COMPUTER_RELAY_SSH_PORT } else { 22 })
        relay_port = $(if ($env:AGENT_COMPUTER_RELAY_PORT) { [int]$env:AGENT_COMPUTER_RELAY_PORT } else { $null })
        local_host = $(if ($env:AGENT_COMPUTER_LOCAL_HOST) { [string]$env:AGENT_COMPUTER_LOCAL_HOST } else { "127.0.0.1" })
        local_port = $(if ($env:AGENT_COMPUTER_LOCAL_PORT) { [int]$env:AGENT_COMPUTER_LOCAL_PORT } else { $Port })
        public_base_url_configured = -not [string]::IsNullOrWhiteSpace($publicBaseUrl)
    }
}

Ensure-Directory $agentDir
$condaStatus = Ensure-CondaEnvironment
Install-EditablePackage
$observationUrls = Start-And-CheckDaemon
$remoteConfigStatus = Get-RemoteConfigStatusFromEnv

$payload = [ordered]@{
    generated_at = (Get-Date).ToString("o")
    project_root = $projectRoot
    conda_env = Resolve-AbsolutePath $localEnvRoot
    conda_status = $condaStatus
    editable_install = $true
    daemon_ready = $true
    daemon_host = $AccessHost
    daemon_bind_host = $BindHost
    daemon_port = $Port
    observation_urls_path = Join-Path $agentDir "observation.urls.json"
    remote_env = $remoteConfigStatus
    external_skills_install = "npx skills add https://github.com/ChasePassion/agent-computer-skill"
}

$payload | ConvertTo-Json -Depth 8 | Set-Content -Path $statusPath -Encoding utf8

if ($Json) {
    $payload | ConvertTo-Json -Depth 8
    exit 0
}

Write-Host "Bootstrap completed."
Write-Host "Project root: $projectRoot"
Write-Host "Conda env: $($payload.conda_env)"
Write-Host "Daemon bind: http://$BindHost`:$Port"
Write-Host "Daemon access: http://$AccessHost`:$Port"
Write-Host "Bootstrap status: $statusPath"
if ($remoteConfigStatus.configured) {
    Write-Host "Remote observation config: loaded from .env"
} else {
    Write-Host "Remote observation config: not configured in .env"
}
Write-Host "Install external skills with:"
Write-Host "  npx skills add https://github.com/ChasePassion/agent-computer-skill"
