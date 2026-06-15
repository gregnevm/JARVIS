# JARVIS autonomous setup helpers (secrets, logging, resume).
# Dot-source from FirstSetup.ps1

function Write-SetupLog {
    param([string]$Root, [string]$Message)
    $dir = Join-Path $Root 'data'
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    $log = Join-Path $dir 'firstsetup.log'
    $line = '{0} {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Message
    Add-Content -LiteralPath $log -Value $line -Encoding UTF8
}

function Import-SetupSecrets {
    param(
        [string]$Root,
        [string]$TelegramToken,
        [string]$AllowedUserIds
    )
    $secrets = @{
        TELEGRAM_BOT_TOKEN = $TelegramToken
        ALLOWED_USER_IDS   = $AllowedUserIds
    }

    $localPath = Join-Path $Root 'setup.local.env'
    if (Test-Path $localPath) {
        foreach ($line in Get-Content -LiteralPath $localPath -Encoding UTF8) {
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
            if ($k -in @('TELEGRAM_BOT_TOKEN', 'ALLOWED_USER_IDS', 'ADMIN_USER_IDS')) {
                $secrets[$k] = $v
            }
        }
    }

    if ([string]::IsNullOrWhiteSpace($secrets.TELEGRAM_BOT_TOKEN)) {
        $secrets.TELEGRAM_BOT_TOKEN = $env:JARVIS_TELEGRAM_BOT_TOKEN
    }
    if ([string]::IsNullOrWhiteSpace($secrets.ALLOWED_USER_IDS)) {
        $secrets.ALLOWED_USER_IDS = $env:JARVIS_ALLOWED_USER_IDS
    }
    if ([string]::IsNullOrWhiteSpace($secrets.ADMIN_USER_IDS)) {
        $secrets.ADMIN_USER_IDS = $env:JARVIS_ADMIN_USER_IDS
    }

    $secrets
}

function Save-SetupStatus {
    param([string]$Root, [hashtable]$Status)
    $dir = Join-Path $Root 'data'
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    $path = Join-Path $dir 'firstsetup.status.json'
    ($Status | ConvertTo-Json -Depth 6) | Set-Content -LiteralPath $path -Encoding UTF8
    return $path
}

function Register-SetupResume {
    param([string]$Root, [string]$FirstSetupScript)
    $taskName = 'JARVIS-FirstSetup-Resume'
    $psArgs = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$FirstSetupScript`" -Auto"
    $tr = "powershell.exe $psArgs"

    Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue |
        Unregister-ScheduledTask -Confirm:$false -ErrorAction SilentlyContinue
    cmd /c "schtasks /Delete /TN `"$taskName`" /F >nul 2>&1"

    $action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $psArgs
    $trigger = New-ScheduledTaskTrigger -AtLogOn
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null

    $pending = Join-Path $Root 'data\firstsetup.pending'
    Set-Content -LiteralPath $pending -Value (Get-Date -Format 'o') -Encoding UTF8
    return $taskName
}

function Unregister-SetupResume {
    param([string]$Root)
    $taskName = 'JARVIS-FirstSetup-Resume'
    Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue |
        Unregister-ScheduledTask -Confirm:$false -ErrorAction SilentlyContinue
    cmd /c "schtasks /Delete /TN `"$taskName`" /F >nul 2>&1"
    $pending = Join-Path $Root 'data\firstsetup.pending'
    if (Test-Path $pending) { Remove-Item -LiteralPath $pending -Force }
}

function Sync-PostgresPasswordToDb {
    <#
    POSTGRES_PASSWORD у .env не оновлює пароль у вже ініціалізованому volume.
    Сервіси (memory, tools) підключаються по docker network з scram — потрібен ALTER USER.
    #>
    param([string]$Root)
    $envPath = Join-Path $Root '.env'
    if (-not (Test-Path $envPath)) { return $false }

    $pgUser = Get-EnvFileValue -Path $envPath -Key 'POSTGRES_USER'
    if ([string]::IsNullOrWhiteSpace($pgUser)) { $pgUser = 'jarvis' }
    $pgDb = Get-EnvFileValue -Path $envPath -Key 'POSTGRES_DB'
    if ([string]::IsNullOrWhiteSpace($pgDb)) { $pgDb = 'jarvis' }
    $pgPass = Get-EnvFileValue -Path $envPath -Key 'POSTGRES_PASSWORD'
    if ([string]::IsNullOrWhiteSpace($pgPass)) { return $false }

    Push-Location $Root
    try {
        docker compose ps postgres --format '{{.State}}' 2>$null | Out-Null
        if ($LASTEXITCODE -ne 0) { return $false }

        $escaped = $pgPass -replace "'", "''"
        $sql = "ALTER USER $pgUser WITH PASSWORD '$escaped';"
        docker compose exec -T postgres psql -U $pgUser -d $pgDb -c $sql 2>$null | Out-Null
        return ($LASTEXITCODE -eq 0)
    } finally {
        Pop-Location
    }
}
