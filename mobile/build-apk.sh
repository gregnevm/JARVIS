#!/usr/bin/env bash
# Build the JARVIS MVP Android APK (Pillar C / CL-3) on Linux — bash-порт build-apk.ps1.
#
# Бутстрапить локальний тулчейн під mobile/.toolchain (Android SDK cmdline-tools +
# platform-34 + build-tools 34.0.0), генерує release-keystore, збирає signed-release
# через ./gradlew і публікує APK у data/artifacts/jarvis-mvp.apk + <apk>.meta.json
# (паспорт version/built_at/git/sha256 для команди /apk).
#
# JDK і Android SDK беруться з оточення, якщо вже є (CI: setup-java + setup-android),
# інакше SDK качається локально. Ідемпотентний: повторний запуск пропускає готове.
#
#   ./mobile/build-apk.sh            # повна збірка
#   SKIP_BUILD=1 ./mobile/build-apk.sh   # лише тулчейн
set -euo pipefail

MOBILE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(dirname "$MOBILE")"
TC="$MOBILE/.toolchain"
DL="$TC/downloads"
mkdir -p "$TC" "$DL"

# Pinned (детермінований білд).
CLT_URL="https://dl.google.com/android/repository/commandlinetools-linux-11076708_latest.zip"
SDK_DEFAULT="$TC/android-sdk"
BUILD_TOOLS_VER="34.0.0"
PLATFORM="android-34"

step() { printf '\033[36m==> %s\033[0m\n' "$1"; }
die()  { printf '\033[31mERROR: %s\033[0m\n' "$1" >&2; exit 1; }

# ---- 1. JDK 17+ -------------------------------------------------------------
step "JDK (потрібен 17+)"
if [ -n "${JAVA_HOME:-}" ] && [ -x "$JAVA_HOME/bin/javac" ]; then
  echo "    JAVA_HOME=$JAVA_HOME"
elif command -v javac >/dev/null 2>&1; then
  export JAVA_HOME="$(dirname "$(dirname "$(readlink -f "$(command -v javac)")")")"
  echo "    JAVA_HOME=$JAVA_HOME (з PATH)"
else
  die "JDK 17+ не знайдено. Встанови (apt install openjdk-17-jdk) або задай JAVA_HOME."
fi
JAVA_MAJOR="$("$JAVA_HOME/bin/java" -version 2>&1 | sed -n 's/.*version "\([0-9]*\).*/\1/p' | head -1)"
[ "${JAVA_MAJOR:-0}" -ge 17 ] 2>/dev/null || die "Потрібен JDK 17+, знайдено $JAVA_MAJOR."

# ---- 2. Android SDK ---------------------------------------------------------
step "Android SDK ($PLATFORM + build-tools $BUILD_TOOLS_VER)"
SDK="${ANDROID_HOME:-${ANDROID_SDK_ROOT:-$SDK_DEFAULT}}"
# Свідомо НЕ беремо випадковий sdkmanager з PATH: CI-образ має ще й застарілий
# `$SDK/tools/bin/sdkmanager` (розуміє лише SDK XML v3 → падає на v4-репозиторії).
# Гарантуємо свіжий modern cmdline-tools/latest — бутстрапимо, якщо його немає
# (GitHub-раннери мають відкритий інтернет, тож завантаження з Google працює).
CLT="$SDK/cmdline-tools/latest"
SDKMGR="$CLT/bin/sdkmanager"
if [ ! -x "$SDKMGR" ]; then
  echo "    bootstrap cmdline-tools → $CLT"
  zip="$DL/cmdline-tools.zip"
  [ -f "$zip" ] || curl -fSL "$CLT_URL" -o "$zip" || die "download cmdline-tools failed"
  tmp="$TC/_clt_tmp"; rm -rf "$tmp"; mkdir -p "$tmp"
  unzip -q "$zip" -d "$tmp"
  mkdir -p "$SDK/cmdline-tools"
  rm -rf "$CLT"
  mv "$tmp/cmdline-tools" "$CLT"
  rm -rf "$tmp"
fi
export ANDROID_HOME="$SDK" ANDROID_SDK_ROOT="$SDK"
echo "    sdkmanager: $SDKMGR"
"$SDKMGR" --version 2>&1 | sed 's/^/    sdkmanager v/' | head -1 || true

# Прийняти ліцензії детерміновано (hash-файли) — як у PS1, без інтерактиву.
echo "    accepting licenses (hash files)…"
mkdir -p "$SDK/licenses"
printf '%s\n' \
  8933bad161af4178b1185d1a37fbf41ea5269c55 \
  d56f5187479451eabf01fb78af6dfcb131a6481e \
  24333f8a63b6825ea9c5514f83c2829b004d1fee > "$SDK/licenses/android-sdk-license"
