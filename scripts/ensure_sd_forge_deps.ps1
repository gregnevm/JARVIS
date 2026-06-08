# Pin setuptools + pre-install CLIP before Forge launch (setuptools 82+ breaks CLIP build).
# Called from setup_sd_forge.ps1 and start_sd_forge.ps1.

param(
    [Parameter(Mandatory = $true)]
    [string]$ForgeDir
)

$ErrorActionPreference = "Stop"
$python = Join-Path $ForgeDir "venv\Scripts\python.exe"
if (-not (Test-Path $python)) { return }

$clipUrl = "https://github.com/openai/CLIP/archive/d50d76daa670286dd6cacf3bcd80b5e4823fc8e1.zip"

Write-Host "Ensuring Forge venv deps (setuptools pin + CLIP)..." -ForegroundColor DarkGray
& $python -m pip install "setuptools>=69,<82" wheel -q 2>&1 | Out-Null

$clipOk = & $python -c "import importlib.util; print(importlib.util.find_spec('clip') is not None)" 2>$null
if ($clipOk -ne "True") {
    Write-Host "Installing CLIP (setuptools 82+ breaks default pip build)..." -ForegroundColor Cyan
    & $python -m pip install $clipUrl --prefer-binary --no-build-isolation
    if ($LASTEXITCODE -ne 0) {
        Write-Error "CLIP install failed. See output above."
    }
}
