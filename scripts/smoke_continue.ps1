# Smoke test continue_dev: host-agent open + Continue API from tools container.
#   .\scripts\smoke_continue.ps1

$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root
. (Join-Path $PSScriptRoot 'lib\jarvis_continue.ps1')

$cfg = Import-ContinueEnvFromDotenv -Root $root
if ($cfg.ENABLE_CONTINUE_DEV -ne 'true') {
    Write-Host '[FAIL] ENABLE_CONTINUE_DEV=false' -ForegroundColor Red
    exit 1
}

$port = Get-ContinueDevPort -Url $cfg.CONTINUE_DEV_URL
if (-not (Test-ContinueApi -Port $port)) {
    Write-Host "[FAIL] Continue API not on :$port — run start_continue.ps1" -ForegroundColor Red
    exit 1
}
Write-Host "[OK] Continue API :$port" -ForegroundColor Green

$out = docker exec jarvis-tools-1 python -c @"
import asyncio
from app.tools.continue_tool import run

async def main():
    print(await run('get_status'))
    r = await run('send_prompt', prompt='reply with exactly: jarvis-smoke-ok')
    print('SEND:', r[:200])

asyncio.run(main())
"@ 2>&1

Write-Host $out
if ($out -match 'jarvis-smoke-ok') {
    Write-Host '[OK] send_prompt from tools container' -ForegroundColor Green
    exit 0
}
Write-Host '[WARN] send_prompt did not return jarvis-smoke-ok (auth/model may vary)' -ForegroundColor Yellow
if ($out -match 'isProcessing=') {
    Write-Host '[OK] get_status reachable from tools' -ForegroundColor Green
    exit 0
}
exit 1
