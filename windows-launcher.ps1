param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Args
)

$ErrorActionPreference = "Stop"

$projectRoot = $PSScriptRoot
$localEnvRoot = Join-Path $projectRoot ".conda"
$localCliExe = Join-Path $localEnvRoot "Scripts\agent-computer.exe"
$localDaemonExe = Join-Path $localEnvRoot "Scripts\agent-computer-daemon.exe"
$localPythonExe = Join-Path $localEnvRoot "python.exe"
$daemonHost = if ($env:AGENT_COMPUTER_HOST) { $env:AGENT_COMPUTER_HOST } else { "127.0.0.1" }
$daemonPort = if ($env:AGENT_COMPUTER_PORT) { [int]$env:AGENT_COMPUTER_PORT } else { 37688 }
$daemonStartupTimeoutSec = if ($env:AGENT_COMPUTER_STARTUP_TIMEOUT_SEC) {
    [double]$env:AGENT_COMPUTER_STARTUP_TIMEOUT_SEC
} else {
    15.0
}
$projectPythonPath = Join-Path $projectRoot "src"
$pathSeparator = [IO.Path]::PathSeparator
$script:daemonBaseUrl = "http://{0}:{1}" -f $daemonHost, $daemonPort
$pathCliCommand = Get-Command "agent-computer" -ErrorAction SilentlyContinue
$pathDaemonCommand = Get-Command "agent-computer-daemon" -ErrorAction SilentlyContinue

function Invoke-WithProjectPythonPath {
    param(
        [scriptblock]$Action
    )

    $hadPythonPath = Test-Path Env:PYTHONPATH
    $originalPythonPath = $env:PYTHONPATH
    $updatedPythonPath = $projectPythonPath

    if ($hadPythonPath -and -not [string]::IsNullOrWhiteSpace($originalPythonPath)) {
        $existingSegments = $originalPythonPath -split [regex]::Escape($pathSeparator)
        if ($existingSegments -notcontains $projectPythonPath) {
            $updatedPythonPath = "{0}{1}{2}" -f $projectPythonPath, $pathSeparator, $originalPythonPath
        } else {
            $updatedPythonPath = $originalPythonPath
        }
    }

    $env:PYTHONPATH = $updatedPythonPath
    try {
        & $Action
    } finally {
        if ($hadPythonPath) {
            $env:PYTHONPATH = $originalPythonPath
        } else {
            Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
        }
    }
}

function Get-DaemonHealth {
    try {
        return Invoke-RestMethod -Uri ("{0}/system/health" -f $script:daemonBaseUrl) -Method Get
    } catch {
        return $null
    }
}

function Start-DaemonBackground {
    $daemonArgs = @("--host", $daemonHost, "--port", [string]$daemonPort)

    if (Test-Path $localDaemonExe) {
        Start-Process -FilePath $localDaemonExe -ArgumentList $daemonArgs -WorkingDirectory $projectRoot -WindowStyle Hidden | Out-Null
        return
    }

    if (Test-Path $localPythonExe) {
        Invoke-WithProjectPythonPath {
            Start-Process -FilePath $localPythonExe `
                -ArgumentList @("-m", "agent_computer.daemon") + $daemonArgs `
                -WorkingDirectory $projectRoot `
                -WindowStyle Hidden | Out-Null
        }
        return
    }

    if ($pathDaemonCommand) {
        Start-Process -FilePath $pathDaemonCommand.Source -ArgumentList $daemonArgs -WorkingDirectory $projectRoot -WindowStyle Hidden | Out-Null
        return
    }

    Start-Process -FilePath "conda" `
        -ArgumentList @("run", "-p", $localEnvRoot, "python", "-m", "agent_computer.daemon") + $daemonArgs `
        -WorkingDirectory $projectRoot `
        -WindowStyle Hidden | Out-Null
}

function Ensure-DaemonRunning {
    $health = Get-DaemonHealth
    if ($null -ne $health) {
        return $health
    }

    Start-DaemonBackground
    $deadline = (Get-Date).AddSeconds($daemonStartupTimeoutSec)
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Milliseconds 250
        $health = Get-DaemonHealth
        if ($null -ne $health) {
            return $health
        }
    }

    throw "Timed out waiting for agent-computer daemon to become ready."
}

function Invoke-ProjectCli {
    param(
        [string[]]$CommandArgs
    )

    if (Test-Path $localCliExe) {
        & $localCliExe @CommandArgs
        return
    }

    if (Test-Path $localPythonExe) {
        Invoke-WithProjectPythonPath {
            & $localPythonExe -m agent_computer.cli @CommandArgs
        }
        return
    }

    if ($pathCliCommand) {
        & $pathCliCommand.Source @CommandArgs
        return
    }

    & conda run -p $localEnvRoot agent-computer @CommandArgs
}

function Test-ShouldBypassDaemonBootstrap {
    param(
        [string[]]$CommandArgs
    )

    if ($CommandArgs.Count -eq 0) {
        return $true
    }

    if ($CommandArgs -contains "-h" -or $CommandArgs -contains "--help") {
        return $true
    }

    $first = $CommandArgs[0]
    return $first -in @("daemon", "-h", "--help", "help")
}

if (-not (Test-ShouldBypassDaemonBootstrap -CommandArgs $Args)) {
    Ensure-DaemonRunning | Out-Null
}

Invoke-ProjectCli -CommandArgs $Args
exit $LASTEXITCODE
