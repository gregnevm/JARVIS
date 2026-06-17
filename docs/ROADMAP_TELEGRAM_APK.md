# Roadmap — Telegram bot + Mobile APK (handoff)

Документ-передача для продовження **локально**. Фіксує, що вже зроблено в цій сесії,
що лишилось активувати/доробити, і як збирати/тестувати/запускати. Стан `main`: усе
нижче змержено (HEAD на момент створення — `fb15222`).

---

## 0. TL;DR — що зробити в першу чергу

1. **Активувати авто-доставку APK у Telegram** (одна змінна + рестарт):
   ```bash
   git pull
   # у .env додай:  APK_AUTO_DELIVER=true
   docker compose up -d --build gateway        # rebuild (новий код) + recreate (новий .env)
   docker compose logs --since=2m gateway | grep -iE "autodeliver|apk"
   ```
   `restart` НЕ підходить — не перечитує `.env`; потрібен `up -d` (recreate). `--build` —
   бо образ gateway збирається з вихідників, інакше нового коду в контейнері не буде.

2. (Опційно) **Стабільний підпис APK** — щоб оновлення ставились поверх без
   перевстановлення: згенеруй keystore раз, поклади base64 у GitHub Secret
   `ANDROID_KEYSTORE_BASE64` (+ `ANDROID_KEYSTORE_PASS`, `ANDROID_KEY_ALIAS`). Див. §4.

---

## 1. Зроблено в цій сесії (merged у `main`)

| PR | Що | Ключові файли |
|----|----|---------------|
| #20 | **Telegram-бот рефакторинг**: декларативні Command/Callback реєстри замість двох гігантських if/elif; фікс недосяжних `/login`,`/plan`,`/improve`; one-tap авторизація інших ендпоінтів | `gateway/app/bot/dispatch.py`, `bot/commands.py`, `bot/auth_link.py`, `app/auth_links.py`, `app/connect.py` |
| #20 | **Telegram one-tap → веб-консоль**: `/connect/<token>` обмінює токен на JWT-cookie і логінить браузер; cookie як 4-й канал auth | `app/connect.py`, `saas/auth.py` (JWT_COOKIE), `platform/auth.py`, `client_api/deps.py` |
| #24 | **Хмарна збірка APK** (без локального Android SDK) | `.github/workflows/build-apk.yml`, `mobile/build-apk.sh`, `mobile/gradlew` (+wrapper 8.7) |
| #26 | **Аудит + фікси APK → v1.0.1**: підтвердження пейрингу (анти-фішинг), перевірка зʼєднання, UX Telegram-логіну, фікси витоків | `mobile/app/src/main/java/ai/jarvis/mvp/{ChatActivity,TgAuth,IngestClient,Voice}.java` |
| #27 | **Rolling-реліз** `apk-latest` — постійне tap-to-install посилання | `.github/workflows/build-apk.yml` |
| #28 | **Авто-доставка APK у Telegram** через бот (без GitHub-секретів) | `gateway/app/apk_autodeliver.py`, `app/main.py`, `app/config.py` |

**Посилання на APK:** `https://github.com/gregnevm/JARVIS/releases/download/apk-latest/jarvis-mvp.apk`

---

## 2. Архітектура диспетчера бота (для подальшої роботи)

- `bot/dispatch.py` — `CommandRegistry` (декоратор `@registry.command`) + `CallbackRegistry`
  (`@callbacks.callback(prefix)`), `Ctx` / `CbCtx`. **Єдине джерело правди** про команди:
  `is_command`, BotFather-меню (`bot/setup.bot_commands`), `/help` походять звідси.
- Додати команду = один декоратор у `bot/commands.py` (більше не треба синхронити списки).
- Канали авторизації через Telegram: `bot/auth_link.py` (`/connect` → web/app/ext),
  `app/auth_links.py` (mint/redeem), `app/connect.py` (web-редірект + JWT-cookie).

---

## 3. Далі — Mobile APK (пріоритезовано)

Аудит виявив більше, ніж увійшло у v1.0.1. Нижче — РЕАЛЬНІ пункти (хибнопозитиви
автоаудиту відкинуто), що лишаються в межах архітектури «pure-framework, без AndroidX».

### P1 — варті уваги
- [ ] **NtfyService stream-leak** — обгорнути reader у try-with-resources (як уже
      зроблено для `Voice`/`IngestClient`). `mobile/.../NtfyService.java` (loop()).
- [ ] **Permission rationale** — діалог-пояснення ПЕРЕД запитом SMS/calls/mic
      (`SettingsActivity`, `ChatActivity.voice`) + обробка `onRequestPermissionsResult`.
