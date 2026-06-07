# Installs JARVIS autostart at Windows logon + 5-minute watchdog (no admin required).
#   - Startup folder VBS (hidden PowerShell at logon)
#   - Scheduled task JARVIS-Watchdog (logon + every 5 min, idempotent)
# Run once:  powershell -File scripts/install_autostart.ps1
# Remove:    powershell -File scripts/install_autostart.ps1 -Uninstall

param([switch]$Uninstall)

$ErrorActionPreference = 'Stop'
$script = (Resolve-Path (Join-Path $PSScriptRoot 'autostart.ps1')).Path
$startup = [Environment]::GetFolderPath('Startup')
$vbs = Join-Path $startup 'JARVIS-Autostart.vbs'
$taskName = 'JARVIS-Watchdog'

function Remove-JarvisWatchdogTask {
    $t = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    if ($t) {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
        Write-Host "Removed scheduled task: $taskName"
    }
    cmd /c "schtasks /Delete /TN `"$taskName`" /F >nul 2>&1"
}

function Register-JarvisWatchdogSchtasks {
    param([string]$PsArgs)
    $tr = "powershell.exe $PsArgs"
    cmd /c "schtasks /Delete /TN `"$taskName`" /F >nul 2>&1"
    # Every 5 minutes (idempotent watchdog).
    $out = cmd /c "schtasks /Create /TN `"$taskName`" /TR `"$tr`" /SC MINUTE /MO 5 /F 2>&1"
    if ($LASTEXITCODE -ne 0) {
        throw "schtasks failed (exit $LASTEXITCODE): $out"
    }
    Write-Host "Registered via schtasks (every 5 min): $taskName"
}

if ($Uninstall) {
    if (Test-Path $vbs) { Remove-Item $vbs -Force; Write-Host "Removed: $vbs" }
    else { Write-Host "Startup launcher: not found" }
    Remove-JarvisWatchdogTask
    return
}

if (-not (Test-Path $script)) { throw "Not found: $script" }

$root = Split-Path $PSScriptRoot -Parent
. (Join-Path $PSScriptRoot 'lib\jarvis_hardware.ps1')
$hwProfile = Read-JarvisHardwareProfile -Root $root
if (-not $hwProfile) {
    $hwProfile = Get-JarvisHardwareProfile -GpuInfo (Get-JarvisGpuInfo)
}
# Persist Ollama env (manual launches / Ollama desktop also bind 0.0.0.0).
Apply-JarvisOllamaUserEnv -Profile $hwProfile | Out-Null

# VBS shim: hidden PowerShell at logon (no console flash).
$inner = 'powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + $script + '"'
$vbsArg = $inner -replace '"', '""'
$vbsBody = 'Set sh = CreateObject("WScript.Shell")' + "`r`n" + 'sh.Run "' + $vbsArg + '", 0, False' + "`r`n"
[System.IO.File]::WriteAllText($vbs, $vbsBody, [System.Text.Encoding]::ASCII)

# Scheduled task: logon + repeat every 5 min (keeps stack up after crashes / sleep).
Remove-JarvisWatchdogTask

$psArgs = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$script`""
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $psArgs
$logonTrigger = New-ScheduledTaskTrigger -AtLogOn
$watchTrigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(2) `
    -RepetitionInterval (New-TimeSpan -Minutes 5) `
    -RepetitionDuration (New-TimeSpan -Days 3650)
$taskSettings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 25) `
    -MultipleInstances IgnoreNew
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

$taskOk = $false
try {
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger @($logonTrigger, $watchTrigger) `
        -Settings $taskSettings -Principal $principal `
        -Description 'JARVIS: Ollama, Docker compose, host-agent (idempotent, every 5 min)' | Out-Null
    Write-Host "Registered scheduled task: $taskName (logon + every 5 min)"
    $taskOk = $true
} catch {
    Write-Warning "Register-ScheduledTask failed: $($_.Exception.Message)"
    try {
        Register-JarvisWatchdogSchtasks -PsArgs $psArgs
        $taskOk = $true
    } catch {
        Write-Warning "schtasks fallback failed: $($_.Exception.Message)"
        Write-Warning "Startup VBS still runs at logon; install task manually if needed."
    }
}

Write-Host "Installed JARVIS autostart:"
Write-Host "  Startup: $vbs"
if ($taskOk) { Write-Host "  Task:    $taskName (watchdog)" }
else { Write-Host "  Task:    (not registered - Startup VBS only)" }
Write-Host "Running autostart now..."
& powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File $script
Write-Host "Done. Log: $(Join-Path (Split-Path $PSScriptRoot -Parent) 'data\autostart.log')"
