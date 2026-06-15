# JARVIS Game Mode — один перемикач, що звільняє ПК для ігор.
#
#   ON  (game mode):  вимикає весь автозапуск + зупиняє стек (Docker, Ollama,
#                     host-agent, SD Forge, Continue, cloudflared) і звільняє RAM WSL-VM.
#   OFF (відновити):  вмикає автозапуск назад і піднімає стек у фоні (autostart.ps1).
#
# Що вважається "автозапуском" і "перевірками":
#   * Scheduled task  JARVIS-Watchdog   (logon + кожні 5 хв — це і є перевірки/самолікування)
#   * Startup-папка   JARVIS-Autostart.vbs  (запуск autostart.ps1 при вході)
#   * Startup-папка   Ollama.lnk            (трей-додаток Ollama)
#   * HKCU Run        Docker Desktop        (автозапуск Docker Desktop)
#
# Використання:
#   game_mode.ps1            -> -Toggle (перемкнути)
#   game_mode.ps1 -On        -> увімкнути game mode (зупинити все)
#   game_mode.ps1 -Off       -> вимкнути game mode (відновити все)
#   game_mode.ps1 -Status    -> лише показати стан
#   game_mode.ps1 -On -Quiet -> без паузи в кінці (для автоматизації)

[CmdletBinding()]
param(
    [switch]$On,
    [switch]$Off,
    [switch]$Toggle,
    [switch]$Status,
    [switch]$Quiet
)

$ErrorActionPreference = 'Continue'
$root = Split-Path $PSScriptRoot -Parent

# --- константи середовища (з розвідки autostart.ps1) ---
$TaskName     = 'JARVIS-Watchdog'
$StartupDir   = [Environment]::GetFolderPath('Startup')
$VbsName      = 'JARVIS-Autostart.vbs'
$OllamaLnk    = 'Ollama.lnk'
$RunKeyPath   = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
$DockerRunVal = 'Docker Desktop'
$DockerExe    = 'C:\Program Files\Docker\Docker\Docker Desktop.exe'
$WslDistros   = @('docker-desktop', 'docker-desktop-data')

$DataDir   = Join-Path $root 'data'
$BackupDir = Join-Path $DataDir 'game_mode_backup'
$StateFile = Join-Path $DataDir 'game_mode.state.json'
$LogFile   = Join-Path $DataDir 'game_mode.log'

New-Item -ItemType Directory -Force -Path $DataDir   | Out-Null
New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null

# --- логування ---
function Log {
    param([string]$Msg, [string]$Color = 'Gray')
    $line = "{0} {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Msg
    Add-Content -Path $LogFile -Value $line
    Write-Host $Msg -ForegroundColor $Color
}
function Head { param([string]$Msg) Write-Host ''; Write-Host "  $Msg" -ForegroundColor Cyan }

# --- порт -> PID через netstat (без залежності від модуля NetTCPIP) ---
# netstat викликаємо один раз на запуск і кешуємо (швидше + не блокує).
$script:NetstatCache = $null
function Get-NetstatListen {
    if ($null -eq $script:NetstatCache) {
        $script:NetstatCache = @(& netstat -ano -p TCP 2>$null | Select-String -Pattern 'LISTENING')
    }
    return $script:NetstatCache
}
function Get-PidsOnPort {
    param([int]$Port)
    $found = @()
    foreach ($ln in (Get-NetstatListen)) {
        $parts = ($ln.ToString().Trim() -split '\s+')
        if ($parts.Length -ge 5 -and $parts[3] -eq 'LISTENING') {
            $localPort = ($parts[1] -split ':')[-1]
            if ($localPort -eq "$Port" -and $parts[4] -match '^\d+$') {
                $found += [int]$parts[4]
            }
        }
    }
    return ($found | Sort-Object -Unique)
}

# зупинити процес, що слухає порт (з перевіркою імені, щоб не вбити чуже)
function Stop-PortService {
    param([int]$Port, [string]$Label, [string[]]$Expect)
    $procIds = Get-PidsOnPort -Port $Port
    if (-not $procIds) { Log "  - $Label (:$Port): не запущено" 'DarkGray'; return }
    foreach ($procId in $procIds) {
        $p = Get-Process -Id $procId -ErrorAction SilentlyContinue
        if (-not $p) { continue }
        if ($Expect -and ($Expect -notcontains $p.ProcessName)) {
            Log "  ! $Label (:$Port): пропущено pid=$procId ($($p.ProcessName)) — не очікуваний процес" 'Yellow'
            continue
        }
        try {
            Stop-Process -Id $procId -Force -ErrorAction Stop
            Log "  + $Label (:$Port): зупинено pid=$procId ($($p.ProcessName))" 'Green'
        } catch {
            Log "  ! $Label (:$Port): не вдалося зупинити pid=$procId — $($_.Exception.Message)" 'Yellow'
        }
    }
}

