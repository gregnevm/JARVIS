# Cloudflare quick tunnel for Telegram Mini App (no domain / no token).
# URL is ephemeral (*.trycloudflare.com) — this script keeps PUBLIC_APP_URL in sync.
#
# Usage:
#   powershell -File scripts/setup_quick_tunnel.ps1          # start + sync + recreate gateway
#   powershell -File scripts/setup_quick_tunnel.ps1 -SyncOnly   # idempotent (autostart/watchdog)
#   powershell -File scripts/setup_quick_tunnel.ps1 -Stop
#
# Opt-in autostart: ENABLE_QUICK_TUNNEL=true in .env (skipped when CLOUDFLARE_TUNNEL_TOKEN is set).

param(
    [switch]$SyncOnly,
    [switch]$Stop,
    [int]$WaitSeconds = 120
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$envFile = Join-Path $root '.env'
$stateFile = Join-Path $root 'data\quick_tunnel.last_url'
$containerName = 'jarvis-quick-tunnel'
$urlPattern = 'https://[a-z0-9-]+\.trycloudflare\.com'

Set-Location $root

function Get-RunningContainerId {
    param([string]$Name)
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    $out = docker ps --filter "name=$Name" --filter "status=running" -q 2>&1
    $ErrorActionPreference = $prevEap
    if ($out -is [System.Array]) { return ($out | Select-Object -First 1) }
    return $out
}

function Invoke-Native {
    param([scriptblock]$Command)
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    & $Command 2>&1 | ForEach-Object { Write-Host $_ }
    $code = $LASTEXITCODE
    $ErrorActionPreference = $prevEap
    return $code
}

function Write-Step($msg) { Write-Host $msg -ForegroundColor Cyan }

function Get-DotEnvValue {
    param([string]$Path, [string]$Name)
    if (-not (Test-Path $Path)) { return '' }
    foreach ($line in Get-Content -LiteralPath $Path -Encoding UTF8) {
        $t = $line.Trim()
        if (-not $t -or $t.StartsWith('#')) { continue }
        if ($t -match "^\s*$([regex]::Escape($Name))=(.*)$") {
            return $Matches[1].Trim().Trim('"').Trim("'")
        }
    }
    return ''
}

function Set-DotEnvValue {
    param([string]$Path, [string]$Name, [string]$Value)
    $lines = @()
    if (Test-Path $Path) {
        $lines = [System.Collections.Generic.List[string]]@(
            (Get-Content -LiteralPath $Path -Encoding UTF8)
        )
    } else {
        $lines = [System.Collections.Generic.List[string]]@()
    }
    $found = $false
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match "^\s*$([regex]::Escape($Name))=") {
            $lines[$i] = "$Name=$Value"
            $found = $true
            break
        }
    }
    if (-not $found) { [void]$lines.Add("$Name=$Value") }
    Set-Content -LiteralPath $Path -Value $lines -Encoding UTF8
}

function Get-QuickTunnelUrlFromLogs {
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    $raw = docker logs $containerName 2>&1 | Out-String
    $ErrorActionPreference = $prevEap
    if (-not $raw) { return '' }
    $m = [regex]::Matches($raw, $urlPattern)
    if ($m.Count -eq 0) { return '' }
    return $m[$m.Count - 1].Value.TrimEnd('/')
}

function Test-QuickTunnelHttp {
    param([string]$BaseUrl)
    if (-not $BaseUrl) { return $false }
    $probe = "$BaseUrl/health"
    try {
        $code = & curl.exe -s -o NUL -w '%{http_code}' --max-time 12 $probe
        return ($code -eq '200')
    } catch {
        return $false
    }
}

function Wait-QuickTunnelUrl {
    param([int]$TimeoutSec)
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        $url = Get-QuickTunnelUrlFromLogs
        if ($url -and (Test-QuickTunnelHttp -BaseUrl $url)) { return $url }
        Start-Sleep -Seconds 2
    }
    return ''
}

function Start-QuickTunnelContainer {
    # Remove legacy one-off `docker run` container with the same name.
    Invoke-Native { docker rm -f $containerName } | Out-Null
    $code = Invoke-Native { docker compose --profile quick-tunnel up -d cloudflared-quick }
    if ($code -ne 0) { throw 'docker compose --profile quick-tunnel up failed' }
}

