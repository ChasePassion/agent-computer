param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Args
)

$ErrorActionPreference = "Stop"

$script:originalArgs = @($Args)
$projectRoot = $PSScriptRoot
$envPath = Join-Path $projectRoot ".conda"
$agentComputerExe = Join-Path $envPath "Scripts\agent-computer.exe"
$daemonExe = Join-Path $envPath "Scripts\agent-computer-daemon.exe"
$pythonExe = Join-Path $envPath "python.exe"
$daemonHost = if ($env:AGENT_COMPUTER_HOST) { $env:AGENT_COMPUTER_HOST } else { "127.0.0.1" }
$daemonPort = if ($env:AGENT_COMPUTER_PORT) { [int]$env:AGENT_COMPUTER_PORT } else { 37688 }
$daemonStartupTimeoutSec = if ($env:AGENT_COMPUTER_STARTUP_TIMEOUT_SEC) {
    [double]$env:AGENT_COMPUTER_STARTUP_TIMEOUT_SEC
} else {
    15.0
}
$script:daemonBaseUrl = "http://{0}:{1}" -f $daemonHost, $daemonPort

function Invoke-LegacyCli {
    if (Test-Path $agentComputerExe) {
        & $agentComputerExe @script:originalArgs
        exit $LASTEXITCODE
    }

    if (Test-Path $pythonExe) {
        & $pythonExe -m agent_computer.cli @script:originalArgs
        exit $LASTEXITCODE
    }

    & conda run -p $envPath agent-computer @script:originalArgs
    exit $LASTEXITCODE
}

function Write-PrettyJson {
    param([object]$Payload)

    $Payload | ConvertTo-Json -Depth 100
}

function Convert-OptionValue {
    param(
        [string]$RawValue,
        [string]$ValueType
    )

    switch ($ValueType) {
        "int" { return [int]$RawValue }
        "float" { return [double]$RawValue }
        default { return $RawValue }
    }
}

function Parse-Options {
    param(
        [string[]]$CommandArgs,
        [hashtable]$AliasToKey,
        [string[]]$Flags = @(),
        [hashtable]$Types = @{},
        [hashtable]$Defaults = @{},
        [string[]]$RequiredKeys = @(),
        [string]$PositionalField = $null
    )

    $payload = @{}
    foreach ($item in $Defaults.GetEnumerator()) {
        $payload[$item.Key] = $item.Value
    }

    $flagLookup = @{}
    foreach ($flag in $Flags) {
        $flagLookup[$flag] = $true
    }

    $positionals = [System.Collections.Generic.List[string]]::new()
    $index = 0
    while ($index -lt $CommandArgs.Count) {
        $token = $CommandArgs[$index]
        if ($token.StartsWith("--")) {
            $optionName = $token.Substring(2)
            if (-not $AliasToKey.ContainsKey($optionName)) {
                throw "Unsupported option: --$optionName"
            }

            $key = $AliasToKey[$optionName]
            if ($flagLookup.ContainsKey($optionName)) {
                $payload[$key] = $true
                $index += 1
                continue
            }

            if ($index + 1 -ge $CommandArgs.Count) {
                throw "Missing value for --$optionName"
            }

            $rawValue = $CommandArgs[$index + 1]
            $valueType = if ($Types.ContainsKey($key)) { $Types[$key] } else { "string" }
            $payload[$key] = Convert-OptionValue -RawValue $rawValue -ValueType $valueType
            $index += 2
            continue
        }

        if (-not $PositionalField) {
            throw "Unexpected positional argument: $token"
        }

        $positionals.Add($token)
        $index += 1
    }

    if ($PositionalField) {
        $payload[$PositionalField] = @($positionals)
    }

    foreach ($requiredKey in $RequiredKeys) {
        if (-not $payload.ContainsKey($requiredKey)) {
            throw "Missing required option: $requiredKey"
        }

        $value = $payload[$requiredKey]
        if ($null -eq $value) {
            throw "Missing required option: $requiredKey"
        }

        if ($value -is [string] -and [string]::IsNullOrWhiteSpace($value)) {
            throw "Missing required option: $requiredKey"
        }

        if ($value -is [System.Array] -and $value.Count -eq 0) {
            throw "Missing required option: $requiredKey"
        }
    }

    return $payload
}

