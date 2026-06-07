# Cursor task — локально на Windows-хості (без Telegram).
# Usage:
#   .\scripts\cursor_task.ps1 "Додай тести для cursor_tasks.py"
#   .\scripts\cursor_task.ps1 "Fix bug" -Sync

param(
    [Parameter(Mandatory = $true, Position = 0)][string]$Task,
    [string]$Cwd = "O:\JARVIS",
    [string]$Model = "composer-2.5",
    [switch]$Sync
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$py = Join-Path $root "scripts\cursor_run_task.py"
if (-not (Test-Path $py)) { throw "missing: $py" }

$args = @($py, "--task", $Task, "--cwd", $Cwd, "--model", $Model)
if ($env:CURSOR_API_KEY) {
    $args += @("--api-key", $env:CURSOR_API_KEY)
}

if ($Sync) {
    python @args
    exit $LASTEXITCODE
}

# Async — через tools API (Docker)
$body = @{
    user_id     = [int]($env:ADMIN_USER_IDS -split ',')[0]
    task        = $Task
    async_mode  = $true
} | ConvertTo-Json -Compress

try {
    $r = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8200/cursor/tasks" `
        -ContentType "application/json" -Body $body -TimeoutSec 30
    Write-Host "[OK] queued job $($r.job_id)" -ForegroundColor Green
} catch {
    Write-Host "[WARN] API failed, running sync locally..." -ForegroundColor Yellow
    python @args
    exit $LASTEXITCODE
}
