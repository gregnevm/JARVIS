# C.4 — eval gate then promote LoRA in Twin + Ollama deploy.
# Usage: .\scripts\gate_promote_lora.ps1 -Version v0.2.0 [-Holdout data/twin/export/sharegpt_holdout.jsonl]

param(
    [Parameter(Mandatory = $true)][string]$Version,
    [string]$Holdout = "data/twin/export/sharegpt_holdout.jsonl",
    [string]$TwinUrl = "http://127.0.0.1:8765",
    [string]$ToolsUrl = "http://127.0.0.1:8300",
    # Додатково вимагати task-success проти live-стека (COMPETITIVE_ANALYSIS §3.8):
    # промоутимо лише якщо система досі корисна, а не лише формат-чиста.
    [switch]$WithTaskSuccess,
    [double]$TaskSuccessMinPct = 90,
    [switch]$SkipDeploy
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (Test-Path $Holdout) {
    $gateArgs = @("training/eval/gate.py", "--holdout", $Holdout)
    if ($WithTaskSuccess) {
        $gateArgs += @("--with-task-success", "--task-success-min-pct", $TaskSuccessMinPct)
    }
    python @gateArgs
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} else {
    Write-Host "[WARN] holdout missing — skip eval gate" -ForegroundColor Yellow
}

$r = Invoke-RestMethod -Method Post -Uri "$TwinUrl/registry/lora/$Version/promote" -TimeoutSec 15
Write-Host "[OK] promoted $($r.version) status=$($r.status)" -ForegroundColor Green

if (-not $SkipDeploy) {
    try {
        $d = Invoke-RestMethod -Method Post -Uri "$ToolsUrl/lora/deploy" -ContentType "application/json" -Body "{}" -TimeoutSec 180
        Write-Host "[OK] ollama model $($d.model)" -ForegroundColor Green
    } catch {
        Write-Host "[WARN] ollama deploy failed: $_" -ForegroundColor Yellow
        exit 2
    }
}
