# JARVIS first-time setup (Windows). Phase 6.1 skeleton.
# Usage: powershell -ExecutionPolicy Bypass -File scripts\Install-JARVIS.ps1
# Optional: -SkipCompose  (only checks + .env)

param(
    [switch]$SkipCompose,
    [switch]$StrictProd
)

$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root

function Step($msg) { Write-Host "`n== $msg ==" -ForegroundColor Cyan }

Step "Prerequisites"
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker Desktop not found. Install Docker Desktop first."
}
docker info 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Docker daemon not running. Start Docker Desktop." }
Write-Host "[OK] Docker running" -ForegroundColor Green

try {
    Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 3 | Out-Null
    Write-Host "[OK] Ollama reachable" -ForegroundColor Green
} catch {
    Write-Host "[WARN] Ollama not on :11434 — start Ollama with OLLAMA_VULKAN=1" -ForegroundColor Yellow
}

Step ".env"
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env from .env.example — fill TELEGRAM_BOT_TOKEN, HOSTAGENT_TOKEN" -ForegroundColor Yellow
} else {
    Write-Host "[OK] .env exists" -ForegroundColor Green
}

if ($StrictProd) {
    $lines = Get-Content .env -ErrorAction SilentlyContinue
    $dev = $lines | Where-Object { $_ -match "^WEBAPP_DEV_OPEN=true" }
    if ($dev) { throw "WEBAPP_DEV_OPEN=true — set false before prod (-StrictProd)" }
}

if (-not $SkipCompose) {
    Step "Docker Compose"
    docker compose up -d --build
    if ($LASTEXITCODE -ne 0) { throw "docker compose failed" }
    Start-Sleep -Seconds 8
    & "$PSScriptRoot\verify_stack.ps1" @($(if ($StrictProd) { "-StrictProd" }))
}

Step "Host-agent (manual)"
Write-Host @"
On Windows host (outside Docker):
  1. Set HOSTAGENT_TOKEN in .env (same as hostagent)
  2. cd hostagent; pip install -r requirements.txt
  3. uvicorn app.main:app --host 0.0.0.0 --port 8400
  4. scripts\install_autostart.ps1 for logon autostart
"@ -ForegroundColor Gray

Step "Next"
Write-Host "Telegram: set TELEGRAM_BOT_TOKEN, rotate if leaked (M4)." -ForegroundColor White
Write-Host "Mini App: PUBLIC_APP_URL + cloudflared (optional)." -ForegroundColor White
Write-Host "Smoke: docs\SMOKE_TEST.md" -ForegroundColor White