function Stop-ByName {
    param([string[]]$Names, [string]$Label)
    $any = $false
    foreach ($n in $Names) {
        $procs = Get-Process -Name $n -ErrorAction SilentlyContinue
        if ($procs) {
            $any = $true
            try {
                $procs | Stop-Process -Force -ErrorAction Stop
                Log "  + ${Label}: зупинено '$n' ($($procs.Count) проц.)" 'Green'
            } catch {
                Log "  ! ${Label}: '$n' — $($_.Exception.Message)" 'Yellow'
            }
        }
    }
    if (-not $any) { Log "  - ${Label}: не запущено" 'DarkGray' }
}

# --- стан (state-файл лише для бекапу значень реєстру) ---
function Read-State {
    if (Test-Path $StateFile) {
        try { return (Get-Content $StateFile -Raw | ConvertFrom-Json) } catch { return $null }
    }
    return $null
}
function Write-State {
    param([string]$Mode, $DockerRunBackup)
    $obj = [pscustomobject]@{
        mode            = $Mode
        changedAt       = (Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
        dockerRunBackup = $DockerRunBackup
    }
    $obj | ConvertTo-Json | Set-Content -Path $StateFile -Encoding UTF8
}

# --- Watchdog-таск через COM Schedule.Service ---
# Get-ScheduledTask (CIM) у свіжому дочірньому powershell тут підвисає,
# тож працюємо через класичний Task Scheduler COM API (швидко, локаленезалежно).
function Get-WatchdogTask {
    try {
        $svc = New-Object -ComObject Schedule.Service
        $svc.Connect()
        return $svc.GetFolder('\').GetTask($TaskName)   # кидає виняток, якщо немає
    } catch { return $null }
}
# State: 1=Disabled, 2=Queued, 3=Ready, 4=Running
function Get-WatchdogStateText {
    $t = Get-WatchdogTask
    if (-not $t) { return 'відсутній' }
    switch ([int]$t.State) {
        1 { 'Disabled' }
        4 { 'Running' }
        default { 'Ready' }
    }
}
function Set-WatchdogEnabled {
    param([bool]$Enabled)
    $t = Get-WatchdogTask
    if ($t) {
        try {
            $t.Enabled = $Enabled
            if (-not $Enabled) { try { $t.Stop(0) | Out-Null } catch {} }  # зупинити активний інстанс
            return $true
        } catch { }
    }
    # фолбек: schtasks (прапорці не локалізуються)
    $flag = if ($Enabled) { '/ENABLE' } else { '/DISABLE' }
    & schtasks /Change /TN $TaskName $flag 2>$null | Out-Null
    return ($LASTEXITCODE -eq 0)
}
# джерело правди про режим: Watchdog Disabled => game mode ON
function Get-CurrentMode {
    $t = Get-WatchdogTask
    if ($t -and -not $t.Enabled) { return 'on' }
    return 'off'
}

function Test-DockerEngine {
    & docker info --format '{{.ServerVersion}}' 2>$null | Out-Null
    return ($LASTEXITCODE -eq 0)
}

# cloudflared може бути СЛУЖБОЮ (named tunnel) — її Stop-Process не бере (Access denied),
# треба Stop-Service/Set-Service, а це вимагає адмінських прав.
function Get-CloudflaredService {
    return (Get-Service -Name 'Cloudflared', 'cloudflared' -ErrorAction SilentlyContinue | Select-Object -First 1)
}

# вимкнути Startup-ярлик: перенести в бекап. З ретраями — файл буває тимчасово
# зайнятий процесом (напр., Ollama тримає свій ярлик, поки жива).
function Disable-StartupFile {
    param([string]$Name)
    $src = Join-Path $StartupDir $Name
    if (-not (Test-Path $src)) { Log "  - Startup '$Name': вже відсутній" 'DarkGray'; return }
    for ($i = 0; $i -lt 3; $i++) {
        try {
            Move-Item -Path $src -Destination (Join-Path $BackupDir $Name) -Force -ErrorAction Stop
            Log "  + Startup: прибрано '$Name'" 'Green'
            return
        } catch {
            if ($i -lt 2) { Start-Sleep -Milliseconds 700 }
            else { Log "  ! Startup '$Name': $($_.Exception.Message)" 'Yellow' }
        }
    }
}

# ====================== STATUS ======================
function Show-Status {
    $script:NetstatCache = $null   # завжди свіжий знімок портів (інакше після зупинки бреше)
    Head 'JARVIS — стан автозапуску та сервісів'

    # автозапуск
    $taskState = Get-WatchdogStateText
    $vbs    = Test-Path (Join-Path $StartupDir $VbsName)
    $oll    = Test-Path (Join-Path $StartupDir $OllamaLnk)
    $runKey = $null
    try { $runKey = (Get-ItemProperty -Path $RunKeyPath -Name $DockerRunVal -ErrorAction Stop).$DockerRunVal } catch { $runKey = $null }

    function Flag([bool]$on) { if ($on) { 'УВІМК' } else { 'вимк' } }
    function ClrBool([bool]$on) { if ($on) { 'Green' } else { 'DarkGray' } }

    Write-Host ''
    Write-Host '  Автозапуск / перевірки:' -ForegroundColor White
    Write-Host ("    Watchdog task (logon+5хв) : {0}" -f $taskState) -ForegroundColor (ClrBool ($taskState -ne 'Disabled' -and $taskState -ne 'відсутній'))
    Write-Host ("    Startup VBS (autostart)   : {0}" -f (Flag $vbs))    -ForegroundColor (ClrBool $vbs)
    Write-Host ("    Startup Ollama.lnk        : {0}" -f (Flag $oll))    -ForegroundColor (ClrBool $oll)
    Write-Host ("    Docker Run (HKCU)         : {0}" -f (Flag ([bool]$runKey))) -ForegroundColor (ClrBool ([bool]$runKey))

    # сервіси
    $dockerUp = Test-DockerEngine
    $ollPort  = [bool](Get-PidsOnPort -Port 11434)
    $haPort    = [bool](Get-PidsOnPort -Port 8400)
    $forgePort = [bool](Get-PidsOnPort -Port 7860)
    $contPort  = [bool](Get-PidsOnPort -Port 65432)
    $cf        = [bool](Get-Process -Name cloudflared -ErrorAction SilentlyContinue) -or `
                 [bool]((Get-CloudflaredService) | Where-Object { $_.Status -eq 'Running' })

    Write-Host ''
    Write-Host '  Сервіси:' -ForegroundColor White
    Write-Host ("    Docker engine             : {0}" -f (Flag $dockerUp)) -ForegroundColor (ClrBool $dockerUp)
    Write-Host ("    Ollama        :11434      : {0}" -f (Flag $ollPort))  -ForegroundColor (ClrBool $ollPort)
    Write-Host ("    host-agent    :8400       : {0}" -f (Flag $haPort))   -ForegroundColor (ClrBool $haPort)
    Write-Host ("    SD Forge      :7860       : {0}" -f (Flag $forgePort))-ForegroundColor (ClrBool $forgePort)
    Write-Host ("    Continue      :65432      : {0}" -f (Flag $contPort)) -ForegroundColor (ClrBool $contPort)
    Write-Host ("    cloudflared (tunnel)      : {0}" -f (Flag $cf))       -ForegroundColor (ClrBool $cf)

    $mode = Get-CurrentMode
    Write-Host ''
    if ($mode -eq 'on') {
        Write-Host '  ====== GAME MODE: ON (стек має бути зупинений) ======' -ForegroundColor Magenta
    } else {
        Write-Host '  ====== GAME MODE: OFF (нормальний режим, автозапуск активний) ======' -ForegroundColor Cyan
    }
    return $mode
}

# ====================== ENABLE GAME MODE (зупинити все) ======================
function Enable-GameMode {
    Head 'Вмикаю GAME MODE — вимикаю автозапуск і зупиняю стек...'

    # 1) Watchdog: вимкнути + зупинити активний інстанс (щоб не воскресив сервіси)
    if (Get-WatchdogTask) {
        if (Set-WatchdogEnabled $false) { Log "  + Watchdog task вимкнено" 'Green' }
        else { Log "  ! Watchdog: не вдалося вимкнути" 'Yellow' }
    } else {
        Log "  - Watchdog task: відсутній" 'DarkGray'
    }

    Head 'Зупиняю сервіси...'

    # 2) грейсфул-стоп compose, поки движок живий
    if (Test-DockerEngine) {
        Push-Location $root
        & docker compose stop 2>&1 | ForEach-Object { Log "    compose: $_" 'DarkGray' }
        Pop-Location
        Log "  + docker compose stop виконано" 'Green'
    } else {
        Log "  - Docker engine вже не відповідає (пропускаю compose stop)" 'DarkGray'
    }

    # 3) host-agent / SD Forge / Continue — по портах з перевіркою імені
    Stop-PortService -Port 8400  -Label 'host-agent' -Expect @('python')
    Stop-PortService -Port 7860  -Label 'SD Forge'   -Expect @('python')
    Stop-PortService -Port 65432 -Label 'Continue'   -Expect @('node')

    # 4) Ollama (serve + трей)
    Stop-ByName -Names @('ollama', 'ollama app') -Label 'Ollama'

    # 5) cloudflared — як СЛУЖБА (named tunnel, треба адмін) або як процес (quick tunnel)
    $cfSvc = Get-CloudflaredService
    if ($cfSvc) {
        try {
            Set-Service -Name $cfSvc.Name -StartupType Manual -ErrorAction Stop
            Stop-Service -Name $cfSvc.Name -Force -ErrorAction Stop
            Log "  + cloudflared: службу зупинено + автозапуск -> Manual" 'Green'
        } catch {
            Log "  ! cloudflared: це служба, треба адмін (ПКМ по кнопці -> Запуск від адміністратора). Пропущено — вона легка" 'Yellow'
        }
    } else {
        Stop-ByName -Names @('cloudflared') -Label 'cloudflared'
    }

    # 6) Docker Desktop UI + backend, потім звільнити RAM WSL-VM
    Stop-ByName -Names @('Docker Desktop', 'com.docker.backend', 'com.docker.build', 'docker-sandbox') -Label 'Docker Desktop'
    foreach ($d in $WslDistros) {
        & wsl --terminate $d 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) { Log "  + WSL: зупинено '$d' (звільнено RAM)" 'Green' }
    }

    Head 'Вимикаю автозапуск...'

    # 7) Startup-ярлики -> бекап (сервіси вже зупинені, тож файли більше не зайняті)
    Disable-StartupFile -Name $VbsName
    Disable-StartupFile -Name $OllamaLnk

    # 8) Docker Run key -> бекап значення + видалення
    $dockerRunBackup = $null
    try { $dockerRunBackup = (Get-ItemProperty -Path $RunKeyPath -Name $DockerRunVal -ErrorAction Stop).$DockerRunVal } catch { $dockerRunBackup = $null }
    if ($dockerRunBackup) {
        try {
            Remove-ItemProperty -Path $RunKeyPath -Name $DockerRunVal -ErrorAction Stop
            Log "  + HKCU Run '$DockerRunVal': прибрано" 'Green'
        } catch { Log "  ! HKCU Run '$DockerRunVal': $($_.Exception.Message)" 'Yellow' }
    } else { Log "  - HKCU Run '$DockerRunVal': вже відсутній" 'DarkGray' }

    Write-State -Mode 'on' -DockerRunBackup $dockerRunBackup

    Write-Host ''
    Write-Host '  ====== GAME MODE: ON ======' -ForegroundColor Magenta
    Write-Host '  Автозапуск вимкнено, стек зупинено. ПК вільний для ігор.' -ForegroundColor Green
    Write-Host '  Натисни кнопку ще раз, щоб усе повернути.' -ForegroundColor Gray
}

# ====================== DISABLE GAME MODE (відновити) ======================
function Disable-GameMode {
    Head 'Вимикаю GAME MODE — повертаю автозапуск і піднімаю стек...'

    # 1) Watchdog enable
    if (Get-WatchdogTask) {
        if (Set-WatchdogEnabled $true) { Log "  + Watchdog task увімкнено" 'Green' }
        else { Log "  ! Watchdog: не вдалося увімкнути" 'Yellow' }
    } else {
        Log "  ! Watchdog task відсутній — перевстанови: scripts\install_autostart.ps1" 'Yellow'
    }

    # 2) Startup-файли назад
    foreach ($f in @($VbsName, $OllamaLnk)) {
        $bak = Join-Path $BackupDir $f
        $dst = Join-Path $StartupDir $f
        if (Test-Path $bak) {
            try {
                Move-Item -Path $bak -Destination $dst -Force -ErrorAction Stop
                Log "  + Startup: повернуто '$f'" 'Green'
            } catch { Log "  ! Startup '$f': $($_.Exception.Message)" 'Yellow' }
        } elseif (Test-Path $dst) {
            Log "  - Startup '$f': вже на місці" 'DarkGray'
        } else {
            Log "  ! Startup '$f': бекап відсутній (пропускаю)" 'Yellow'
        }
    }

    # 3) Docker Run key назад
    $st = Read-State
    $val = $null
    if ($st -and $st.dockerRunBackup) { $val = $st.dockerRunBackup }
    if (-not $val -and (Test-Path $DockerExe)) { $val = $DockerExe }  # розумний дефолт
    if ($val) {
        try {
            New-ItemProperty -Path $RunKeyPath -Name $DockerRunVal -Value $val -PropertyType String -Force -ErrorAction Stop | Out-Null
            Log "  + HKCU Run '$DockerRunVal': відновлено" 'Green'
        } catch { Log "  ! HKCU Run '$DockerRunVal': $($_.Exception.Message)" 'Yellow' }
    }

    # 4) cloudflared-служба назад (Automatic + запуск), якщо є і є права
    $cfSvc = Get-CloudflaredService
    if ($cfSvc) {
        try {
            Set-Service -Name $cfSvc.Name -StartupType Automatic -ErrorAction Stop
            Start-Service -Name $cfSvc.Name -ErrorAction Stop
            Log "  + cloudflared: службу повернено (Automatic + запущено)" 'Green'
        } catch {
            Log "  ! cloudflared: відновлення служби потребує адмін (пропущено)" 'Yellow'
        }
    }

    Write-State -Mode 'off' -DockerRunBackup $null

    # 5) Підняти стек у фоні так само, як це робить логон (autostart.ps1, hidden)
    $autostart = Join-Path $PSScriptRoot 'autostart.ps1'
    if (Test-Path $autostart) {
        Start-Process -FilePath 'powershell.exe' -ArgumentList @(
            '-NoProfile', '-ExecutionPolicy', 'Bypass', '-WindowStyle', 'Hidden',
            '-File', "`"$autostart`"", '-SkipVerify'
        ) -WorkingDirectory $root
        Log "  + autostart.ps1 запущено у фоні" 'Green'
    } else {
        Log "  ! autostart.ps1 не знайдено — стек доведеться підняти вручну" 'Yellow'
    }

    Write-Host ''
    Write-Host '  ====== GAME MODE: OFF ======' -ForegroundColor Cyan
    Write-Host '  Автозапуск повернено. Стек піднімається у фоні (~1-3 хв, чекає Docker).' -ForegroundColor Green
    Write-Host '  Watchdog добʼє решту протягом 5 хв.' -ForegroundColor Gray
}