function Stop-QuickTunnelContainer {
    Invoke-Native { docker compose --profile quick-tunnel stop cloudflared-quick } | Out-Null
    Invoke-Native { docker rm -f $containerName } | Out-Null
    Write-Host 'Quick tunnel stopped.'
}

function Sync-PublicAppUrl {
    param(
        [string]$TunnelUrl,
        [switch]$RecreateGateway
    )
    if (-not $TunnelUrl) { return $false }

    $appUrl = "$TunnelUrl/app"
    $webhookUrl = "$TunnelUrl/webhook"
    $current = Get-DotEnvValue -Path $envFile -Name 'PUBLIC_APP_URL'
    $currentWh = Get-DotEnvValue -Path $envFile -Name 'TELEGRAM_WEBHOOK_URL'
    $ingest = (Get-DotEnvValue -Path $envFile -Name 'TELEGRAM_INGEST_MODE').ToLower()
    $last = if (Test-Path $stateFile) { (Get-Content $stateFile -Raw).Trim() } else { '' }

    $changed = ($current.TrimEnd('/') -ne $appUrl.TrimEnd('/')) -or ($last -ne $TunnelUrl)
    if ($ingest -eq 'webhook' -and $currentWh.TrimEnd('/') -ne $webhookUrl.TrimEnd('/')) {
        $changed = $true
    }
    if (-not $changed) {
        Write-Host "PUBLIC_APP_URL already $appUrl"
        return $false
    }

    Set-DotEnvValue -Path $envFile -Name 'PUBLIC_APP_URL' -Value $appUrl
    if ($ingest -eq 'webhook') {
        Set-DotEnvValue -Path $envFile -Name 'TELEGRAM_WEBHOOK_URL' -Value $webhookUrl
        Write-Host "Updated TELEGRAM_WEBHOOK_URL -> $webhookUrl" -ForegroundColor Green
    }
    New-Item -ItemType Directory -Force -Path (Split-Path $stateFile) | Out-Null
    Set-Content -Path $stateFile -Value $TunnelUrl -Encoding UTF8 -NoNewline
    Write-Host "Updated PUBLIC_APP_URL -> $appUrl" -ForegroundColor Green

    if ($RecreateGateway) {
        Write-Step 'Recreating gateway (menu button + Mini App URL)...'
        $code = Invoke-Native { docker compose up -d --force-recreate gateway }
        if ($code -ne 0) { throw 'gateway recreate failed' }
    }
    return $true
}

if (-not (Test-Path $envFile)) {
    throw '.env not found - copy .env.example first'
}

$namedToken = Get-DotEnvValue -Path $envFile -Name 'CLOUDFLARE_TUNNEL_TOKEN'
if ($namedToken) {
    Write-Host 'CLOUDFLARE_TUNNEL_TOKEN is set - use named tunnel (profile tunnel), not quick tunnel.' -ForegroundColor Yellow
    exit 0
}

if ($Stop) {
    Stop-QuickTunnelContainer
    exit 0
}

Write-Step 'Quick tunnel: ensuring cloudflared-quick is up...'
$running = Get-RunningContainerId -Name $containerName
if (-not $running) {
    Start-QuickTunnelContainer
} elseif (-not $SyncOnly) {
    # Fresh start requested — bounce for a clean URL attempt when API was flaky.
    Write-Host 'Container already running.'
}

Write-Step "Waiting for trycloudflare.com URL (up to ${WaitSeconds}s)..."
$tunnelUrl = Wait-QuickTunnelUrl -TimeoutSec $WaitSeconds
if (-not $tunnelUrl) {
    Write-Host 'Quick tunnel URL not ready. Check: docker logs jarvis-quick-tunnel' -ForegroundColor Red
    Write-Host 'Cloudflare quick API can be slow - retry: powershell -File scripts/setup_quick_tunnel.ps1 -SyncOnly'
    exit 1
}

Write-Host "Tunnel URL: $tunnelUrl" -ForegroundColor Green
$synced = Sync-PublicAppUrl -TunnelUrl $tunnelUrl -RecreateGateway

Write-Host ''
Write-Host 'Mini App in Telegram: /app or menu button Dashboard'
Write-Host 'Note: URL changes when jarvis-quick-tunnel restarts - re-run this script or keep ENABLE_QUICK_TUNNEL=true in autostart.'

if ($synced) { exit 0 }
exit 0
