# Memory Alembic (Phase 3.3)
param(
    [string]$Service = "memory"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)

Write-Host "Alembic upgrade head via docker compose exec $Service ..."
docker compose -f (Join-Path $Root "docker-compose.yml") exec -T $Service `
    python -c "from app.migrate import upgrade_head; upgrade_head(); print('ok')"
