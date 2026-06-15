# JARVIS prerequisite install helpers (winget on Windows).
# Dot-source after Ask/Ok/Warn helpers exist in the caller.

function Test-WingetAvailable {
    return [bool](Get-Command winget -ErrorAction SilentlyContinue)
}

function Test-WingetPackageInstalled {
    param([string]$Id)
    if (-not (Test-WingetAvailable)) { return $false }
    & winget list --id $Id -e --disable-interactivity 2>$null | Out-Null
    return ($LASTEXITCODE -eq 0)
}

function Update-SessionPath {
    $machine = [Environment]::GetEnvironmentVariable('Path', 'Machine')
    $user = [Environment]::GetEnvironmentVariable('Path', 'User')
    $env:Path = "$machine;$user"
}

function Invoke-JarvisWingetInstall {
    param(
        [string]$Id,
        [string]$Label,
        [string]$ManualUrl
    )
    if (Test-WingetPackageInstalled -Id $Id) {
        return $false
    }
    if (-not (Test-WingetAvailable)) {
        throw @"
$Label не знайдено, winget теж відсутній.
Встанови вручну: $ManualUrl
Після встановлення перезапусти FirstSetup.
"@
    }
    Write-Host "  winget install $Id ..." -ForegroundColor Gray
    & winget install --id $Id -e --accept-package-agreements --accept-source-agreements --disable-interactivity
    # 0 = ok; -1978335189 (0x8A150009) = already installed / no update
    if ($LASTEXITCODE -ne 0 -and $LASTEXITCODE -ne -1978335189) {
        throw "winget install $Id failed (exit $LASTEXITCODE). Спробуй вручну: $ManualUrl"
    }
    Update-SessionPath
    Start-Sleep -Seconds 3
    return $true
}

function Request-JarvisInstall {
    param(
        [string]$Label,
        [string]$ManualUrl,
        [switch]$InstallMissing,
        [switch]$NonInteractive,
        [scriptblock]$OnAsk
    )
    if ($InstallMissing) { return $true }
    if ($NonInteractive) { return $false }
    $r = & $OnAsk "Встановити $Label через winget? (Y/n)" 'Y'
    return ($r -notmatch '^[nN]')
}

function Wait-DockerEngine {
    param(
        [scriptblock]$TestEngine,
        [scriptblock]$OnOk,
        [int]$MaxSeconds = 360
    )
    $steps = [math]::Max(1, [int]($MaxSeconds / 3))
    for ($i = 0; $i -lt $steps; $i++) {
        if (& $TestEngine) {
            & $OnOk 'Docker engine ready'
            return $true
        }
        Start-Sleep -Seconds 3
    }
    return $false
}

function Ensure-JarvisDocker {
    param(
        [switch]$InstallMissing,
        [switch]$NonInteractive,
        [switch]$Auto,
        [scriptblock]$OnAsk,
        [scriptblock]$OnOk,
        [scriptblock]$OnWarn,
        [scriptblock]$TestEngine
    )

    if (& $TestEngine) {
        & $OnOk 'Docker engine running'
        return @{ Ready = $true; InstalledNow = $false }
    }

    $installedNow = $false
    $dockerCmd = Get-Command docker -ErrorAction SilentlyContinue
    if (-not $dockerCmd) {
        if (Request-JarvisInstall -Label 'Docker Desktop' -ManualUrl 'https://www.docker.com/products/docker-desktop/' `
                -InstallMissing:$InstallMissing -NonInteractive:$NonInteractive -OnAsk $OnAsk) {
            $installedNow = Invoke-JarvisWingetInstall -Id 'Docker.DockerDesktop' -Label 'Docker Desktop' `
                -ManualUrl 'https://www.docker.com/products/docker-desktop/'
            $dockerCmd = Get-Command docker -ErrorAction SilentlyContinue
        }
        if (-not $dockerCmd) {
            throw @"
Docker Desktop не знайдено.
Встанови: https://www.docker.com/products/docker-desktop/
Або: powershell -File scripts\FirstSetup.ps1 -Auto
"@
        }
    }

    $dd = 'C:\Program Files\Docker\Docker\Docker Desktop.exe'
    if (Test-Path $dd) {
        & $OnWarn 'Docker engine не запущений — стартую Docker Desktop...'
        Start-Process -FilePath $dd
    }

    $maxWait = if ($installedNow -or $Auto) { 600 } else { 360 }
    if (Wait-DockerEngine -TestEngine $TestEngine -OnOk $OnOk -MaxSeconds $maxWait) {
        return @{ Ready = $true; InstalledNow = $installedNow }
    }

    return @{ Ready = $false; InstalledNow = $installedNow }
}

function Get-JarvisOllamaExe {
    $cmd = Get-Command ollama -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $local = Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe'
    if (Test-Path $local) { return $local }
    return $null
}

function Ensure-JarvisOllama {
    param(
        [switch]$InstallMissing,
        [switch]$NonInteractive,
        [scriptblock]$OnAsk,
        [scriptblock]$OnOk
    )

    $exe = Get-JarvisOllamaExe
    if ($exe) {
        & $OnOk "Ollama: $exe"
        return $exe
    }

    if (Request-JarvisInstall -Label 'Ollama' -ManualUrl 'https://ollama.com/download' `
            -InstallMissing:$InstallMissing -NonInteractive:$NonInteractive -OnAsk $OnAsk) {
        [void](Invoke-JarvisWingetInstall -Id 'Ollama.Ollama' -Label 'Ollama' `
            -ManualUrl 'https://ollama.com/download')
        $exe = Get-JarvisOllamaExe
    }

    if (-not $exe) {
        throw @"
Ollama не знайдено.
Встанови: https://ollama.com/download
Або: powershell -File scripts\FirstSetup.ps1 -Auto
"@
    }
    & $OnOk "Ollama: $exe"
    return $exe
}

function Ensure-JarvisPython {
    param(
        [switch]$InstallMissing,
        [switch]$NonInteractive,
        [scriptblock]$OnAsk,
        [scriptblock]$OnOk,
        [scriptblock]$OnWarn
    )

    $py = Get-Command python -ErrorAction SilentlyContinue
    if ($py) {
        & $OnOk "Python: $($py.Source)"
        return $true
    }

    if (Request-JarvisInstall -Label 'Python 3.12' -ManualUrl 'https://www.python.org/downloads/' `
            -InstallMissing:$InstallMissing -NonInteractive:$NonInteractive -OnAsk $OnAsk) {
        [void](Invoke-JarvisWingetInstall -Id 'Python.Python.3.12' -Label 'Python 3.12' `
            -ManualUrl 'https://www.python.org/downloads/')
        Update-SessionPath
        $py = Get-Command python -ErrorAction SilentlyContinue
    }

    if (-not $py) {
        & $OnWarn 'Python не знайдено — host-agent пропущено (Computer Use не працюватиме)'
        return $false
    }
    & $OnOk "Python: $($py.Source)"
    return $true
}
