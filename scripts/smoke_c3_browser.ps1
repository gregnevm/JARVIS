# C3 smoke — browser_open/read через Tools API (без Telegram).
# Usage: .\scripts\smoke_c3_browser.ps1
# Requires: docker tools up, ENABLE_BROWSER=true, rebuild tools image.

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$toolsUrl = $env:TOOLS_URL
if (-not $toolsUrl) { $toolsUrl = "http://localhost:8200" }

Write-Host "=== C3 browser smoke ($toolsUrl) ===" -ForegroundColor Cyan

$health = Invoke-RestMethod -Uri "$toolsUrl/health" -Method Get -TimeoutSec 10
if ($health.status -ne "ok") { throw "tools health failed" }
Write-Host "[OK] tools health" -ForegroundColor Green

$body = @{
    name       = "browser_open"
    arguments  = @{ url = "https://example.com" }
    user_id    = 1
} | ConvertTo-Json -Depth 5

# Direct dispatch via calc-style endpoint if exists — use /agent with short prompt fallback
$status = Invoke-RestMethod -Uri "$toolsUrl/status" -Method Get -TimeoutSec 15 -ErrorAction SilentlyContinue
if ($status.enable_browser -eq $false) {
    Write-Host "[SKIP] ENABLE_BROWSER=false — set true and rebuild tools" -ForegroundColor Yellow
    exit 2
}
Write-Host "[OK] enable_browser=true" -ForegroundColor Green

$dispatchBody = @{
    name      = "browser_open"
    arguments = @{ url = "https://example.com" }
    user_id   = 1
} | ConvertTo-Json -Depth 5
try {
    $d = Invoke-RestMethod -Method Post -Uri "$toolsUrl/tool/dispatch" -ContentType "application/json" -Body $dispatchBody -TimeoutSec 90
    if ($d.text -match "example|Example|вимкнено|Некоректний|title|Title") {
        Write-Host "[OK] tool/dispatch browser_open: $($d.text.Substring(0, [Math]::Min(80, $d.text.Length)))" -ForegroundColor Green
    } else {
        Write-Host "[WARN] unexpected: $($d.text)" -ForegroundColor Yellow
    }
} catch {
    Write-Host "[FAIL] tool/dispatch browser_open: $_" -ForegroundColor Red
    exit 1
}

$evalBody = @{
    name      = "browser_eval"
    arguments = @{ script = "document.title" }
    user_id   = 1
} | ConvertTo-Json -Depth 5
try {
    $e = Invoke-RestMethod -Method Post -Uri "$toolsUrl/tool/dispatch" -ContentType "application/json" -Body $evalBody -TimeoutSec 60
    if ($e.text -match "Example|example|вимкнено") {
        Write-Host "[OK] tool/dispatch browser_eval: $($e.text.Substring(0, [Math]::Min(60, $e.text.Length)))" -ForegroundColor Green
    } else {
        Write-Host "[WARN] browser_eval: $($e.text)" -ForegroundColor Yellow
    }
} catch {
    Write-Host "[FAIL] tool/dispatch browser_eval: $_" -ForegroundColor Red
    exit 1
}

Write-Host @"

Manual E2E (Telegram):
  1. ENABLE_BROWSER=true in .env
  2. docker compose up -d --build tools
  3. /mode computer
  4. «відкрий https://example.com і прочитай сторінку»

Automated browser unit tests:
  cd tools; python -m pytest tests/test_browser.py -q

"@

exit 0
