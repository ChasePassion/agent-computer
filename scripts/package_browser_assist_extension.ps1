param(
    [string]$WsUrl,
    [string]$OutputDir = "artifacts\browser-assist-locator-package"
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$sourceDir = Join-Path $projectRoot "extensions\browser-assist-locator"
$configPath = Join-Path $projectRoot ".agent\browser_assist.json"
$resolvedOutputDir = Join-Path $projectRoot $OutputDir
$buildDir = Join-Path $resolvedOutputDir "browser-assist-locator"
$zipPath = Join-Path $resolvedOutputDir "browser-assist-locator.zip"
$daemonHost = if ($env:AGENT_COMPUTER_HOST) { [string]$env:AGENT_COMPUTER_HOST } else { "127.0.0.1" }
$daemonPort = if ($env:AGENT_COMPUTER_PORT) { [int]$env:AGENT_COMPUTER_PORT } else { 37688 }
$daemonBaseUrl = "http://{0}:{1}" -f $daemonHost, $daemonPort

if (-not (Test-Path $sourceDir)) {
    throw "Browser Assist extension source directory not found: $sourceDir"
}

if ([string]::IsNullOrWhiteSpace($WsUrl)) {
    if (-not (Test-Path $configPath)) {
        throw "Browser Assist config not found. Start the daemon once or pass -WsUrl explicitly."
    }

    $config = Get-Content $configPath -Raw | ConvertFrom-Json
    $token = [string]$config.token
    if ([string]::IsNullOrWhiteSpace($token)) {
        throw "Browser Assist token is missing in $configPath"
    }

    $WsUrl = "ws://{0}:{1}/ws/browser-assist?token={2}" -f $daemonHost, $daemonPort, $token
}

if (Test-Path $resolvedOutputDir) {
    Remove-Item $resolvedOutputDir -Recurse -Force
}

New-Item -ItemType Directory -Path $buildDir -Force | Out-Null
Copy-Item (Join-Path $sourceDir "*") -Destination $buildDir -Recurse -Force

$serviceWorkerPath = Join-Path $buildDir "service_worker.js"
$serviceWorker = Get-Content $serviceWorkerPath -Raw
$serviceWorker = $serviceWorker.Replace("__BROWSER_ASSIST_WS_URL__", $WsUrl)
$serviceWorker = $serviceWorker.Replace("__BROWSER_ASSIST_DAEMON_BASE_URL__", $daemonBaseUrl)
Set-Content -Path $serviceWorkerPath -Value $serviceWorker -Encoding UTF8

Compress-Archive -Path (Join-Path $buildDir "*") -DestinationPath $zipPath -Force

Write-Output "Browser Assist extension packaged."
Write-Output "Build directory: $buildDir"
Write-Output "Zip archive: $zipPath"
Write-Output "Daemon base URL: $daemonBaseUrl"
Write-Output "WebSocket URL: $WsUrl"
