# D.2 — symlink active LoRA artifact (Blue-Green on host).
# Usage: .\scripts\link_active_lora.ps1 -Source O:\JARVIS\data\twin\lora\v0.2.0

param(
    [Parameter(Mandatory = $true)][string]$Source,
    [string]$Target = "O:\JARVIS\data\twin\lora\active"
)

$ErrorActionPreference = "Stop"
if (-not (Test-Path $Source)) { throw "Source not found: $Source" }
$parent = Split-Path $Target -Parent
New-Item -ItemType Directory -Force -Path $parent | Out-Null
if (Test-Path $Target) { Remove-Item $Target -Force -Recurse }
New-Item -ItemType Junction -Path $Target -Target $Source | Out-Null
Write-Host "[OK] active -> $Source" -ForegroundColor Green
