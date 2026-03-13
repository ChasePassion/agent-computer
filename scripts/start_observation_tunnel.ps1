param(
    [string]$RelayHost,
    [string]$RelayUser,
    [int]$SshPort = 22,
    [int]$RelayPort = 43768,
    [string]$LocalHost = "127.0.0.1",
    [int]$LocalPort = 37688
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$configPath = Join-Path $projectRoot ".agent\observation.remote.json"

if (Test-Path $configPath) {
    $config = Get-Content $configPath -Raw | ConvertFrom-Json
    if (-not $RelayHost -and $config.relay_host) { $RelayHost = [string]$config.relay_host }
    if (-not $RelayUser -and $config.relay_user) { $RelayUser = [string]$config.relay_user }
    if ($PSBoundParameters.ContainsKey("SshPort") -eq $false -and $config.ssh_port) { $SshPort = [int]$config.ssh_port }
    if ($PSBoundParameters.ContainsKey("RelayPort") -eq $false -and $config.relay_port) { $RelayPort = [int]$config.relay_port }
    if ($PSBoundParameters.ContainsKey("LocalHost") -eq $false -and $config.local_host) { $LocalHost = [string]$config.local_host }
    if ($PSBoundParameters.ContainsKey("LocalPort") -eq $false -and $config.local_port) { $LocalPort = [int]$config.local_port }
}

if (-not $RelayHost) {
    throw "Missing RelayHost. Pass -RelayHost or create .agent/observation.remote.json."
}

if (-not $RelayUser) {
    throw "Missing RelayUser. Pass -RelayUser or create .agent/observation.remote.json."
}

$target = "{0}@{1}" -f $RelayUser, $RelayHost
$remoteSpec = "127.0.0.1:{0}:{1}:{2}" -f $RelayPort, $LocalHost, $LocalPort

Write-Host "Opening reverse SSH tunnel to $target ..."
Write-Host "Remote: 127.0.0.1:$RelayPort -> Local: $LocalHost`:$LocalPort"
Write-Host ""
Write-Host "Keep this window open while you need remote access."

ssh -N `
    -p $SshPort `
    -o ServerAliveInterval=30 `
    -o ExitOnForwardFailure=yes `
    -R $remoteSpec `
    $target