- [ ] **JobScheduler constraints** — `setRequiresBatteryNotLow(true)` +
      `setBackoffCriteria(EXPONENTIAL)` у `CollectorScheduler`.
- [ ] **UpdateChecker silent fail** — показувати статус, якщо `/platform/api/apk/info`
      недоступний (зараз тихо ігнориться).

### P2 — полірування / безпека (зважено)
- [ ] **Cleartext HTTP** (`network_security_config.xml`, `usesCleartextTraffic`) —
      звузити cleartext до приватних діапазонів (192.168/10/172.16-31 + localhost),
      решта → HTTPS. ⚠️ Ризик зламати наявний LAN-сетап — тестувати.
- [ ] **WebView permission grant** (`MainActivity.onPermissionRequest`) — давати
      ресурси лише для origin власного сервера, не будь-якій сторінці.
- [ ] **EventQueue.delete** — параметризований `delete()` замість `execSQL` з конкатенацією.
- [ ] **ProGuard/minify** (`app/build.gradle`) — `minifyEnabled true` + `proguard-rules.pro`.
- [ ] **minSdk 24 → 26** — лише якщо не треба Android 7; інакше лишити.

---

## 4. Далі — інфраструктура доставки / релізи

- [ ] **Стабільний keystore** для відтворюваного підпису (апдейт без reinstall):
      ```bash
      keytool -genkeypair -keystore release.jks -alias jarvis -keyalg RSA -keysize 2048 \
        -validity 10000 -storepass <PASS> -keypass <PASS> -dname "CN=JARVIS, O=JARVIS, C=UA"
      base64 -w0 release.jks   # → GitHub Secret ANDROID_KEYSTORE_BASE64
      ```
      + секрети `ANDROID_KEYSTORE_PASS`, `ANDROID_KEY_ALIAS`. CI підхопить автоматично.
- [ ] **Семвер-релізи**: тег `mobile-v1.0.1` → `git tag mobile-v1.0.1 && git push origin mobile-v1.0.1`
      → workflow створює окремий GitHub Release (на додачу до rolling `apk-latest`).
- [ ] (Опц.) **CI → Telegram напряму**: секрети `TELEGRAM_BOT_TOKEN` + `TELEGRAM_TO_CHAT_ID`
      → крок `Send APK to Telegram` шле APK на кожен білд (альтернатива gateway-авто-доставці).
- [ ] (Опц.) **`/apk check`** — ручний тригер перевірки релізу в боті (викликає
      `apk_autodeliver.check_once`).

---

## 5. Відомі баги / борг (поза цією сесією)

- [ ] **`cmpA:` (admin PowerShell) callback недосяжний** — диспетчер маршрутизує лише
      `cmp:`, а `"cmpA:...".startswith("cmp:")` = False, тож admin-PS підтвердження не
      доходить до `handle_computer_callback`. Pre-existing; не чіпав свідомо (security-sensitive).
      Фікс: зареєструвати окремий префікс `"cmpA:"` у `CallbackRegistry` АБО нормалізувати.
      Файли: `bot/commands.py` (callback-реєстр), `bot/computer.py` (handle_computer_callback).

---

## 6. Локальна розробка / перевірка

**Тести + типи (по-сервісно, з кореня репо):**
```bash
pip install -r gateway/requirements.txt -r requirements-dev.txt
mypy gateway/app                 # strict, має бути clean
pytest gateway/tests             # 428 passed, 2 skipped
mypy jarvis_core && pytest jarvis_core/tests   # 129 passed
```

**Зібрати APK локально:**
```bash
bash mobile/build-apk.sh         # Linux/macOS (потрібен JDK 17+; SDK качається сам)
pwsh -File mobile/build-apk.ps1  # Windows
# → data/artifacts/jarvis-mvp.apk (+ .meta.json)
```

**Надіслати APK адмінам вручну (хост, поза Docker):**
```bash
python scripts/send_apk_to_admin.py
```

**Запустити стек:**
```bash
docker compose up -d             # повний стек (Ollama — на хості)
docker compose logs -f gateway
```

**Швидкі смоук-чеки (без реального токена/сервісів):**
- `/connect/<token>` → 303 + JWT-cookie → `/platform/api/whoami` `via=cookie`.
- `apk_autodeliver._fetch_remote_version()` → бачить версію з `apk-latest`.

---

## 7. Конвенції (нагадування)

- Розробка по-сервісно; три пакети `app` не збираються в одному процесі (mypy/pytest окремо).
- Mobile — свідомо **без залежностей** (лише `android.*` framework), офлайн-збірка. НЕ
  додавати AndroidX (тому EncryptedSharedPreferences тощо — не варіант без зміни принципу).
- Принципи P3/P4 (композиція замість моноліту), S2/S3 (за прапором; бізнес-логіка не в каналі).
