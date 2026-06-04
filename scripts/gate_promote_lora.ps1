# C.4 — eval gate then promote LoRA in Twin.
# Usage: .\scripts\gate_promote_lora.ps1 -Version v0.2.0 [-Holdout data/twin/export/sharegpt_holdout.jsonl]

param(
    [Parameter(Mandatory = $true)][string]$Version,
    [string]$Holdout = "data/twin/export/sharegpt_holdout.jsonl",
    [string]$TwinUrl = "http://127.0.0.1:8765"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (Test-Path $Holdout) {
    python training/eval/gate.py --holdout $Holdout
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} else {
    Write-Host "[WARN] holdout missing — skip eval gate" -ForegroundColor Yellow
}

$r = Invoke-RestMethod -Method Post -Uri "$TwinUrl/registry/lora/$Version/promote" -TimeoutSec 15
Write-Host "[OK] promoted $($r.version) status=$($r.status)" -ForegroundColor Green
