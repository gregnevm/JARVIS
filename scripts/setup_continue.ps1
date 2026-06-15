# One-time / idempotent setup for Continue.dev + JARVIS continue_dev tool.
#   .\scripts\setup_continue.ps1          # install cn, check auth, start serve
#   .\scripts\setup_continue.ps1 -Login   # open browser login (interactive)

param([switch]$Login)

$ErrorActionPreference = 'Continue'
$root = Split-Path $PSScriptRoot -Parent
. (Join-Path $PSScriptRoot 'lib\jarvis_continue.ps1')

$logDir = Join-Path $root 'data\logs'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$logFile = Join-Path $logDir 'continue-setup.log'

function Log($m) {
    $line = '{0} {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $m
    Add-Content -LiteralPath $logFile -Value $line -Encoding UTF8
    Write-Host $line
}

Log '=== setup_continue start ==='
$cfg = Import-ContinueEnvFromDotenv -Root $root

if ($cfg.ENABLE_CONTINUE_DEV -ne 'true') {
    Log 'ENABLE_CONTINUE_DEV is not true — enable in .env first'
    Write-Host @'

Add to .env:
  ENABLE_CONTINUE_DEV=true
  CONTINUE_DEV_URL=http://host.docker.internal:65432

'@ -ForegroundColor Yellow
    exit 1
}

if (-not (Install-ContinueCn)) { exit 1 }
Log ('cn: ' + (Get-ContinueCnCommand))

if ($cfg.CONTINUE_API_KEY) {
    $env:CONTINUE_API_KEY = $cfg.CONTINUE_API_KEY
    Log 'CONTINUE_API_KEY found in .env (cloud Continue account)'
} elseif ($Login) {
    Log 'Launching cn login (complete in browser)...'
    $cn = Get-ContinueCnCommand
    Start-Process -FilePath $cn -ArgumentList 'login' -Wait
} else {
    Log 'Local Ollama mode: writing ~/.continue/config.yaml'
    if (-not (Ensure-ContinueLocalConfig -Root $root -Cfg $cfg -Force)) {
        Log 'Failed to write local Continue config'
        exit 1
    }
    Log ("Local config: Ollama model=$($cfg.OLLAMA_MODEL_AGENT) @ 127.0.0.1:11434")
}

if (-not (Test-ContinueReady -EnvVars $cfg)) {
    Log 'Continue not ready'
    Write-Host @'

Опції (одна з):

  Локальна Ollama (рекомендовано, без API):
    powershell -File scripts/setup_continue.ps1

  Continue акаунт у браузері:
    powershell -File scripts/setup_continue.ps1 -Login

  Headless cloud Continue (не для локальної моделі):
    CONTINUE_API_KEY=con_... у .env

'@ -ForegroundColor Yellow
    exit 2
}

$start = Join-Path $PSScriptRoot 'start_continue.ps1'
if (Test-Path $start) {
    & powershell -NoProfile -ExecutionPolicy Bypass -File $start
}

Log '=== setup_continue done ==='
exit 0
