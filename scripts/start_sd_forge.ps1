# Start Forge API on :7860 for JARVIS local image gen.
#   .\scripts\start_sd_forge.ps1

$ErrorActionPreference = "Continue"
$root = Split-Path $PSScriptRoot -Parent
$forgeDir = Join-Path $root "vendor\sd-forge"
$logDir = Join-Path $root "data\logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$logFile = Join-Path $logDir "sd-forge.log"

function Test-ForgeApi {
    try {
        Invoke-RestMethod -Uri "http://127.0.0.1:7860/sdapi/v1/options" -TimeoutSec 4 | Out-Null
        return $true
    } catch { return $false }
}

if (Test-ForgeApi) {
    Write-Host "[OK] Forge API already on :7860" -ForegroundColor Green
    exit 0
}

if (-not (Test-Path (Join-Path $forgeDir "webui.py"))) {
    Write-Host "[FAIL] Run setup first: .\scripts\setup_sd_forge.ps1" -ForegroundColor Red
    exit 1
}

& (Join-Path $PSScriptRoot "ensure_sd_forge_deps.ps1") -ForgeDir $forgeDir

$webui = Join-Path $forgeDir "webui.bat"
if (-not (Test-Path $webui)) {
    Write-Host "[FAIL] webui.bat missing in $forgeDir" -ForegroundColor Red
    exit 1
}

# Do not use cmd /c - webui.bat spawns Python and the wrapper exits immediately.
Write-Host "Starting Forge (log: $logFile)..." -ForegroundColor Cyan
$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = $webui
$psi.WorkingDirectory = $forgeDir
$psi.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Minimized
$psi.UseShellExecute = $true
[void][System.Diagnostics.Process]::Start($psi)

Write-Host "Waiting for API (first run: venv + torch, 15-40 min)..."
for ($i = 0; $i -lt 240; $i++) {
    Start-Sleep -Seconds 5
    if (Test-ForgeApi) {
        Write-Host "[OK] Forge API ready on :7860" -ForegroundColor Green
        exit 0
    }
}

Write-Host "[WARN] API not up yet - check $logFile or vendor\sd-forge console" -ForegroundColor Yellow
Write-Host "Tail: Get-Content $logFile -Tail 30 -Wait" -ForegroundColor Gray
exit 0
