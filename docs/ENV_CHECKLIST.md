# JARVIS — чеклист змінних середовища (ops)

Після merge residual-фіксів перевір `.env` на хості (не комітити секрети).

> **Дисципліна флагів** ([`AGENTS.md`](../AGENTS.md) §5): нова фіча → новий `ENABLE_*` із безпечним
> дефолтом (`false`) + рядок тут і в `.env.example`. Майбутні змінні стовпів (SaaS `SAAS_MODE`/`JWT_SECRET`,
> API per-org keys) — у [`API_PLATFORM_ROADMAP.md`](API_PLATFORM_ROADMAP.md) і [`SAAS_DEEP_DIVE.md`](SAAS_DEEP_DIVE.md) §13.3.

## Обовʼязково для Computer Use + FS

| Змінна | Приклад | Навіщо |
|--------|---------|--------|
| `ENABLE_COMPUTER_USE` | `true` | Агент + host tools (скріншот, PS, FS) |
| `HOSTAGENT_TOKEN` | *(секрет)* | Звʼязок tools ↔ hostagent |
| `HOSTAGENT_FS_ROOTS` | `C:\Users\you\Documents,O:\JARVIS` | Обмеження шляхів FS (comma-separated). Без цього — доступ до будь-якого абсолютного шляху на хості |

Hostagent читає `HOSTAGENT_FS_ROOTS` як `fs_roots` у `hostagent/.env` або через compose.

## Coding-агент (Стовп B) — repo-інструменти

| Змінна | Приклад | Навіщо |
|--------|---------|--------|
| `ENABLE_CODING_TOOLS` | `true` | read-only `repo_tree`/`repo_grep`/`code_read`/`repo_symbols`, тест/лінт `run_tests`/`run_lint`, мутуючий `code_edit` (computer mode). Owner-gate + `ENABLE_COMPUTER_USE` |
| `CODING_TREE_MAX_ENTRIES` | `300` | Стеля рядків дерева `repo_tree` |
| `CODING_GREP_MAX_RESULTS` | `60` | Стеля результатів `repo_grep` (можна перебити аргументом, до 500) |

Залежність на хості: `ripgrep` (`rg`). `repo_tree`/`repo_grep` за дефолтом пропускають
`.git`/hidden/`.gitignore` (тож `.env` не потрапляє у вивід). `code_edit` — мутуючий (T1):
показує diff → confirm у Telegram (як `fs_write`), перед записом зберігає
`.jarvis_backup/<name>.<ts>.bak`. Деталі: [`CODING_AGENT_ROADMAP.md`](CODING_AGENT_ROADMAP.md) CA-1.x/2.x.

## C3 Browser (Playwright)

| Змінна | Приклад | Навіщо |
|--------|---------|--------|
| `ENABLE_BROWSER` | `true` | `browser_*` у computer mode (потрібен rebuild `tools` з Chromium) |
| `COMPUTER_PROFILE` | `safe` | `safe` (T0/T1) · `standard` (+browser, UIA, see_screen) · `full` (+screen_click) |
| `COMPUTER_SESSION_TRUST_MINUTES` | `10` | Після ✅ — без confirm для T0/T1; `0` = вимк. Кнопка «Full trust» = усі tier |
| `COMPUTER_MAX_ITERS` | `12` | Ітерації тул-лупа в `AGENT_MODE=computer` |

Профіль браузера: [`docs/adr/C3-browser-profile.md`](adr/C3-browser-profile.md).
Повний план Agent Mode: [`AGENT_MODE_ROADMAP.md`](AGENT_MODE_ROADMAP.md).

| `COMPUTER_RATE_LIMIT_PER_HOUR` | `120` | Мутуючі computer-дії на годину; `0` = вимкнено |

## Telegram Mini App / deep link

| Змінна | Приклад | Навіщо |
|--------|---------|--------|
| `PUBLIC_APP_URL` | `https://your-tunnel.example/app` | HTTPS URL для Web App кнопки (`/app`, `/start canvas`). Без HTTPS — текстовий фолбек |

Deep link `/start canvas` додає `?canvas=1` до URL Mini App.

## Нагадування

| Змінна | За замовч. | Навіщо |
|--------|------------|--------|
| `REMINDER_POLL_SECONDS` | `20` | Інтервал полера gateway для due reminders |

## Client-API / JWT (Стовп C, CL-1)

| Змінна | За замовч. | Навіщо |
|--------|------------|--------|
| `JWT_SECRET` | `` (вимкнено) | HS256-секрет для JWT-логіну клієнтів (`/api/v1/auth/login`). Порожньо → JWT off, лишаються initData/Basic. Згенеруй ≥32 байти: `openssl rand -hex 32` |
| `JWT_ACCESS_TTL` | `3600` | Час життя access-токена (сек) |
| `JWT_REFRESH_TTL` | `604800` | Час життя refresh-токена (сек, 7 днів) |
| `SAAS_MODE` | `false` | Мультитенант (cloud). `false` = self-hosted, один synthetic org |
| `DEFAULT_ORG_ID` | `00000000-…-0001` | Synthetic org для self-hosted (рідко змінюють) |

