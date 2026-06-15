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

# xformers 0.0.27 (Forge default) breaks on torch 2.10+ (RTX 50xx / cu128 wheels).
$torchVer = (& $python -c "import torch; print(torch.__version__)" 2>$null)
if ($torchVer -match '^2\.(1[0-9]|[2-9]\d)') {
    $xfOk = & $python -c "import xformers; print(xformers.__version__)" 2>$null
    if ($xfOk -ne "0.0.35") {
        Write-Host "Syncing xformers 0.0.35 for torch $torchVer..." -ForegroundColor Cyan
        & $python -m pip uninstall xformers -y 2>&1 | Out-Null
        & $python -m pip install "xformers==0.0.35" --no-cache-dir
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "xformers upgrade failed — Forge uses --disable-xformers + sdp-attention"
        }
    }
}

$skOk = & $python -c "from skimage import exposure" 2>$null; $LASTEXITCODE -eq 0
if (-not $skOk) {
    Write-Host "Repairing numpy/scikit-image (binary mismatch)..." -ForegroundColor Cyan
    & $python -m pip install --force-reinstall "numpy<2.1" "scikit-image>=0.22,<0.25" -q
    if ($LASTEXITCODE -ne 0) {
        Write-Error "numpy/scikit-image repair failed."
    }
}
