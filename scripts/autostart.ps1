# JARVIS autostart — idempotent bring-up (safe to re-run).
#   1) Ollama serve (0.0.0.0:11434, keep_alive 24h, Vulkan)
#   2) Docker Desktop engine + wait until ready
#   3) docker compose up -d
#   4) host-agent on Windows (127.0.0.1:8400)
#   5) Ollama API health check
# Register watchdog: scripts/install_autostart.ps1

$ErrorActionPreference = 'Continue'
$root = Split-Path $PSScriptRoot -Parent
$log = Join-Path $root 'data\autostart.log'
New-Item -ItemType Directory -Force -Path (Split-Path $log) | Out-Null

function Log($m) {
    $line = "{0} {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $m
    Add-Content -Path $log -Value $line
    Write-Host $line
}

function Import-JarvisEnvLine {
    param([string]$Line)
    $t = $Line.Trim()
    if (-not $t -or $t.StartsWith('#')) { return }
    $eq = $t.IndexOf('=')
    if ($eq -lt 1) { return }
    $name = $t.Substring(0, $eq).Trim()
    $value = $t.Substring($eq + 1).Trim()
    if ($value.Length -ge 2) {
        if (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'"))) {
            $value = $value.Substring(1, $value.Length - 2)
        }
    }
    Set-Item -Path "Env:$name" -Value $value
}

function Import-JarvisEnv {
    param([string]$EnvPath)
    if (-not (Test-Path $EnvPath)) { return }
    Get-Content -LiteralPath $EnvPath -Encoding UTF8 | ForEach-Object { Import-JarvisEnvLine $_ }
}

function Test-HostagentHealth {
    param([string]$BindHost = '127.0.0.1', [int]$Port = 8400)
    try {
        $uri = "http://${BindHost}:${Port}/health"
        Invoke-RestMethod -Uri $uri -TimeoutSec 3 | Out-Null
        return $true
    } catch {
        return $false
    }
}

function Ensure-HostagentPython {
    $py = Get-Command python -ErrorAction SilentlyContinue
    if (-not $py) {
        Log "hostagent: python not found on PATH"
        return $false
    }
    & python -c "import uvicorn, fastapi" 2>$null
    if ($LASTEXITCODE -ne 0) {
        $req = Join-Path $root 'hostagent\requirements.txt'
        if (-not (Test-Path $req)) {
            Log "hostagent: requirements.txt missing"
            return $false
        }
        Log "hostagent: installing pip deps..."
        & python -m pip install -q -r $req 2>&1 | ForEach-Object { Log "hostagent pip: $_" }
    }
    return $true
}

function Start-JarvisHostagent {
    $envPath = Join-Path $root '.env'
    Import-JarvisEnv $envPath

    $bind = if ($env:HOSTAGENT_BIND_HOST) { $env:HOSTAGENT_BIND_HOST } else { '127.0.0.1' }
    $port = 8400
    if ($env:HOSTAGENT_PORT) {
        [void][int]::TryParse($env:HOSTAGENT_PORT, [ref]$port)
    }

    if (Test-HostagentHealth -BindHost $bind -Port $port) {
        Log "hostagent: already healthy ($bind`:$port)"
        return
    }

    if (-not $env:HOSTAGENT_TOKEN) {
        Log "hostagent: skipped (HOSTAGENT_TOKEN missing in .env)"
        return
    }

    if (-not (Ensure-HostagentPython)) { return }

    $workDir = Join-Path $root 'hostagent'
    if (-not (Test-Path (Join-Path $workDir 'app\main.py'))) {
        Log "hostagent: app not found ($workDir)"
        return
    }

    $args = @('-m', 'uvicorn', 'app.main:app', '--host', $bind, '--port', "$port")
    Start-Process -FilePath 'python' -ArgumentList $args -WorkingDirectory $workDir -WindowStyle Hidden
    Log "hostagent: started ($bind`:$port)"

    for ($i = 0; $i -lt 20; $i++) {
        Start-Sleep -Seconds 1
        if (Test-HostagentHealth -BindHost $bind -Port $port) {
            Log "hostagent: healthy"
            return
        }
    }
    Log "hostagent: started but health check failed after 20s"
}

$accessDir = Join-Path $root 'data\access'
New-Item -ItemType Directory -Force -Path $accessDir | Out-Null

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

# --- 4) Host-agent (Windows, outside Docker) ---
Start-JarvisHostagent

# --- 5) Ollama API health ---
for ($i = 0; $i -lt 15; $i++) {
    try {
        Invoke-RestMethod 'http://localhost:11434/api/tags' -TimeoutSec 4 | Out-Null
        Log "Ollama API: ok"
        break
    } catch { Start-Sleep -Seconds 2 }
}

Log "=== autostart done ==="
