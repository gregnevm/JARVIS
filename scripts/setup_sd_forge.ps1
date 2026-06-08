# One-time Stable Diffusion WebUI Forge install (local image gen).
# Run:  .\scripts\setup_sd_forge.ps1
# Then: .\scripts\start_sd_forge.ps1  (API http://127.0.0.1:7860)

$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$forgeDir = Join-Path $root "vendor\sd-forge"

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Error "git required: https://git-scm.com/download/win"
}

New-Item -ItemType Directory -Force -Path (Split-Path $forgeDir) | Out-Null

if (-not (Test-Path (Join-Path $forgeDir "webui.py"))) {
    Write-Host "Cloning stable-diffusion-webui-forge..." -ForegroundColor Cyan
    git clone --depth 1 https://github.com/lllyasviel/stable-diffusion-webui-forge.git $forgeDir
}

$constraintsPath = Join-Path $forgeDir "pip-constraints.txt"
@'
setuptools>=69,<82
'@ | Set-Content -Path $constraintsPath -Encoding ASCII

$batPath = Join-Path $forgeDir "webui-user.bat"
@'
@echo off
REM JARVIS local txt2img API. NVIDIA: remove --directml, add --xformers if needed.
set PIP_CONSTRAINT=%~dp0pip-constraints.txt
set COMMANDLINE_ARGS=--api --port 7860 --medvram --opt-sdp-attention --no-half-vae --directml --skip-torch-cuda-test
'@ | Set-Content -Path $batPath -Encoding ASCII

& (Join-Path $PSScriptRoot "ensure_sd_forge_deps.ps1") -ForgeDir $forgeDir

Write-Host ""
Write-Host "Done: $forgeDir" -ForegroundColor Green
Write-Host "1) Start:  .\scripts\start_sd_forge.ps1"
Write-Host "2) First run downloads deps (10-30 min). Use SD 1.5 checkpoint for 8GB VRAM."
Write-Host "3) .env: IMAGE_GEN_URL=http://host.docker.internal:7860"
Write-Host "4) docker compose up -d tools"
