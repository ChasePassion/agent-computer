param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Args
)

$ErrorActionPreference = "Stop"

$projectRoot = $PSScriptRoot
. (Join-Path $projectRoot "scripts\load_env.ps1")
Import-ProjectEnv -ProjectRoot $projectRoot
$localEnvRoot = Join-Path $projectRoot ".conda"
$localCliExe = Join-Path $localEnvRoot "Scripts\agent-computer.exe"
$localPythonExe = Join-Path $localEnvRoot "python.exe"
$projectPythonPath = Join-Path $projectRoot "src"
$pathSeparator = [IO.Path]::PathSeparator
$pathCliCommand = Get-Command "agent-computer" -ErrorAction SilentlyContinue

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

Invoke-ProjectCli -CommandArgs $Args
exit $LASTEXITCODE
