# Continue.dev CLI helpers (cn serve for JARVIS continue_dev tool).
# Dot-source from setup_continue.ps1, start_continue.ps1, autostart.ps1

function Get-ContinueDevPort {
    param([string]$Url = 'http://host.docker.internal:65432')
    if ($Url -match ':(\d+)(?:/|$)') { return [int]$Matches[1] }
    return 65432
}

function Get-ContinueCnCommand {
    $candidates = @(
        (Join-Path $env:APPDATA 'npm\cn.cmd'),
        (Join-Path $env:USERPROFILE '.continue\bin\cn.exe'),
        (Get-Command cn.cmd -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source),
        (Get-Command cn -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source)
    ) | Where-Object { $_ -and (Test-Path $_) }
    if ($candidates) { return $candidates[0] }
    return $null
}

function Test-ContinueCnInstalled {
    return [bool](Get-ContinueCnCommand)
}

function Install-ContinueCn {
    if (Test-ContinueCnInstalled) { return $true }
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
        Write-Host '[FAIL] npm not found — install Node.js first' -ForegroundColor Red
        return $false
    }
    Write-Host 'Installing @continuedev/cli...' -ForegroundColor Cyan
    & npm install -g @continuedev/cli 2>&1 | ForEach-Object { Write-Host $_ }
    return (Test-ContinueCnInstalled)
}

function Test-ContinueApi {
    param(
        [string]$BindHost = '127.0.0.1',
        [int]$Port = 65432,
        [switch]$AllowMock
    )
    try {
        $state = Invoke-RestMethod -Uri "http://${BindHost}:${Port}/state" -TimeoutSec 4
        if (-not $AllowMock) {
            $hist = $state.session.history
            if ($hist) {
                foreach ($item in $hist) {
                    $content = $item.message.content
                    if ($content -like 'MOCK OK:*') { return $false }
                }
            }
        }
        return $null -ne $state
    } catch {
        return $false
    }
}

function Get-ContinueHome {
    return Join-Path $env:USERPROFILE '.continue'
}

function Test-ContinueLocalConfig {
    $continueHome = Get-ContinueHome
    $cfg = Join-Path $continueHome 'config.yaml'
    $done = Join-Path $continueHome '.onboarding_complete'
    return (Test-Path $cfg) -and (Test-Path $done)
}

function Ensure-ContinueLocalConfig {
    param(
        [string]$Root,
        [hashtable]$Cfg,
        [switch]$Force
    )
    $continueHome = Get-ContinueHome
    New-Item -ItemType Directory -Force -Path $continueHome | Out-Null

    $model = ($Cfg.OLLAMA_MODEL_AGENT -as [string]).Trim()
    if (-not $model) { $model = 'qwen2.5:14b-instruct' }

    $cfgPath = Join-Path $continueHome 'config.yaml'
    if ($Force -or -not (Test-Path $cfgPath)) {
        $tpl = Join-Path $Root 'scripts\templates\continue-config.local.yaml'
        if (-not (Test-Path $tpl)) { return $false }
        $yaml = Get-Content -LiteralPath $tpl -Raw -Encoding UTF8
        $yaml = $yaml.Replace('__OLLAMA_MODEL__', $model)
        Set-Content -LiteralPath $cfgPath -Value $yaml -Encoding UTF8 -NoNewline
    }

    $done = Join-Path $continueHome '.onboarding_complete'
    if ($Force -or -not (Test-Path $done)) {
        Set-Content -LiteralPath $done -Value (Get-Date -Format 'o') -Encoding UTF8
    }
    return $true
}

function Test-ContinueReady {
    param([hashtable]$EnvVars = @{})
    if ($EnvVars.CONTINUE_API_KEY) { return $true }
    if ($env:CONTINUE_API_KEY) { return $true }
    if (Test-ContinueLocalConfig) { return $true }
    return $false
}

function Stop-ContinuePortListener {
    param([int]$Port = 65432)
    try {
        Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
            ForEach-Object {
                $p = Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue
                if ($p) {
                    Write-Host "Stopping $($p.ProcessName) on :$Port (pid $($p.Id))"
                    Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
                }
            }
    } catch { }
    Start-Sleep -Seconds 1
}

function Import-ContinueEnvFromDotenv {
    param([string]$Root)
    $envPath = Join-Path $Root '.env'
    $out = @{
        ENABLE_CONTINUE_DEV  = 'false'
        CONTINUE_DEV_URL     = 'http://host.docker.internal:65432'
        CONTINUE_DEV_TIMEOUT = '3600'
        CONTINUE_API_KEY     = ''
        OLLAMA_MODEL_AGENT   = 'qwen2.5:14b-instruct'
    }
    if (-not (Test-Path $envPath)) { return $out }
    foreach ($line in Get-Content -LiteralPath $envPath -Encoding UTF8) {
        $t = $line.Trim()
        if (-not $t -or $t.StartsWith('#')) { continue }
        $eq = $t.IndexOf('=')
        if ($eq -lt 1) { continue }
        $k = $t.Substring(0, $eq).Trim()
        $v = $t.Substring($eq + 1).Trim()
        if ($v.Length -ge 2) {
            if (($v.StartsWith('"') -and $v.EndsWith('"')) -or ($v.StartsWith("'") -and $v.EndsWith("'"))) {
                $v = $v.Substring(1, $v.Length - 2)
            }
        }
        if ($k -eq 'OLLAMA_MODEL_AGENT') { $out[$k] = $v }
        elseif ($out.ContainsKey($k)) { $out[$k] = $v }
    }
    return $out
}

function Start-ContinueServe {
    param(
        [string]$Root,
        [hashtable]$Cfg,
        [scriptblock]$Log = { param($m) Write-Host $m }
    )
    if ($Cfg.ENABLE_CONTINUE_DEV -ne 'true') {
        & $Log 'continue: skipped (ENABLE_CONTINUE_DEV=false)'
        return $false
    }

    $port = Get-ContinueDevPort -Url $Cfg.CONTINUE_DEV_URL
    if (Test-ContinueApi -Port $port) {
        & $Log "continue: API already up :$port"
        return $true
    }

    if (-not (Install-ContinueCn)) {
        & $Log 'continue: cn CLI missing'
        return $false
    }

    if (-not (Test-ContinueReady -EnvVars $Cfg)) {
        & $Log 'continue: not ready — run: powershell -File scripts/setup_continue.ps1'
        return $false
    }

    Stop-ContinuePortListener -Port $port

    $cn = Get-ContinueCnCommand
    $timeout = 3600
    if ($Cfg.CONTINUE_DEV_TIMEOUT) {
        [void][int]::TryParse($Cfg.CONTINUE_DEV_TIMEOUT, [ref]$timeout)
    }
    if ($timeout -lt 300) { $timeout = 300 }

    if ($Cfg.CONTINUE_API_KEY) { $env:CONTINUE_API_KEY = $Cfg.CONTINUE_API_KEY }

    $serveArgs = @('serve', '--port', "$port", '--timeout', "$timeout")
    Start-Process -FilePath $cn -ArgumentList $serveArgs -WorkingDirectory $Root -WindowStyle Minimized
    & $Log "continue: started cn serve :$port (timeout ${timeout}s)"

    for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep -Seconds 2
        if (Test-ContinueApi -Port $port) {
            & $Log 'continue: API healthy'
            return $true
        }
    }
    & $Log 'continue: started but /state not ready after 60s (check data/logs/continue-serve.log)'
    return $false
}
