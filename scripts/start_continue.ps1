# Idempotent start Continue agent API (cn serve) for JARVIS continue_dev.
#   .\scripts\start_continue.ps1

$ErrorActionPreference = 'Continue'
$root = Split-Path $PSScriptRoot -Parent
. (Join-Path $PSScriptRoot 'lib\jarvis_continue.ps1')

$logDir = Join-Path $root 'data\logs'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$logFile = Join-Path $logDir 'continue-serve.log'

function Log($m) {
    $line = '{0} {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $m
    Add-Content -LiteralPath $logFile -Value $line -Encoding UTF8
    Write-Host $line
}

$cfg = Import-ContinueEnvFromDotenv -Root $root
if ($cfg.ENABLE_CONTINUE_DEV -ne 'true') {
    Write-Host '[skip] ENABLE_CONTINUE_DEV=false' -ForegroundColor Gray
    exit 0
}

if ($cfg.CONTINUE_API_KEY) { $env:CONTINUE_API_KEY = $cfg.CONTINUE_API_KEY }

$ok = Start-ContinueServe -Root $root -Cfg $cfg -Log ${function:Log}
if ($ok) { exit 0 }
exit 1
