# Installs JARVIS autostart at Windows logon (no admin required).
# Drops a hidden launcher into the per-user Startup folder that runs autostart.ps1.
# Run once: powershell -File scripts/install_autostart.ps1
# Remove:   powershell -File scripts/install_autostart.ps1 -Uninstall

param([switch]$Uninstall)

$ErrorActionPreference = 'Stop'
$script = Join-Path $PSScriptRoot 'autostart.ps1'
$startup = [Environment]::GetFolderPath('Startup')
$vbs = Join-Path $startup 'JARVIS-Autostart.vbs'

if ($Uninstall) {
    if (Test-Path $vbs) { Remove-Item $vbs -Force; Write-Host "Removed: $vbs" }
    else { Write-Host "Nothing to remove." }
    return
}

if (-not (Test-Path $script)) { throw "Not found: $script" }

# Persist Ollama env (so manual launch / Ollama desktop app also bind 0.0.0.0).
[Environment]::SetEnvironmentVariable('OLLAMA_HOST', '0.0.0.0:11434', 'User')
[Environment]::SetEnvironmentVariable('OLLAMA_KEEP_ALIVE', '24h', 'User')
[Environment]::SetEnvironmentVariable('OLLAMA_VULKAN', '1', 'User')

# VBS shim runs PowerShell fully hidden (window mode 0) -> no console flash at logon.
# Build a single-line Run statement; double inner quotes for VBScript string escaping.
$inner = 'powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + $script + '"'
$vbsArg = $inner -replace '"', '""'
$vbsBody = 'Set sh = CreateObject("WScript.Shell")' + "`r`n" + 'sh.Run "' + $vbsArg + '", 0, False' + "`r`n"
[System.IO.File]::WriteAllText($vbs, $vbsBody, [System.Text.Encoding]::ASCII)

Write-Host "Installed autostart launcher:"
Write-Host "  $vbs"
Write-Host "It runs scripts/autostart.ps1 (Ollama + Docker stack) at every logon."
