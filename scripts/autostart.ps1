# JARVIS autostart — idempotent bring-up (safe to re-run).
#   -SkipVerify  skip verify_stack.ps1 at the end (faster logon)
#   1) Ollama serve (0.0.0.0:11434, keep_alive 24h, Vulkan)
#   2) Docker Desktop engine + wait until ready
#   3) docker compose up -d
#   4) host-agent on Windows (127.0.0.1:8400)
#   5) Ollama API health check
# Register watchdog: scripts/install_autostart.ps1

param([switch]$SkipVerify)

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

function Test-HostagentScreenEndpoint {
    param([string]$BindHost = '127.0.0.1', [int]$Port = 8400)
    try {
        $uri = "http://${BindHost}:${Port}/screen/capture"
        Invoke-WebRequest -Uri $uri -Method POST -UseBasicParsing -TimeoutSec 3 | Out-Null
        return $true
    } catch {
        $resp = $_.Exception.Response
        if ($resp -and $resp.StatusCode.value__ -eq 403) { return $true }
        return $false
    }
}

function Stop-HostagentListener {
    param([int]$Port = 8400)
    try {
        Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
            ForEach-Object {
                Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue
            }
    } catch { }
    Start-Sleep -Seconds 1
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

    $needScreen = ($env:ENABLE_COMPUTER_USE -eq 'true')
    $healthy = Test-HostagentHealth -BindHost $bind -Port $port
    $screenOk = (-not $needScreen) -or (Test-HostagentScreenEndpoint -BindHost $bind -Port $port)

    if ($healthy -and $screenOk) {
        Log "hostagent: already healthy $($bind):$port"
        return
    }

    if ($healthy -and -not $screenOk) {
        Log "hostagent: stale build (missing /screen/capture) - restarting"
        Stop-HostagentListener -Port $port
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
    Log "hostagent: started $($bind):$port"

    for ($i = 0; $i -lt 20; $i++) {
        Start-Sleep -Seconds 1
        if (Test-HostagentHealth -BindHost $bind -Port $port) {
            if ((-not $needScreen) -or (Test-HostagentScreenEndpoint -BindHost $bind -Port $port)) {
                Log "hostagent: healthy"
                return
            }
        }
    }
    Log "hostagent: started but health/capability check failed after 20s"
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

function Test-ForgeApi {
    try {
        Invoke-RestMethod 'http://127.0.0.1:7860/sdapi/v1/options' -TimeoutSec 4 | Out-Null
        return $true
    } catch { return $false }
}

function Start-SdForgeIfConfigured {
    $envPath = Join-Path $root '.env'
    Import-JarvisEnv $envPath
    $url = ($env:IMAGE_GEN_URL -as [string]).Trim().ToLower()
    if ($url -notmatch '7860' -and $url -notmatch 'host\.docker\.internal') { return }
    if (Test-ForgeApi) {
        Log 'sd-forge: API already up :7860'
        return
    }
    $start = Join-Path $root 'scripts\start_sd_forge.ps1'
    if (-not (Test-Path $start)) {
        Log 'sd-forge: start script missing'
        return
    }
    & powershell -NoProfile -ExecutionPolicy Bypass -File $start 2>&1 | ForEach-Object { Log "sd-forge: $_" }
}

# --- 4) SD Forge (локальні картинки, :7860) ---
Start-SdForgeIfConfigured

# --- 5) Host-agent (Windows, outside Docker) ---
Start-JarvisHostagent

# --- 6) Ollama API health ---
for ($i = 0; $i -lt 15; $i++) {
    try {
        Invoke-RestMethod 'http://localhost:11434/api/tags' -TimeoutSec 4 | Out-Null
        Log "Ollama API: ok"
        break
    } catch { Start-Sleep -Seconds 2 }
}

if (-not $SkipVerify) {
    $verify = Join-Path $root 'scripts\verify_stack.ps1'
    if (Test-Path $verify) {
        Log 'verify_stack: starting...'
        & powershell -NoProfile -ExecutionPolicy Bypass -File $verify 2>&1 | ForEach-Object { Log "verify: $_" }
        if ($LASTEXITCODE -eq 0) { Log 'verify_stack: ok' }
        else { Log "verify_stack: FAIL (exit $LASTEXITCODE)" }
    } else {
        Log 'verify_stack: script missing'
    }
} else {
    Log 'verify_stack: skipped (-SkipVerify)'
}

Log "=== autostart done ==="
