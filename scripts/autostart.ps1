# JARVIS autostart - brings the whole stack up at Windows logon.
#   1) Ollama serve (0.0.0.0:11434, keep_alive 24h, Vulkan)
#   2) Docker Desktop engine + wait until ready
#   3) docker compose up -d
# Idempotent: safe to re-run (nothing is duplicated).
# Register as scheduled task: scripts/install_autostart.ps1

$ErrorActionPreference = 'Continue'
$root = Split-Path $PSScriptRoot -Parent
$log = Join-Path $root 'data\autostart.log'
New-Item -ItemType Directory -Force -Path (Split-Path $log) | Out-Null

function Log($m) {
    $line = "{0} {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $m
    Add-Content -Path $log -Value $line
    Write-Host $line
}

Log "=== autostart start ==="

# --- 1) Ollama ---
$env:OLLAMA_HOST = '0.0.0.0:11434'
$env:OLLAMA_KEEP_ALIVE = '24h'
$env:OLLAMA_VULKAN = '1'
$ollama = Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe'
if (Get-Process ollama -ErrorAction SilentlyContinue) {
    Log "Ollama: already running"
} elseif (Test-Path $ollama) {
    Start-Process -FilePath $ollama -ArgumentList 'serve' -WindowStyle Hidden
    Log "Ollama: started"
} else {
    Log "Ollama: exe not found ($ollama)"
}

# --- 2) Docker Desktop engine ---
function Test-DockerEngine {
    docker info --format '{{.ServerVersion}}' 2>$null | Out-Null
    return $LASTEXITCODE -eq 0
}

if (Test-DockerEngine) {
    Log "Docker engine: already up"
} else {
    $dd = 'C:\Program Files\Docker\Docker\Docker Desktop.exe'
    if (Test-Path $dd) {
        Start-Process -FilePath $dd
        Log "Docker Desktop: launching, waiting for engine..."
    } else {
        Log "Docker Desktop: exe not found ($dd)"
    }
    for ($i = 0; $i -lt 60; $i++) {
        Start-Sleep -Seconds 3
        if (Test-DockerEngine) { break }
    }
    if (Test-DockerEngine) { Log "Docker engine: up" }
    else { Log "Docker engine: NOT up after ~180s" }
}

# --- 3) Compose up ---
if (Test-DockerEngine) {
    Set-Location $root
    docker compose up -d 2>&1 | ForEach-Object { Log "compose: $_" }
    Log "compose up -d done"
} else {
    Log "Skipping compose: engine unavailable"
}

# --- 4) Ollama API health ---
for ($i = 0; $i -lt 15; $i++) {
    try {
        Invoke-RestMethod 'http://localhost:11434/api/tags' -TimeoutSec 4 | Out-Null
        Log "Ollama API: ok"
        break
    } catch { Start-Sleep -Seconds 2 }
}

Log "=== autostart done ==="
