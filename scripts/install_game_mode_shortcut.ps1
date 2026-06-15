# Кладе кнопки JARVIS Game Mode на робочий стіл.
#   Встановити:  powershell -File scripts/install_game_mode_shortcut.ps1
#   Прибрати:    powershell -File scripts/install_game_mode_shortcut.ps1 -Uninstall
#
# Створює дві іконки:
#   "JARVIS Game Mode"  -> перемикач (зупинити все / повернути все)
#   "JARVIS Status"     -> лише показати стан (read-only)

param([switch]$Uninstall)

$ErrorActionPreference = 'Stop'
$root    = Split-Path $PSScriptRoot -Parent
$engine  = Join-Path $PSScriptRoot 'game_mode.ps1'
$desktop = [Environment]::GetFolderPath('Desktop')

$toggleLnk = Join-Path $desktop 'JARVIS Game Mode.lnk'
$statusLnk = Join-Path $desktop 'JARVIS Status.lnk'

if ($Uninstall) {
    foreach ($p in @($toggleLnk, $statusLnk)) {
        if (Test-Path $p) { Remove-Item $p -Force; Write-Host "Прибрано: $p" }
        else { Write-Host "Немає: $p" }
    }
    return
}

if (-not (Test-Path $engine)) { throw "Не знайдено рушій: $engine" }

function New-JarvisShortcut {
    param([string]$Path, [string]$ScriptArgs, [string]$Desc, [string]$Icon)
    $ws  = New-Object -ComObject WScript.Shell
    $lnk = $ws.CreateShortcut($Path)
    $lnk.TargetPath       = (Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe')
    $lnk.Arguments        = "-NoProfile -ExecutionPolicy Bypass -File `"$engine`" $ScriptArgs"
    $lnk.WorkingDirectory = $root
    $lnk.WindowStyle      = 1            # звичайне вікно (видно прогрес)
    $lnk.Description       = $Desc
    $lnk.IconLocation      = $Icon
    $lnk.Save()
    Write-Host "Створено: $Path"
}

# іконки зі стокових DLL (завжди присутні)
$shell32 = Join-Path $env:SystemRoot 'System32\shell32.dll'

New-JarvisShortcut -Path $toggleLnk -ScriptArgs '-Toggle' `
    -Desc 'JARVIS Game Mode — перемкнути: зупинити весь стек і автозапуск / повернути назад' `
    -Icon "$shell32,27"

New-JarvisShortcut -Path $statusLnk -ScriptArgs '-Status' `
    -Desc 'JARVIS — показати стан автозапуску та сервісів (нічого не змінює)' `
    -Icon "$shell32,23"

Write-Host ''
Write-Host 'Готово. На робочому столі:' -ForegroundColor Green
Write-Host '  • JARVIS Game Mode  — головна кнопка (перемикач)' -ForegroundColor Gray
Write-Host '  • JARVIS Status     — перевірити стан без змін' -ForegroundColor Gray
