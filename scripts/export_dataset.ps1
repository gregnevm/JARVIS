# Export session logs to ShareGPT JSONL for Twin training.
# Usage: .\scripts\export_dataset.ps1 [-UserId 123456789]

param([int]$UserId = 0)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$args = @()
if ($UserId -gt 0) { $args += "--user-id", $UserId }

python training/export_sessions.py @args
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "[OK] dataset under data/twin/export/" -ForegroundColor Green
