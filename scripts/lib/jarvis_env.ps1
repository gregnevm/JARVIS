# JARVIS .env helpers (preserve comments, update keys in place).
# Dot-source: . "$PSScriptRoot\lib\jarvis_env.ps1"

function Get-EnvFileValue {
    param([string]$Path, [string]$Key)
    if (-not (Test-Path $Path)) { return '' }
    foreach ($line in Get-Content -LiteralPath $Path -Encoding UTF8) {
        $t = $line.Trim()
        if ($t.StartsWith('#') -or -not $t.Contains('=')) { continue }
        if ($t -match "^$([regex]::Escape($Key))=(.*)$") {
            return $Matches[1].Trim()
        }
    }
    return ''
}

function Set-EnvFileValue {
    param(
        [string]$Path,
        [string]$Key,
        [string]$Value,
        [switch]$OnlyIfEmpty
    )
    if (-not (Test-Path $Path)) { throw ".env not found: $Path" }

    if ($OnlyIfEmpty) {
        $cur = Get-EnvFileValue -Path $Path -Key $Key
        if (-not [string]::IsNullOrWhiteSpace($cur)) { return $false }
    }

    $lines = Get-Content -LiteralPath $Path -Encoding UTF8
    $pattern = "^$([regex]::Escape($Key))="
    $found = $false
    $out = foreach ($line in $lines) {
        if ($line -match $pattern) {
            $found = $true
            "$Key=$Value"
        } else { $line }
    }
    if (-not $found) {
        $out = @($out) + "$Key=$Value"
    }
    $utf8bom = New-Object System.Text.UTF8Encoding $true
    [System.IO.File]::WriteAllText($Path, ($out -join "`r`n") + "`r`n", $utf8bom)
    return $true
}

function Set-EnvFileValues {
    param(
        [string]$Path,
        [hashtable]$Values,
        [switch]$OnlyIfEmpty
    )
    foreach ($kv in $Values.GetEnumerator()) {
        if ($null -eq $kv.Value) { continue }
        [void](Set-EnvFileValue -Path $Path -Key $kv.Key -Value ([string]$kv.Value) -OnlyIfEmpty:$OnlyIfEmpty)
    }
}

function New-JarvisSecret {
    param([int]$Bytes = 24)
    $buf = New-Object byte[] $Bytes
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($buf)
    -join ($buf | ForEach-Object { $_.ToString('x2') })
}

function Ensure-JarvisEnvFile {
    param([string]$Root)
    $envPath = Join-Path $Root '.env'
    $example = Join-Path $Root '.env.example'
    if (-not (Test-Path $envPath)) {
        if (-not (Test-Path $example)) { throw ".env.example missing" }
        Copy-Item -LiteralPath $example -Destination $envPath
    }
    return $envPath
}
