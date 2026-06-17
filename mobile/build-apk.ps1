<#
.SYNOPSIS
  Build the JARVIS MVP Android APK (Pillar C / CL-3) self-contained.

.DESCRIPTION
  Bootstraps a LOCAL toolchain under mobile/.toolchain (JDK 17 + Android SDK
  cmdline-tools/platform/build-tools + Gradle), then runs Gradle assembleDebug.
  The resulting signed-debug APK is copied to data/artifacts/jarvis-mvp.apk
  (which Compose mounts into the gateway as /data/artifacts/...), plus a
  <apk>.meta.json passport (version/built_at/git/sha256) for the /apk command.

  Idempotent: re-running skips already-downloaded tools.

.PARAMETER SkipBuild
  Only bootstrap the toolchain, do not run Gradle.
#>
[CmdletBinding()]
param(
    [switch]$SkipBuild
)

# Native tools (java/sdkmanager/gradle) write progress to stderr; under "Stop" with
# any stream-merge that becomes a *terminating* error in PS 5.1. We use "Continue"
# and gate real failures explicitly via $LASTEXITCODE / Test-Path / try-catch.
$ErrorActionPreference = "Continue"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

# ---- paths ------------------------------------------------------------------
$Mobile = $PSScriptRoot
$Repo   = Split-Path $Mobile -Parent
$TC     = Join-Path $Mobile ".toolchain"
$Dl     = Join-Path $TC "downloads"
New-Item -ItemType Directory -Force -Path $TC, $Dl | Out-Null

# Pinned versions (deterministic builds).
$JdkUrl   = "https://github.com/adoptium/temurin17-binaries/releases/download/jdk-17.0.12%2B7/OpenJDK17U-jdk_x64_windows_hotspot_17.0.12_7.zip"
$JdkDir   = Join-Path $TC "jdk-17.0.12+7"
$CltUrl   = "https://dl.google.com/android/repository/commandlinetools-win-11076708_latest.zip"
$Sdk      = Join-Path $TC "android-sdk"
$GradleUrl= "https://services.gradle.org/distributions/gradle-8.7-bin.zip"
$GradleDir= Join-Path $TC "gradle-8.7"

function Write-Step($msg) { Write-Host "==> $msg" -ForegroundColor Cyan }

function Get-File($url, $dest) {
    if (Test-Path $dest) { Write-Host "    cached: $(Split-Path $dest -Leaf)"; return }
    Write-Host "    download: $url"
    try {
        Invoke-WebRequest -Uri $url -OutFile $dest -UseBasicParsing -ErrorAction Stop
    } catch {
        if (Test-Path $dest) { Remove-Item $dest -Force }
        throw "download failed: $url -> $_"
    }
}

function Expand-Zip($zip, $dest) {
    New-Item -ItemType Directory -Force -Path $dest | Out-Null
    Expand-Archive -Path $zip -DestinationPath $dest -Force -ErrorAction Stop
}

# ---- 1. JDK 17 --------------------------------------------------------------
Write-Step "JDK 17 (Temurin)"
if (-not (Test-Path (Join-Path $JdkDir "bin\java.exe"))) {
    $z = Join-Path $Dl "jdk17.zip"
    Get-File $JdkUrl $z
    Expand-Zip $z $TC
}
if (-not (Test-Path (Join-Path $JdkDir "bin\java.exe"))) {
    throw "JDK not found at $JdkDir after extract"
}
$env:JAVA_HOME = $JdkDir
$env:PATH = "$JdkDir\bin;$env:PATH"
# Note: java writes -version to stderr; keep this non-fatal.
try { & "$JdkDir\bin\java.exe" -version } catch { Write-Host "    (java -version note: $_)" }

# ---- 2. Android SDK ---------------------------------------------------------
Write-Step "Android SDK (cmdline-tools + platform-34 + build-tools 34.0.0)"
$CltLatest = Join-Path $Sdk "cmdline-tools\latest"
if (-not (Test-Path (Join-Path $CltLatest "bin\sdkmanager.bat"))) {
    $z = Join-Path $Dl "cmdline-tools.zip"
    Get-File $CltUrl $z
    $tmp = Join-Path $TC "_clt_tmp"
    if (Test-Path $tmp) { Remove-Item -Recurse -Force $tmp }
    Expand-Zip $z $tmp
    New-Item -ItemType Directory -Force -Path (Split-Path $CltLatest -Parent) | Out-Null
    Move-Item (Join-Path $tmp "cmdline-tools") $CltLatest
    Remove-Item -Recurse -Force $tmp
}
$env:ANDROID_HOME = $Sdk
$env:ANDROID_SDK_ROOT = $Sdk
$SdkMgr = Join-Path $CltLatest "bin\sdkmanager.bat"

