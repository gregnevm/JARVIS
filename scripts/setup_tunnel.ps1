# Named Cloudflare tunnel for Telegram Mini App (PUBLIC_APP_URL).
# Prerequisites: Cloudflare Zero Trust account, tunnel token, hostname → http://gateway:8000
#
# Usage:
#   1. Set CLOUDFLARE_TUNNEL_TOKEN and PUBLIC_APP_URL=https://your.domain/app in .env
#   2. docker compose --profile tunnel up -d
#   3. docker compose up -d gateway  (recreate to register menu button)

param(
    [string]$EnvFile = (Join-Path $PSScriptRoot ".." ".env")
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $root

if (-not (Test-Path $EnvFile)) {
    Write-Error ".env not found at $EnvFile — copy .env.example first"
}

Write-Host "Starting Cloudflare tunnel profile (docker compose --profile tunnel)..."
docker compose --profile tunnel up -d

Write-Host ""
Write-Host "Next steps:"
Write-Host "  1. Ensure PUBLIC_APP_URL=https://<your-hostname>/app in .env"
Write-Host "  2. docker compose up -d gateway"
Write-Host "  3. In Telegram: /app or menu button Dashboard"
