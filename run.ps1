param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Args
)

$envPath = Join-Path $PSScriptRoot ".conda"
$agentComputerExe = Join-Path $envPath "Scripts\agent-computer.exe"
$pythonExe = Join-Path $envPath "python.exe"

if (Test-Path $agentComputerExe) {
    & $agentComputerExe @Args
    exit $LASTEXITCODE
}

if (Test-Path $pythonExe) {
    & $pythonExe -m agent_computer.cli @Args
    exit $LASTEXITCODE
}

& conda run -p $envPath agent-computer @Args
exit $LASTEXITCODE