function Get-DaemonHealth {
    try {
        return Invoke-RestMethod -Uri ("{0}/system/health" -f $script:daemonBaseUrl) -Method Get
    } catch {
        return $null
    }
}

function Start-DaemonBackground {
    if (Test-Path $daemonExe) {
        Start-Process -FilePath $daemonExe `
            -ArgumentList @("--host", $daemonHost, "--port", [string]$daemonPort) `
            -WorkingDirectory $projectRoot `
            -WindowStyle Hidden | Out-Null
        return
    }

    if (Test-Path $pythonExe) {
        Start-Process -FilePath $pythonExe `
            -ArgumentList @("-m", "agent_computer.daemon", "--host", $daemonHost, "--port", [string]$daemonPort) `
            -WorkingDirectory $projectRoot `
            -WindowStyle Hidden | Out-Null
        return
    }

    Start-Process -FilePath "conda" `
        -ArgumentList @("run", "-p", $envPath, "python", "-m", "agent_computer.daemon", "--host", $daemonHost, "--port", [string]$daemonPort) `
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

function Invoke-DaemonRequest {
    param(
        [string]$Method,
        [string]$Path,
        [object]$Body = $null
    )

    Ensure-DaemonRunning | Out-Null
    $uri = "{0}{1}" -f $script:daemonBaseUrl, $Path

    if ($null -eq $Body) {
        $response = Invoke-RestMethod -Uri $uri -Method $Method
    } else {
        $jsonBody = $Body | ConvertTo-Json -Depth 100 -Compress
        $response = Invoke-RestMethod -Uri $uri -Method $Method -ContentType "application/json; charset=utf-8" -Body $jsonBody
    }

    Write-PrettyJson $response
}

if ($Args.Count -eq 0) {
    Invoke-LegacyCli
}

$command = $Args[0]
$commandArgs = if ($Args.Count -gt 1) { $Args[1..($Args.Count - 1)] } else { @() }

if ($command -eq "daemon") {
    Invoke-LegacyCli
}

try {
    switch ($command) {
        "capture" {
            $payload = Parse-Options -CommandArgs $commandArgs `
                -AliasToKey @{
                    "output" = "output"
                    "target" = "target"
                    "window-title" = "window_title"
                    "window-exact" = "window_exact"
                    "grid" = "grid"
                    "grid-size" = "grid_size"
                    "format" = "format"
                    "jpeg-quality" = "jpeg_quality"
                } `
                -Flags @("window-exact", "grid") `
                -Types @{
                    "grid_size" = "int"
                    "jpeg_quality" = "int"
                } `
                -Defaults @{
                    "target" = "active-window"
                    "window_exact" = $false
                    "grid" = $false
                    "grid_size" = 50
                    "format" = "png"
                    "jpeg_quality" = 75
                }
            Invoke-DaemonRequest -Method POST -Path "/capture" -Body $payload
            break
        }

        "capture-preview" {
            $payload = Parse-Options -CommandArgs $commandArgs `
                -AliasToKey @{
                    "output" = "output"
                    "jpeg-quality" = "jpeg_quality"
                } `
                -Types @{
                    "jpeg_quality" = "int"
                } `
                -Defaults @{
                    "jpeg_quality" = 75
                }
            Invoke-DaemonRequest -Method POST -Path "/capture/preview" -Body $payload
            break
        }

        "capture-grid" {
            $payload = Parse-Options -CommandArgs $commandArgs `
                -AliasToKey @{
                    "output" = "output"
                    "grid-size" = "grid_size"
                    "jpeg-quality" = "jpeg_quality"
                } `
                -Types @{
                    "grid_size" = "int"
                    "jpeg_quality" = "int"
                } `
                -Defaults @{
                    "grid_size" = 50
                    "jpeg_quality" = 75
                }
            Invoke-DaemonRequest -Method POST -Path "/capture/grid" -Body $payload
            break
        }

        "windows" {
            if ($commandArgs.Count -gt 0) {
                throw "windows does not accept additional arguments."
            }
            Invoke-DaemonRequest -Method GET -Path "/navigation/windows"
            break
        }

        "focus" {
            $payload = Parse-Options -CommandArgs $commandArgs `
                -AliasToKey @{
                    "title" = "title"
                    "exact" = "exact"
                } `
                -Flags @("exact") `
                -Defaults @{
                    "exact" = $false
                } `
                -RequiredKeys @("title")
            Invoke-DaemonRequest -Method POST -Path "/navigation/focus" -Body $payload
            break
        }

        "move" {
            $payload = Parse-Options -CommandArgs $commandArgs `
                -AliasToKey @{
                    "x" = "x"
                    "y" = "y"
                    "duration" = "duration"
                } `
                -Types @{
                    "x" = "int"
                    "y" = "int"
                    "duration" = "float"
                } `
                -Defaults @{
                    "duration" = 0.0
                } `
                -RequiredKeys @("x", "y")
            Invoke-DaemonRequest -Method POST -Path "/actions/move" -Body $payload
            break
        }

        "click" {
            $payload = Parse-Options -CommandArgs $commandArgs `
                -AliasToKey @{
                    "x" = "x"
                    "y" = "y"
                    "button" = "button"
                    "double" = "double"
                } `
                -Flags @("double") `
                -Types @{
                    "x" = "int"
                    "y" = "int"
                } `
                -Defaults @{
                    "button" = "left"
                    "double" = $false
                } `
                -RequiredKeys @("x", "y")
            Invoke-DaemonRequest -Method POST -Path "/actions/click" -Body $payload
            break
        }

        "scroll" {
            $payload = Parse-Options -CommandArgs $commandArgs `
                -AliasToKey @{
                    "amount" = "amount"
                } `
                -Types @{
                    "amount" = "int"
                } `
                -RequiredKeys @("amount")
            Invoke-DaemonRequest -Method POST -Path "/actions/scroll" -Body $payload
            break
        }

        "type" {
            $payload = Parse-Options -CommandArgs $commandArgs `
                -AliasToKey @{
                    "text" = "text"
                    "interval" = "interval"
                } `
                -Types @{
                    "interval" = "float"
                } `
                -Defaults @{
                    "interval" = 0.02
                } `
                -RequiredKeys @("text")
            Invoke-DaemonRequest -Method POST -Path "/actions/type" -Body $payload
            break
        }

        "paste" {
            $payload = Parse-Options -CommandArgs $commandArgs `
                -AliasToKey @{
                    "text" = "text"
                    "restore-clipboard" = "restore_clipboard"
                } `
                -Flags @("restore-clipboard") `
                -Defaults @{
                    "restore_clipboard" = $false
                } `
                -RequiredKeys @("text")
            Invoke-DaemonRequest -Method POST -Path "/actions/paste" -Body $payload
            break
        }

        "open-url" {
            $payload = Parse-Options -CommandArgs $commandArgs `
                -AliasToKey @{
                    "url" = "url"
                    "restore-clipboard" = "restore_clipboard"
                } `
                -Flags @("restore-clipboard") `
                -Defaults @{
                    "restore_clipboard" = $false
                } `
                -RequiredKeys @("url")
            Invoke-DaemonRequest -Method POST -Path "/navigation/open-url" -Body $payload
            break
        }

        "browser-back" {
            if ($commandArgs.Count -gt 0) {
                throw "browser-back does not accept additional arguments."
            }
            Invoke-DaemonRequest -Method POST -Path "/navigation/browser-back"
            break
        }

        "browser-forward" {
            if ($commandArgs.Count -gt 0) {
                throw "browser-forward does not accept additional arguments."
            }
            Invoke-DaemonRequest -Method POST -Path "/navigation/browser-forward"
            break
        }

        "browser-refresh" {
            if ($commandArgs.Count -gt 0) {
                throw "browser-refresh does not accept additional arguments."
            }
            Invoke-DaemonRequest -Method POST -Path "/navigation/browser-refresh"
            break
        }

        "press" {
            $payload = Parse-Options -CommandArgs $commandArgs `
                -AliasToKey @{
                    "key" = "key"
                } `
                -RequiredKeys @("key")
            Invoke-DaemonRequest -Method POST -Path "/actions/press" -Body $payload
            break
        }

        "hotkey" {
            $payload = Parse-Options -CommandArgs $commandArgs `
                -AliasToKey @{} `
                -PositionalField "keys" `
                -RequiredKeys @("keys")
            Invoke-DaemonRequest -Method POST -Path "/actions/hotkey" -Body $payload
            break
        }

        default {
            Invoke-LegacyCli
        }
    }
} catch {
    Write-Error $_
    exit 1
}
