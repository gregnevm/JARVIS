# JARVIS — Mobile MVP (Android APK)

> **Стовп C, CL-3** — рідний Android-клієнт поверх власного JARVIS-сервера.
> MVP: тонкий WebView, що відкриває твою веб-консоль/Mini App; адреса сервера
> налаштовується при першому запуску (LAN або tunnel). Без бізнес-логіки на
> клієнті (AGENTS.md S3).

## Що вміє MVP (v0.1.0)

- Перший запуск питає **URL сервера** (напр. `http://192.168.0.100:8000/app`), зберігає його.
- Відкриває JARVIS у WebView (JS, DOM-storage, медіа, mixed-content для LAN).
- Меню: **Оновити** · **Змінити сервер**. Кнопка «Назад» — навігація історією WebView.
- Дозвіл мікрофона прокинуто у WebView (ґрунт під voice, CL-3.4).
- `usesCleartextTraffic` + network-security-config — працює по http у локальній мережі.

Свідомо **не** в MVP (наступні CL-3.x): нативний JWT-логін, SSE-стрім поза webview,
FCM-push, native computer-confirm. Див. [`docs/CLIENTS_ROADMAP.md`](../docs/CLIENTS_ROADMAP.md).

## Структура

```
mobile/
  settings.gradle · build.gradle · gradle.properties   # Gradle (AGP 8.5, без AndroidX)
  app/build.gradle
  app/src/main/AndroidManifest.xml
  app/src/main/java/ai/jarvis/mvp/MainActivity.java     # увесь клієнт (1 Activity)
  app/src/main/res/values/{strings,themes}.xml
  app/src/main/res/xml/network_security_config.xml
  app/src/main/res/drawable/ic_launcher.png             # генерується tools/make_icon.py
  build-apk.ps1                                         # self-contained білд (Windows)
  build-apk.sh                                          # self-contained білд (Linux/macOS)
  gradlew / gradle/wrapper/                             # Gradle wrapper (8.7) — спільний для CI/локалі
  VERSION                                               # 1.0.0
```

## Збірка APK

Версіонована через Gradle **wrapper** (`./gradlew`, Gradle 8.7) — CI й локальна збірка
використовують ту саму версію. Три способи:

### CI (рекомендовано) — GitHub Actions

Workflow `.github/workflows/build-apk.yml` збирає APK у хмарі (не треба локального SDK):
ручний запуск (**Actions → Build APK → Run**), пуш у `main` зі змінами в `mobile/**`,
або тег `mobile-v*` (додатково створює **GitHub Release** з APK). Артефакт —
`jarvis-mvp-apk`. Для стабільного підпису (оновлення без перевстановлення) поклади
base64-keystore у secret `ANDROID_KEYSTORE_BASE64` (+ `ANDROID_KEYSTORE_PASS`,
`ANDROID_KEY_ALIAS`); без секрету підпис ефемерний.

### Linux / macOS

```bash
bash mobile/build-apk.sh          # повна збірка   (SKIP_BUILD=1 — лише тулчейн)
```

JDK і Android SDK беруться з оточення, якщо є; інакше SDK качається локально у
`mobile/.toolchain/`. Потрібен лише **JDK 17+** у системі.

### Windows (self-contained)

На машині **не** потрібні заздалегідь JDK/Android SDK/Gradle — скрипт качає їх
локально у `mobile/.toolchain/` (у `.gitignore`):

```powershell
pwsh -File mobile\build-apk.ps1
# або в Windows PowerShell:
powershell -ExecutionPolicy Bypass -File mobile\build-apk.ps1
```

Що роблять скрипти (`.sh` / `.ps1`):
1. Готують **Android cmdline-tools** (+ `platform-34`, `build-tools;34.0.0`); `.ps1` ще й тягне Temurin JDK 17.
2. Приймають ліцензії SDK, пишуть `local.properties` (`sdk.dir`), генерують release-keystore.
3. `./gradlew assembleRelease` → `app/build/outputs/apk/release/app-release.apk` + apksigner re-sign (v1+v2+v3).
4. Копіюють у **`data/artifacts/jarvis-mvp.apk`** + паспорт `*.meta.json` (version/git/sha256).

> `data/` змонтовано в gateway як `/data` → бот одразу бачить новий apk для `/apk`.

Параметри: `-SkipBuild` — лише підготувати тулчейн.

## Доставка у Telegram

- **Авто адміну після білду:**
  ```powershell
  python scripts\send_apk_to_admin.py
  ```
- **Команда `/apk`** у боті — завжди віддає поточний `data/artifacts/jarvis-mvp.apk`
  (реалізація: `gateway/app/bot/apk.py` + `gateway/app/apk_artifact.py`).

## Встановлення на телефон

1. Перекинь `jarvis-mvp.apk` на пристрій (Telegram `/apk`, USB, або хмара).
2. Дозволь «Встановлення з невідомих джерел» для джерела.
3. Відкрий додаток → введи адресу свого JARVIS (LAN-IP:8000/app або tunnel-URL).

> Debug-підпис: для особистого/тестового встановлення достатньо. Release-підпис
> власним keystore — CL-3.8.

## Регенерація іконки

```powershell
python mobile\tools\make_icon.py
```
