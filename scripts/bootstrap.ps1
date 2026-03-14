param(
    [string]$BindHost = "127.0.0.1",
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
$remoteConfigPath = Join-Path $agentDir "observation.remote.json"
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
    & $windowsLauncher daemon start --host $BindHost --port $Port | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to start daemon."
    }

    $urlsJson = & $windowsLauncher observation urls --host $BindHost --port $Port --json
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to generate observation URLs."
    }

    return $urlsJson | ConvertFrom-Json
}

function Ensure-RemoteConfigFromEnv {
    $relayHost = $env:AGENT_COMPUTER_RELAY_HOST
    $relayUser = $env:AGENT_COMPUTER_RELAY_USER
    $relayPort = $env:AGENT_COMPUTER_RELAY_PORT
    $publicBaseUrl = $env:AGENT_COMPUTER_OBSERVATION_PUBLIC_BASE_URL

    if (-not [string]::IsNullOrWhiteSpace($relayHost) -and
        -not [string]::IsNullOrWhiteSpace($relayUser) -and
        -not [string]::IsNullOrWhiteSpace($relayPort) -and
        -not [string]::IsNullOrWhiteSpace($publicBaseUrl)) {
        $payload = [ordered]@{
            relay_host = [string]$relayHost
            relay_user = [string]$relayUser
            ssh_port = $(if ($env:AGENT_COMPUTER_RELAY_SSH_PORT) { [int]$env:AGENT_COMPUTER_RELAY_SSH_PORT } else { 22 })
            relay_port = [int]$relayPort
            local_host = $(if ($env:AGENT_COMPUTER_LOCAL_HOST) { [string]$env:AGENT_COMPUTER_LOCAL_HOST } else { "127.0.0.1" })
            local_port = $(if ($env:AGENT_COMPUTER_LOCAL_PORT) { [int]$env:AGENT_COMPUTER_LOCAL_PORT } else { $Port })
            public_base_url = [string]$publicBaseUrl
        }

        if ($env:AGENT_COMPUTER_RELAY_PASSWORD) {
            $payload["relay_password"] = $env:AGENT_COMPUTER_RELAY_PASSWORD
        }

        $payload | ConvertTo-Json -Depth 4 | Set-Content -Path $remoteConfigPath -Encoding utf8
        return $payload
    }

    if (Test-Path $remoteConfigPath) {
        return (Get-Content $remoteConfigPath -Raw | ConvertFrom-Json)
    }

    if ([string]::IsNullOrWhiteSpace($relayHost) -or
        [string]::IsNullOrWhiteSpace($relayUser) -or
        [string]::IsNullOrWhiteSpace($relayPort) -or
        [string]::IsNullOrWhiteSpace($publicBaseUrl)) {
        return $null
    }
}

Ensure-Directory $agentDir
$condaStatus = Ensure-CondaEnvironment
Install-EditablePackage
$observationUrls = Start-And-CheckDaemon
$remoteConfig = Ensure-RemoteConfigFromEnv

$payload = [ordered]@{
    generated_at = (Get-Date).ToString("o")
    project_root = $projectRoot
    conda_env = Resolve-AbsolutePath $localEnvRoot
    conda_status = $condaStatus
    editable_install = $true
    daemon_ready = $true
    daemon_host = $BindHost
    daemon_port = $Port
    observation_urls = $observationUrls
    remote_config_path = $remoteConfigPath
    remote_config_present = [bool]($null -ne $remoteConfig)
    remote_config = $remoteConfig
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
Write-Host "Daemon: http://$BindHost`:$Port"
Write-Host "Bootstrap status: $statusPath"
if ($null -ne $remoteConfig) {
    Write-Host "Remote observation config: $remoteConfigPath"
} else {
    Write-Host "Remote observation config: not generated (set AGENT_COMPUTER_RELAY_HOST / AGENT_COMPUTER_RELAY_USER / AGENT_COMPUTER_RELAY_PORT / AGENT_COMPUTER_OBSERVATION_PUBLIC_BASE_URL to auto-generate)."
}
Write-Host "Install external skills with:"
Write-Host "  npx skills add https://github.com/ChasePassion/agent-computer-skill"
