# JARVIS stack verification (.env + live services).
# Run: .\scripts\verify_stack.ps1

$ErrorActionPreference = "Continue"
Set-Location (Split-Path $PSScriptRoot -Parent)

$fail = 0
$warn = 0
function Ok($msg) { Write-Host "[OK]   $msg" -ForegroundColor Green }
function Bad($msg) { Write-Host "[FAIL] $msg" -ForegroundColor Red; $script:fail++ }
function Warn($msg) { Write-Host "[WARN] $msg" -ForegroundColor Yellow; $script:warn++ }

$envLines = Get-Content .env -ErrorAction SilentlyContinue
function EnvVal($k) {
    $l = $envLines | Where-Object { $_ -match "^$k=" } | Select-Object -First 1
    if ($l) { return ($l -split "=", 2)[1] }
    return ""
}

Write-Host "`n=== JARVIS verify_stack ===`n" -ForegroundColor Cyan

$ps = docker compose ps --format json 2>$null | ForEach-Object { $_ | ConvertFrom-Json }
foreach ($svc in @("gateway", "tools", "memory", "postgres", "redis", "whisper", "tts", "twin")) {
    $c = $ps | Where-Object { $_.Service -eq $svc }
    if (-not $c -or $c.State -ne "running") { Bad "compose: $svc"; continue }
    if ($c.Health -and $c.Health -ne "healthy") { Bad "compose: $svc health=$($c.Health)"; continue }
    Ok "compose: $svc"
}

foreach ($pair in @{
    gateway = "http://127.0.0.1:8000/health"
    tools   = "http://127.0.0.1:8200/health"
    memory  = "http://127.0.0.1:8100/health"
    twin    = "http://127.0.0.1:8765/health"
    tts     = "http://127.0.0.1:8300/health"
    whisper = "http://127.0.0.1:9000/"
}.GetEnumerator()) {
    try {
        $r = Invoke-WebRequest -Uri $pair.Value -TimeoutSec 8 -UseBasicParsing
        if ($r.StatusCode -ge 200 -and $r.StatusCode -lt 400) { Ok "http: $($pair.Key)" }
        else { Bad "http: $($pair.Key) status $($r.StatusCode)" }
    } catch { Bad "http: $($pair.Key) $($_.Exception.Message)" }
}

try {
    $tags = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 5
    Ok "ollama: $($tags.models.Count) models"
    foreach ($m in @("qwen2.5:7b-instruct", "nomic-embed-text", "qwen2.5vl:7b")) {
        $found = $tags.models | Where-Object { $_.name -eq $m -or $_.name -like "$m*" }
        if ($found) { Ok "ollama: $m" } else { Warn "ollama: missing $m" }
    }
} catch { Bad "ollama: $($_.Exception.Message)" }

try {
    $st = Invoke-RestMethod -Uri "http://127.0.0.1:8200/status" -TimeoutSec 10
    if ($st.ollama_up) { Ok "tools/status: ollama_up" } else { Bad "tools/status: ollama_up=false" }
    if ((EnvVal "ENABLE_COMPUTER_USE") -eq "true") {
        if ($st.hostagent_up) { Ok "tools/status: hostagent_up" }
        else { Bad "tools/status: hostagent_up=false (run hostagent\run.bat)" }
    }
} catch { Bad "tools/status: $($_.Exception.Message)" }

$tok = EnvVal "HOSTAGENT_TOKEN"
try {
    $h = Invoke-WebRequest -Uri "http://127.0.0.1:8400/health" -Headers @{ "X-Hostagent-Token" = $tok } -TimeoutSec 3 -UseBasicParsing
    if ($h.StatusCode -eq 200) { Ok "hostagent:8400" } else { Bad "hostagent: status $($h.StatusCode)" }
} catch {
    if ((EnvVal "ENABLE_COMPUTER_USE") -eq "true") { Bad "hostagent: down (Computer Use enabled)" }
    else { Warn "hostagent: down" }
}

try {
    $emb = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8100/embed" -ContentType "application/json" -Body '{"text":"test"}' -TimeoutSec 60
    if ($emb.dim -eq 768) { Ok "memory: embed dim=768" } else { Warn "memory: embed dim=$($emb.dim)" }
} catch { Bad "memory: embed $($_.Exception.Message)" }

try {
    $c = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8200/calc" -ContentType "application/json" -Body '{"expression":"2+2"}' -TimeoutSec 5
    if ($c.result -match "4") { Ok "tools: calc" } else { Bad "tools: calc bad result" }
} catch { Bad "tools: calc $($_.Exception.Message)" }

$igUrl = (EnvVal "IMAGE_GEN_URL").ToLower()
$igModel = EnvVal "IMAGE_GEN_MODEL"
if ($igUrl -match "7860") {
    try {
        Invoke-RestMethod -Uri "http://127.0.0.1:7860/sdapi/v1/options" -TimeoutSec 5 | Out-Null
        Ok "IMAGE_GEN: Forge local :7860"
    } catch {
        Bad "Forge not running - .\scripts\start_sd_forge.ps1"
    }
} elseif ($igUrl -eq "horde") {
    Ok "IMAGE_GEN: stable horde (cloud)"
} elseif ($igUrl -eq "pollinations") {
    Ok "IMAGE_GEN: pollinations (cloud)"
} elseif ($igUrl -eq "ollama") {
    if ($igModel) { Ok "IMAGE_GEN: ollama model=$igModel" }
    else { Bad "IMAGE_GEN_URL=ollama but IMAGE_GEN_MODEL empty" }
} elseif ([string]::IsNullOrWhiteSpace($igUrl)) {
    Warn "IMAGE_GEN off"
} else {
    try {
        Invoke-WebRequest -Uri "$igUrl/sdapi/v1/options" -TimeoutSec 3 -UseBasicParsing | Out-Null
        Ok "IMAGE_GEN: Forge/A1111 up"
    } catch { Bad "IMAGE_GEN_URL set but backend down" }
}

if ([string]::IsNullOrWhiteSpace((EnvVal "TELEGRAM_BOT_TOKEN"))) { Bad "TELEGRAM_BOT_TOKEN empty" }
else { Ok "telegram token set" }

if ([string]::IsNullOrWhiteSpace((EnvVal "PUBLIC_APP_URL"))) {
    Warn "PUBLIC_APP_URL empty - no Telegram Mini App menu button"
}

Write-Host "`nSummary: fail=$fail warn=$warn`n" -ForegroundColor Cyan
if ($fail -gt 0) { exit 1 }
exit 0
