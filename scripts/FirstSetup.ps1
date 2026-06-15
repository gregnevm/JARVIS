# JARVIS FirstSetup — перше розгортання на своєму ПК (Windows).
#
# Інтерактивно:
#   powershell -ExecutionPolicy Bypass -File scripts\FirstSetup.ps1
#
# Повністю автономно (winget + env + compose + autostart, без питань):
#   powershell -ExecutionPolicy Bypass -File scripts\FirstSetup.ps1 -Auto
#   FirstSetup-Auto.bat
#
# Секрети для -Auto: setup.local.env (copy setup.local.env.example) або
#   JARVIS_TELEGRAM_BOT_TOKEN / JARVIS_ALLOWED_USER_IDS у середовищі.

param(
    [switch]$Auto,
    [switch]$NonInteractive,
    [switch]$InstallMissing,
    [switch]$SkipCompose,
    [switch]$SkipModels,
    [switch]$SkipHostagent,
    [switch]$SkipAutostart,
    [switch]$StrictProd,
    [switch]$EnableComputerUse,
    [switch]$ForceEnv,
    [string]$TelegramToken = '',
    [string]$AllowedUserIds = ''
)

if ($Auto) {
    $NonInteractive = $true
    $InstallMissing = $true
    $EnableComputerUse = $true
}

$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root
$script:SetupExitCode = 0

. (Join-Path $PSScriptRoot 'lib\jarvis_hardware.ps1')
. (Join-Path $PSScriptRoot 'lib\jarvis_env.ps1')
. (Join-Path $PSScriptRoot 'lib\jarvis_prereq.ps1')
. (Join-Path $PSScriptRoot 'lib\jarvis_setup.ps1')

function Step($msg) {
    Write-Host "`n== $msg ==" -ForegroundColor Cyan
    Write-SetupLog -Root $root -Message "== $msg =="
}
function Ok($msg) {
    Write-Host "[OK]   $msg" -ForegroundColor Green
    Write-SetupLog -Root $root -Message "[OK] $msg"
}
function Warn($msg) {
    Write-Host "[WARN] $msg" -ForegroundColor Yellow
    Write-SetupLog -Root $root -Message "[WARN] $msg"
}
function Ask($prompt, [string]$default = '') {
    if ($NonInteractive) { return $default }
    $hint = if ($default) { " [$default]" } else { '' }
    $r = Read-Host "$prompt$hint"
    if ([string]::IsNullOrWhiteSpace($r)) { return $default }
    return $r.Trim()
}

function Test-DockerEngine {
    docker info --format '{{.ServerVersion}}' 2>$null | Out-Null
    return $LASTEXITCODE -eq 0
}

function Start-OllamaServe {
    param([hashtable]$Profile, [string]$OllamaExe)

    foreach ($kv in (Get-JarvisOllamaUserEnv -Profile $Profile).GetEnumerator()) {
        Set-Item -Path "Env:$($kv.Key)" -Value $kv.Value
    }
    if (-not $Profile.ollama_vulkan) {
        Remove-Item Env:OLLAMA_VULKAN -ErrorAction SilentlyContinue
    }

    try {
        Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 3 | Out-Null
        Ok 'Ollama API вже працює'
        return
    } catch { }

    if (Get-Process ollama -ErrorAction SilentlyContinue) {
        Warn 'Ollama процес є, але API не відповідає — чекаю...'
    } else {
        Start-Process -FilePath $OllamaExe -ArgumentList 'serve' -WindowStyle Hidden
        Ok 'Ollama serve запущено'
    }
    for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep -Seconds 2
        try {
            Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 4 | Out-Null
            Ok 'Ollama API ready'
            return
        } catch { }
    }
    Warn 'Ollama API ще не відповідає — pull моделей може не вдатися'
}