printf '%s\n' 84831b9409646a918e30573bab4c9c91346d8abd > "$SDK/licenses/android-sdk-preview-license"
echo "    installing packages…"
yes 2>/dev/null | "$SDKMGR" --sdk_root="$SDK" \
  "platform-tools" "platforms;$PLATFORM" "build-tools;$BUILD_TOOLS_VER" 2>&1 \
  | grep -vE '^\[=*>* *\] *[0-9]+% ' | sed 's/^/    /' \
  || true
[ -d "$SDK/platforms/$PLATFORM" ] && [ -d "$SDK/build-tools/$BUILD_TOOLS_VER" ] \
  || die "sdkmanager install failed (platform/build-tools відсутні)"

# ---- 3. local.properties ----------------------------------------------------
printf 'sdk.dir=%s\n' "$SDK" > "$MOBILE/local.properties"

# ---- 4. Release keystore + signing props (детермінований підпис) ------------
step "Release keystore"
KS="${ANDROID_KEYSTORE_PATH:-$TC/release.jks}"
KS_PASS="${ANDROID_KEYSTORE_PASS:-jarvis123}"
KS_ALIAS="${ANDROID_KEY_ALIAS:-jarvis}"
if [ ! -f "$KS" ]; then
  echo "    generating release keystore…"
  "$JAVA_HOME/bin/keytool" -genkeypair -keystore "$KS" -alias "$KS_ALIAS" -keyalg RSA \
    -keysize 2048 -validity 10000 -storepass "$KS_PASS" -keypass "$KS_PASS" \
    -dname "CN=JARVIS, O=JARVIS, C=UA" >/dev/null 2>&1 || die "keystore generation failed"
else
  echo "    cached keystore"
fi
cat > "$MOBILE/keystore.properties" <<EOF
storeFile=$KS
storePassword=$KS_PASS
keyAlias=$KS_ALIAS
keyPassword=$KS_PASS
EOF

if [ -n "${SKIP_BUILD:-}" ]; then step "Toolchain ready (SKIP_BUILD). Done."; exit 0; fi

# ---- 5. Build (signed release) ----------------------------------------------
step "gradlew assembleRelease"
( cd "$MOBILE" && ./gradlew --no-daemon assembleRelease )
APK="$MOBILE/app/build/outputs/apk/release/app-release.apk"
[ -f "$APK" ] || die "APK not produced at $APK"

# ---- 5b. apksigner re-sign (v1+v2+v3) — root-fix «App not installed» ---------
# AGP 8 при minSdk≥24 вимикає v1 (JAR); частина інсталяторів/OEM тоді відмовляють.
step "apksigner re-sign (v1+v2+v3)"
APKSIGNER="$(find "$SDK/build-tools/$BUILD_TOOLS_VER" -maxdepth 1 -name apksigner 2>/dev/null | head -1 || true)"
if [ -n "$APKSIGNER" ]; then
  "$APKSIGNER" sign --ks "$KS" --ks-pass "pass:$KS_PASS" --key-pass "pass:$KS_PASS" \
    --v1-signing-enabled true --v2-signing-enabled true --v3-signing-enabled true \
    --min-sdk-version 24 "$APK" || die "apksigner re-sign failed"
  "$APKSIGNER" verify --verbose "$APK" | sed 's/^/    /'
else
  echo "    WARN: apksigner не знайдено, лишаю AGP-підписи"
fi

# ---- 6. Publish artifact + passport -----------------------------------------
step "publish artifact → data/artifacts/jarvis-mvp.apk"
ART_DIR="$REPO/data/artifacts"
mkdir -p "$ART_DIR"
OUT="$ART_DIR/jarvis-mvp.apk"
cp -f "$APK" "$OUT"

VERSION="$(tr -d ' \t\r\n' < "$MOBILE/VERSION")"
SHA="$(sha256sum "$OUT" | cut -d' ' -f1)"
SIZE="$(stat -c%s "$OUT")"
GIT="$(git -C "$REPO" rev-parse --short HEAD 2>/dev/null || echo '')"
BUILT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
cat > "$OUT.meta.json" <<EOF
{
  "version": "$VERSION",
  "built_at": "$BUILT",
  "git": "$GIT",
  "sha256": "$SHA",
  "size": $SIZE,
  "applicationId": "ai.jarvis.mvp"
}
EOF

printf '\n\033[32mOK  APK: %s\033[0m\n' "$OUT"
printf '\033[32m    version=%s sha256=%s size=%s bytes\033[0m\n' "$VERSION" "${SHA:0:12}" "$SIZE"
