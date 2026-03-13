param(
    [string]$LocalHost = "127.0.0.1",
    [int]$LocalPort = 37688
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot
& .\windows-launcher.ps1 observation urls --host $LocalHost --port $LocalPort
