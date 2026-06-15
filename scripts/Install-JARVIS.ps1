# JARVIS first-time setup (Windows). Delegates to FirstSetup.ps1.
# Usage: powershell -ExecutionPolicy Bypass -File scripts\Install-JARVIS.ps1
#        powershell -ExecutionPolicy Bypass -File scripts\FirstSetup.ps1  (recommended)

param(
    [switch]$Auto,
    [switch]$SkipCompose,
    [switch]$StrictProd,
    [switch]$NonInteractive,
    [switch]$InstallMissing
)

$firstSetup = Join-Path $PSScriptRoot 'FirstSetup.ps1'
if (-not (Test-Path $firstSetup)) {
    throw "FirstSetup.ps1 not found: $firstSetup"
}

$args = @()
if ($Auto) { $args += '-Auto' }
if ($SkipCompose) { $args += '-SkipCompose' }
if ($StrictProd) { $args += '-StrictProd' }
if ($NonInteractive) { $args += '-NonInteractive' }
if ($InstallMissing) { $args += '-InstallMissing' }

& $firstSetup @args
exit $LASTEXITCODE