# ====================== MAIN ======================
Write-Host ''
Write-Host '  ╔══════════════════════════════════╗' -ForegroundColor Cyan
Write-Host '  ║      JARVIS  ·  GAME  MODE        ║' -ForegroundColor Cyan
Write-Host '  ╚══════════════════════════════════╝' -ForegroundColor Cyan

$action = 'toggle'
if ($Status) { $action = 'status' }
elseif ($On) { $action = 'on' }
elseif ($Off) { $action = 'off' }
elseif ($Toggle) { $action = 'toggle' }

if ($action -eq 'toggle') {
    $cur = Get-CurrentMode
    if ($cur -eq 'on') { $action = 'off' } else { $action = 'on' }
    Write-Host ("  Поточний стан: {0}  ->  перемикаю на: {1}" -f $cur.ToUpper(), $action.ToUpper()) -ForegroundColor White
}

switch ($action) {
    'status' { Show-Status | Out-Null }
    'on'     { Enable-GameMode;  Write-Host ''; Show-Status | Out-Null }
    'off'    { Disable-GameMode; Write-Host ''; Show-Status | Out-Null }
}

Log "action=$action done" 'DarkGray'

if (-not $Quiet) {
    Write-Host ''
    Read-Host '  Натисни Enter, щоб закрити'
}