> Self-hosted: `/api/v1/whoami` приймає JWT **або** Telegram initData **або** Basic (один resolver, CL-1.4).
> JWT потрібен клієнтам без initData — mobile APK (CL-3) і майбутній SPA (CL-2).

## Mobile APK (Стовп C, CL-3)

| Змінна | За замовч. | Навіщо |
|--------|------------|--------|
| `APK_ARTIFACT_PATH` | `` → `{DATA_DIR}/artifacts/jarvis-mvp.apk` | Шлях до зібраного APK, який віддає команда `/apk`. Білд кладе файл у `data/artifacts/` (`./data:/data`), gateway бачить його одразу |
| `APK_VERSION` | `0.1.0` | Версія для caption/підпису (синхронізована з `mobile/VERSION`) |

> Збірка: `mobile/build-apk.ps1` (self-contained тулчейн) → `data/artifacts/jarvis-mvp.apk` + `*.meta.json`.
> Доставка адміну: `scripts/send_apk_to_admin.py`; у боті — команда `/apk` (завжди віддає поточний apk).

## Context ingest API (Стовп C, CL-3 — культура P9/P10)

| Змінна | За замовч. | Навіщо |
|--------|------------|--------|
| `ENABLE_CONTEXT_API` | `false` | Вмикає `/api/v1/ingest/events` + `/api/v1/context/{search,recent,purge}` (паспорти контексту → memory). Дефолт off (S2) |
| `CONTEXT_INGEST_MAX_BATCH` | `500` | Стеля подій в одному батчі ingest |
| `ENABLE_CONTEXT_RETRIEVAL` | `false` | (tools) Інжект паспортів контексту в промпт агента (memory `/context/search`). Off = нуль додаткового latency |
| `CONTEXT_RETRIEVAL_TOP_K` | `5` | Скільки паспортів інжектити в контекст агента |
| `CONTEXT_SCHEDULER_ENABLED` | `false` | (gateway) In-app автозапуск context-jobs. Off = нічого; альтернатива — зовн. cron на `/api/v1/context/jobs/*` (ADR-008) |
| `CONTEXT_SCHEDULER_USER_IDS` | `` → `ADMIN_USER_IDS` | Кого обслуговує scheduler (CSV Telegram id) |
| `CONTEXT_DAILY_HOUR` | `6` | Година UTC щоденного `context_daily`+`context_retention` |
| `CONTEXT_SCHEDULER_INTERVAL` | `1800` | Сек між тіками (summarize + перевірка daily) |

> Збір контексту з паспортами (`kind`+`summary`+namespaced `tags`+embedding 768D, AGENTS.md C1).
> Auth — спільний client-API resolver (JWT/initData/Basic). Колектор без залежностей:
> `scripts/jarvis_context.py` (нотатка/pipe/hotkey/cron). Дані лише в memory користувача (S1).

## Безпека (рекомендовано)

| Змінна | Навіщо |
|--------|--------|
| `TELEGRAM_WEBHOOK_SECRET` | Перевірка `X-Telegram-Bot-Api-Secret-Token` у webhook-режимі |
| `COMPUTER_MODE_ADMINS_ONLY` | Обмежити `/mode computer` |
| `WEBAPP_DEV_OPEN` | `false` у проді — `/app` лише з Telegram initData |
| **M4** | Ротація `TELEGRAM_BOT_TOKEN` у @BotFather після витоку в логах/чаті |

## Autostart і моніторинг

| Змінна / скрипт | Навіщо |
|-----------------|--------|
| `HEALTH_WATCH_INTERVAL` | Секунди між перевірками стеку; `0` = вимкнено; дефолт `300` |
| `HOSTAGENT_DROP_DIR` | Куди класти файли з caption «на диск» без явного шляху |
| `scripts/install_autostart.ps1` | Один раз: logon + watchdog кожні 5 хв |
| `scripts/autostart.ps1` | Ollama → Docker → compose → SD Forge → host-agent |
| `scripts/verify_stack.ps1` | Після autostart або вручну — exit 1 при fail |
| `scripts/verify_stack.ps1 -StrictProd` | Прод: `WEBAPP_DEV_OPEN=true` → fail |
| `FirstSetup-Auto.bat` + `setup.local.env` | Повністю автономний setup (winget, compose, autostart) |
| `scripts/FirstSetup.ps1` / `FirstSetup.bat` | Інтерактивний setup |
| `scripts/Install-JARVIS.ps1` | Alias → `FirstSetup.ps1` |

## Бекапи

Див. [`docs/BACKUP.md`](BACKUP.md).

## Після змін

```powershell
cd O:\JARVIS\hostagent; .\run.bat
cd O:\JARVIS
docker compose up -d --build gateway tools
```

Тести: `pytest gateway/tests tools/tests hostagent/tests`
