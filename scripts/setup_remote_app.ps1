# JARVIS — one-shot Mini App HTTPS (Tailscale Funnel або Cloudflare tunnel).
# Запуск: .\scripts\setup_remote_app.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$envFile = Join-Path $root ".env"

Write-Host "JARVIS Remote Mini App setup"
Write-Host "1) Підніми HTTPS reverse proxy на gateway :8000 (/app)"
Write-Host "2) Запиши PUBLIC_APP_URL=https://your-domain/app у .env"
Write-Host "3) docker compose restart gateway"
Write-Host ""
Write-Host "Tailscale Funnel (приклад):"
Write-Host "  tailscale funnel 8000"
Write-Host "  PUBLIC_APP_URL=https://<machine>.<tailnet>.ts.net/app"
Write-Host ""
Write-Host "Cloudflare named tunnel — див. README webhook-режим."

if (Test-Path $envFile) {
    $pub = (Select-String -Path $envFile -Pattern '^PUBLIC_APP_URL=' | Select-Object -First 1)
    if ($pub) { Write-Host "Поточний PUBLIC_APP_URL: $($pub.Line)" }
}