# Accept licenses ДЕТЕРМІНОВАНО — пишемо хеш-файли прийнятих ліцензій напряму.
# (Старий `$yes | --licenses` ненадійний у PS 5.1: stdin не доходить → пакети skip.)
Write-Host "    accepting licenses (hash files)..."
$licDir = Join-Path $Sdk "licenses"
New-Item -ItemType Directory -Force -Path $licDir | Out-Null
Set-Content -Path (Join-Path $licDir "android-sdk-license") -Encoding ascii -Value @(
    "8933bad161af4178b1185d1a37fbf41ea5269c55",
    "d56f5187479451eabf01fb78af6dfcb131a6481e",
    "24333f8a63b6825ea9c5514f83c2829b004d1fee"
)
Set-Content -Path (Join-Path $licDir "android-sdk-preview-license") -Encoding ascii `
    -Value "84831b9409646a918e30573bab4c9c91346d8abd"
Write-Host "    installing packages..."
& $SdkMgr --sdk_root="$Sdk" "platform-tools" "platforms;android-34" "build-tools;34.0.0"
if ($LASTEXITCODE -ne 0) { throw "sdkmanager install failed (exit $LASTEXITCODE)" }

# ---- 3. Gradle 8.7 ----------------------------------------------------------
Write-Step "Gradle 8.7"
$GradleBat = Join-Path $GradleDir "bin\gradle.bat"
if (-not (Test-Path $GradleBat)) {
    $z = Join-Path $Dl "gradle.zip"
    Get-File $GradleUrl $z
    Expand-Zip $z $TC
}
if (-not (Test-Path $GradleBat)) { throw "gradle not found at $GradleBat" }

# ---- 4. local.properties (sdk.dir) -----------------------------------------
$sdkFwd = $Sdk -replace '\\', '/'
Set-Content -Path (Join-Path $Mobile "local.properties") -Value "sdk.dir=$sdkFwd" -Encoding ascii

# ---- 4b. Release keystore + signing props (детермінований підпис) -----------
Write-Step "Release keystore"
$Keystore = Join-Path $TC "release.jks"
$KeyTool = Join-Path $JdkDir "bin\keytool.exe"
if (-not (Test-Path $Keystore)) {
    Write-Host "    generating release keystore..."
    & $KeyTool -genkeypair -keystore $Keystore -alias jarvis -keyalg RSA -keysize 2048 `
        -validity 10000 -storepass jarvis123 -keypass jarvis123 `
        -dname "CN=JARVIS, O=JARVIS, C=UA" 2>&1 | Out-Null
    if (-not (Test-Path $Keystore)) { throw "keystore generation failed" }
} else {
    Write-Host "    cached keystore"
}
$ksFwd = $Keystore -replace '\\', '/'
Set-Content -Path (Join-Path $Mobile "keystore.properties") -Encoding ascii -Value @(
    "storeFile=$ksFwd",
    "storePassword=jarvis123",
    "keyAlias=jarvis",
    "keyPassword=jarvis123"
)

if ($SkipBuild) { Write-Step "Toolchain ready (SkipBuild set). Done."; return }

# ---- 5. Build (signed release) ----------------------------------------------
Write-Step "gradle assembleRelease"
Push-Location $Mobile
try {
    & $GradleBat --no-daemon -p $Mobile assembleRelease
    if ($LASTEXITCODE -ne 0) { throw "gradle assembleRelease failed (exit $LASTEXITCODE)" }
} finally {
    Pop-Location
}

$apk = Join-Path $Mobile "app\build\outputs\apk\release\app-release.apk"
if (-not (Test-Path $apk)) { throw "APK not produced at $apk" }

# ---- 5b. Force v1+v2+v3 signing (root-fix for "App not installed") ----------
# AGP 8 disables v1 (JAR) signing at minSdk>=24; some installers/OEMs then reject
# the APK. Direct apksigner re-sign guarantees all schemes for max compatibility.
Write-Step "apksigner re-sign (v1+v2+v3)"
$ApkSigner = Get-ChildItem (Join-Path $Sdk "build-tools") -Recurse -Filter "apksigner.bat" |
    Select-Object -First 1 -ExpandProperty FullName
if ($ApkSigner) {
    $env:JAVA_HOME = $JdkDir
    & $ApkSigner sign --ks $Keystore --ks-pass "pass:jarvis123" --key-pass "pass:jarvis123" --v1-signing-enabled true --v2-signing-enabled true --v3-signing-enabled true --min-sdk-version 24 $apk
    if ($LASTEXITCODE -ne 0) { throw "apksigner re-sign failed (exit $LASTEXITCODE)" }
    & $ApkSigner verify --verbose $apk
} else {
    Write-Host "    WARN: apksigner not found, keeping AGP signatures" -ForegroundColor Yellow
}

# ---- 6. Publish artifact + passport ----------------------------------------
Write-Step "publish artifact -> data/artifacts/jarvis-mvp.apk"
$artDir = Join-Path $Repo "data\artifacts"
New-Item -ItemType Directory -Force -Path $artDir | Out-Null
$outApk = Join-Path $artDir "jarvis-mvp.apk"
Copy-Item $apk $outApk -Force

$version = (Get-Content (Join-Path $Mobile "VERSION") -Raw).Trim()
$sha = (Get-FileHash $outApk -Algorithm SHA256).Hash.ToLower()
$git = ""
try { $git = (& git -C $Repo rev-parse --short HEAD).Trim() } catch {}
$built = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
$meta = [ordered]@{
    version   = $version
    built_at  = $built
    git       = $git
    sha256    = $sha
    size      = (Get-Item $outApk).Length
    applicationId = "ai.jarvis.mvp"
}
$meta | ConvertTo-Json | Set-Content -Path "$outApk.meta.json" -Encoding ascii

Write-Host ""
Write-Host "OK  APK: $outApk" -ForegroundColor Green
Write-Host "    version=$version sha256=$($sha.Substring(0,12)) size=$($meta.size) bytes" -ForegroundColor Green
Write-Host "    Send to admin:  python scripts/send_apk_to_admin.py" -ForegroundColor Green