function Pull-OllamaModels {
    param([string[]]$Models, [string]$OllamaExe)

    $ollamaCmd = if ($OllamaExe) { $OllamaExe } else { 'ollama' }
    foreach ($m in $Models) {
        Write-Host "  pull $m ..." -ForegroundColor Gray
        Write-SetupLog -Root $root -Message "ollama pull $m"
        & $ollamaCmd pull $m
        if ($LASTEXITCODE -ne 0) { Warn "ollama pull $m failed (exit $LASTEXITCODE)" }
        else { Ok "model $m" }
    }
}

function Ensure-HostagentDeps {
    if (-not (Ensure-JarvisPython -InstallMissing:$InstallMissing -NonInteractive:$NonInteractive `
            -OnAsk ${function:Ask} -OnOk ${function:Ok} -OnWarn ${function:Warn})) {
        return $false
    }
    & python -c 'import uvicorn, fastapi' 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host '  pip install hostagent deps...' -ForegroundColor Gray
        & python -m pip install -q -r (Join-Path $root 'hostagent\requirements.txt')
        if ($LASTEXITCODE -ne 0) { Warn 'pip install hostagent failed'; return $false }
    }
    Ok 'hostagent Python deps'
    return $true
}

function Start-HostagentProcess {
    param([string]$EnvPath)
    $token = Get-EnvFileValue -Path $EnvPath -Key 'HOSTAGENT_TOKEN'
    if ([string]::IsNullOrWhiteSpace($token)) {
        Warn 'HOSTAGENT_TOKEN порожній — host-agent не стартує'
        return
    }
    try {
        Invoke-RestMethod -Uri 'http://127.0.0.1:8400/health' -TimeoutSec 2 | Out-Null
        Ok 'hostagent вже працює :8400'
        return
    } catch { }

    $workDir = Join-Path $root 'hostagent'
    Start-Process -FilePath 'python' -ArgumentList @(
        '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8400'
    ) -WorkingDirectory $workDir -WindowStyle Hidden
    Start-Sleep -Seconds 3
    try {
        Invoke-RestMethod -Uri 'http://127.0.0.1:8400/health' -TimeoutSec 5 | Out-Null
        Ok 'hostagent started :8400'
    } catch {
        Warn 'hostagent не відповідає — autostart/watchdog підніме пізніше'
    }
}

function Apply-SetupSecrets {
    param([string]$EnvPath, [hashtable]$Secrets)

    if (-not [string]::IsNullOrWhiteSpace($Secrets.TELEGRAM_BOT_TOKEN)) {
        [void](Set-EnvFileValue -Path $EnvPath -Key 'TELEGRAM_BOT_TOKEN' -Value $Secrets.TELEGRAM_BOT_TOKEN)
    }
    $uids = $Secrets.ALLOWED_USER_IDS
    if (-not [string]::IsNullOrWhiteSpace($uids) -and $uids -ne '123456789') {
        [void](Set-EnvFileValue -Path $EnvPath -Key 'ALLOWED_USER_IDS' -Value $uids)
        $admin = if ($Secrets.ADMIN_USER_IDS) { $Secrets.ADMIN_USER_IDS } else { ($uids -split ',' | Select-Object -First 1) }
        [void](Set-EnvFileValue -Path $EnvPath -Key 'ADMIN_USER_IDS' -Value $admin)
        $owner = Get-EnvFileValue -Path $EnvPath -Key 'COMPUTER_OWNER_USER_IDS'
        if ($owner -eq '123456789' -or [string]::IsNullOrWhiteSpace($owner)) {
            [void](Set-EnvFileValue -Path $EnvPath -Key 'COMPUTER_OWNER_USER_IDS' -Value ($uids -split ',' | Select-Object -First 1))
        }
    }
}

$modeLabel = if ($Auto) { 'AUTO (повністю автономно)' } else { 'interactive' }
Write-Host "`n  JARVIS FirstSetup — $modeLabel`n" -ForegroundColor White
Write-SetupLog -Root $root -Message "=== FirstSetup start mode=$modeLabel ==="

$secrets = Import-SetupSecrets -Root $root -TelegramToken $TelegramToken -AllowedUserIds $AllowedUserIds

# --- 1) Hardware ---
Step 'Hardware detection'
$gpu = Get-JarvisGpuInfo
$hw = Get-JarvisHardwareProfile -GpuInfo $gpu
$profilePath = Save-JarvisHardwareProfile -Root $root -Profile $hw
Ok "GPU: $($hw.gpu_name) ($($hw.profile))"
foreach ($n in $hw.notes) { Write-Host "  · $n" -ForegroundColor DarkGray }
Ok "profile saved: $profilePath"

$ollamaUserEnv = Apply-JarvisOllamaUserEnv -Profile $hw
Ok ('Ollama User env: ' + (($ollamaUserEnv.GetEnumerator() | ForEach-Object { "$($_.Key)=$($_.Value)" }) -join ', '))

# --- 2) Prerequisites ---
Step 'Prerequisites'
if (-not (Test-WingetAvailable)) {
    if ($Auto) {
        throw 'winget не знайдено — для -Auto потрібен App Installer (Windows 10/11). Онови Windows або встанови winget вручну.'
    }
    Warn 'winget не знайдено — відсутні Docker/Ollama/Python треба ставити вручну'
}

$dockerResult = Ensure-JarvisDocker -InstallMissing:$InstallMissing -NonInteractive:$NonInteractive -Auto:$Auto `
    -OnAsk ${function:Ask} -OnOk ${function:Ok} -OnWarn ${function:Warn} -TestEngine ${function:Test-DockerEngine}

if (-not $dockerResult.Ready) {
    if ($Auto) {
        $task = Register-SetupResume -Root $root -FirstSetupScript $PSCommandPath
        Warn "Docker ще не готовий — зареєстровано resume: $task (наступний логін продовжить -Auto)"
        Save-SetupStatus -Root $root -Status @{
            phase = 'docker_pending'
            auto  = $true
            at    = (Get-Date).ToString('o')
        } | Out-Null
        Write-Host @"

Docker встановлено, але engine ще не піднявся.
- Перезавантаж Windows АБО дочекайся Docker Desktop у треї
- FirstSetup продовжиться автоматично при наступному логіні (-Auto)

"@ -ForegroundColor Yellow
        exit 2
    }
    throw @"
Docker engine не відповідає.
Запусти Docker Desktop і повтори FirstSetup.
"@
}

$ollamaExe = Ensure-JarvisOllama -InstallMissing:$InstallMissing -NonInteractive:$NonInteractive `
    -OnAsk ${function:Ask} -OnOk ${function:Ok}

# --- 3) .env ---
Step '.env configuration'
$envPath = Ensure-JarvisEnvFile -Root $root

$userHome = [Environment]::GetFolderPath('UserProfile')
$downloads = Join-Path $userHome 'Downloads\JARVIS'
$tz = [TimeZoneInfo]::Local.Id

$pgPass = Get-EnvFileValue -Path $envPath -Key 'POSTGRES_PASSWORD'
if ($ForceEnv -or [string]::IsNullOrWhiteSpace($pgPass) -or $pgPass -eq 'changeme') {
    [void](Set-EnvFileValue -Path $envPath -Key 'POSTGRES_PASSWORD' -Value (New-JarvisSecret -Bytes 16))
}
$haTok = Get-EnvFileValue -Path $envPath -Key 'HOSTAGENT_TOKEN'
if ($ForceEnv -or [string]::IsNullOrWhiteSpace($haTok)) {
    [void](Set-EnvFileValue -Path $envPath -Key 'HOSTAGENT_TOKEN' -Value (New-JarvisSecret -Bytes 24))
}

$hwOverrides = @{
    OLLAMA_MODEL_CHAT       = $hw.ollama_model_chat
    OLLAMA_MODEL_AGENT      = $hw.ollama_model_agent
    EMBED_MODEL             = $hw.embed_model
    WHISPER_MODEL           = $hw.whisper_model
    OLLAMA_VISION_ON_DEMAND = if ($hw.vision_on_demand) { 'true' } else { 'false' }
    HOSTAGENT_DROP_DIR      = $downloads
    HOSTAGENT_FS_ROOTS      = "$userHome,$(Join-Path $root 'data')"
    GENERIC_TIMEZONE        = $tz
    TZ                      = $tz
}
[void](Set-EnvFileValues -Path $envPath -Values $hwOverrides -OnlyIfEmpty:(-not $ForceEnv))

Apply-SetupSecrets -EnvPath $envPath -Secrets $secrets

if (-not $NonInteractive) {
    Write-Host @"

Telegram (@BotFather → /newbot):
  TELEGRAM_BOT_TOKEN — токен бота
  ALLOWED_USER_IDS   — твій Telegram ID (@userinfobot → Id)

"@ -ForegroundColor DarkGray
    $token = Ask 'TELEGRAM_BOT_TOKEN' (Get-EnvFileValue -Path $envPath -Key 'TELEGRAM_BOT_TOKEN')
    if ($token) { [void](Set-EnvFileValue -Path $envPath -Key 'TELEGRAM_BOT_TOKEN' -Value $token) }
    $uidDefault = Get-EnvFileValue -Path $envPath -Key 'ALLOWED_USER_IDS'
    if ($uidDefault -eq '123456789') { $uidDefault = '' }
    $userId = Ask 'ALLOWED_USER_IDS (comma-separated)' $uidDefault
    if ($userId) {
        Apply-SetupSecrets -EnvPath $envPath -Secrets @{ ALLOWED_USER_IDS = $userId }
    }
    if (-not $EnableComputerUse) {
        $cu = Ask 'Увімкнути Computer Use (керування цим ПК)? (y/N)' 'N'
        if ($cu -match '^[yY]') { $EnableComputerUse = $true }
    }
}

if ($EnableComputerUse) {
    [void](Set-EnvFileValue -Path $envPath -Key 'ENABLE_COMPUTER_USE' -Value 'true')
    Ok 'ENABLE_COMPUTER_USE=true'
}

if ($StrictProd -or $Auto) {
    [void](Set-EnvFileValue -Path $envPath -Key 'WEBAPP_DEV_OPEN' -Value 'false')
    if ($Auto) { Ok 'WEBAPP_DEV_OPEN=false (Auto)' }
    else { Ok 'WEBAPP_DEV_OPEN=false (StrictProd)' }
}

Ok ".env ready: $envPath"

$tokFinal = Get-EnvFileValue -Path $envPath -Key 'TELEGRAM_BOT_TOKEN'
if ([string]::IsNullOrWhiteSpace($tokFinal)) {
    Warn 'TELEGRAM_BOT_TOKEN порожній — додай у setup.local.env і: docker compose up -d gateway'
    $script:SetupExitCode = 1
}

# --- 4) Ollama + models ---
Step 'Ollama'
Start-OllamaServe -Profile $hw -OllamaExe $ollamaExe

if (-not $SkipModels) {
    Step 'Ollama models'
    Write-Host "Профіль $($hw.profile): $($hw.models -join ', ')" -ForegroundColor Gray
    Pull-OllamaModels -Models $hw.models -OllamaExe $ollamaExe
} else {
    Warn 'SkipModels — ollama pull пропущено'
}

# --- 5) Host-agent ---
if (-not $SkipHostagent) {
    Step 'Host-agent'
    if (Ensure-HostagentDeps) {
        Start-HostagentProcess -EnvPath $envPath
    }
}

# --- 5b) SD Forge (локальна генерація зображень) ---
function Test-SdForgeWanted {
    if (-not (Test-Path (Join-Path $root '.env'))) { return $false }
    $line = Get-Content (Join-Path $root '.env') -ErrorAction SilentlyContinue |
        Where-Object { $_ -match '^\s*IMAGE_GEN_URL=' } | Select-Object -First 1
    if (-not $line) { return $false }
    $val = ($line -split '=', 2)[1].Trim().ToLower()
    return ($val -match '7860' -or $val -match 'host\.docker\.internal')
}

if (Test-SdForgeWanted) {
    Step 'SD Forge (local image gen)'
    $setupForge = Join-Path $PSScriptRoot 'setup_sd_forge.ps1'
    $startForge = Join-Path $PSScriptRoot 'start_sd_forge.ps1'
    $forgeDir = Join-Path $root 'vendor\sd-forge'
    if (-not (Test-Path (Join-Path $forgeDir 'webui.py')) -and (Test-Path $setupForge)) {
        & powershell -NoProfile -ExecutionPolicy Bypass -File $setupForge
        if ($LASTEXITCODE -ne 0) { Warn 'setup_sd_forge.ps1 failed' }
    }
    if (Test-Path $startForge) {
        & powershell -NoProfile -ExecutionPolicy Bypass -File $startForge
        if ($LASTEXITCODE -ne 0) { Warn 'start_sd_forge.ps1 did not confirm API (watchdog/autostart will retry)' }
        else { Ok 'SD Forge API :7860' }
    } else {
        Warn 'start_sd_forge.ps1 missing'
    }
}

# --- 6) Docker Compose ---
$verifyOk = $false
if (-not $SkipCompose) {
    Step 'Docker Compose'
    New-Item -ItemType Directory -Force -Path (Join-Path $root 'data\access') | Out-Null
    docker compose up -d --build
    if ($LASTEXITCODE -ne 0) { throw 'docker compose up failed' }
    Ok 'compose up -d --build'
    if (Sync-PostgresPasswordToDb -Root $root) {
        Ok 'postgres password synced to .env'
    } else {
        Warn 'postgres password sync skipped (postgres not ready or .env empty)'
    }
    Write-Host '  чекаю healthchecks (20s)...' -ForegroundColor Gray
    Start-Sleep -Seconds 20

    Step 'verify_stack'
    $verifyArgs = @()
    if ($StrictProd -or $Auto) { $verifyArgs += '-StrictProd' }
    & (Join-Path $PSScriptRoot 'verify_stack.ps1') @verifyArgs
    $verifyOk = ($LASTEXITCODE -eq 0)
    if (-not $verifyOk) {
        Warn "verify_stack: деякі перевірки не пройшли (exit $LASTEXITCODE)"
        if ($script:SetupExitCode -eq 0) { $script:SetupExitCode = 1 }
    } else {
        Ok 'verify_stack passed'
    }
} else {
    Warn 'SkipCompose — docker compose пропущено'
}

# --- 7) Autostart (Auto) ---
if ($Auto -and -not $SkipAutostart) {
    Step 'Autostart (logon + watchdog)'
    $autostartInstaller = Join-Path $PSScriptRoot 'install_autostart.ps1'
    if (Test-Path $autostartInstaller) {
        try {
            & powershell -NoProfile -ExecutionPolicy Bypass -File $autostartInstaller
            Ok 'install_autostart.ps1 done'
        } catch {
            Warn "install_autostart failed: $($_.Exception.Message)"
        }
    }
}

if ($verifyOk -or $SkipCompose) {
    Unregister-SetupResume -Root $root
}

$statusPath = Save-SetupStatus -Root $root -Status @{
    completed_at   = (Get-Date).ToString('o')
    auto           = [bool]$Auto
    profile        = $hw.profile
    verify_ok      = $verifyOk
    telegram_ready = -not [string]::IsNullOrWhiteSpace($tokFinal)
    models         = $hw.models
    env_path       = $envPath
}

# --- 8) Summary ---
Step 'Готово'
Write-Host @"
Статус: $statusPath
Лог:    data\firstsetup.log

$(if ($tokFinal) { 'Telegram: напиши боту /start' } else { 'Telegram: заповни setup.local.env → docker compose up -d gateway' })
Smoke:  docs\SMOKE_TEST.md

Моделі ($($hw.profile)): $($hw.ollama_model_chat) + $($hw.ollama_model_agent)
"@ -ForegroundColor White

Write-SetupLog -Root $root -Message "=== FirstSetup done exit=$script:SetupExitCode ==="
exit $script:SetupExitCode
