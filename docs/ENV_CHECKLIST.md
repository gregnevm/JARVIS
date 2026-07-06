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
| `ENABLE_MCP_HUB` | `false` | (gateway, AP-7.4) Вмикає `/api/v1/mcp/{servers,call}` — ре-експонує агрегатор MCP-серверів (tools `/mcp/*`) під client-API auth для конектора `/jarvis`. Дефолт off (S2); вимкнено → 404 |
| `ENABLE_CONTEXT_RETRIEVAL` | `false` | (tools) Інжект паспортів контексту в промпт агента (memory `/context/search`). Off = нуль додаткового latency |
| `CONTEXT_RETRIEVAL_TOP_K` | `5` | Скільки паспортів інжектити в контекст агента |
| `CONTEXT_SCHEDULER_ENABLED` | `false` | (gateway) In-app автозапуск context-jobs. Off = нічого; альтернатива — зовн. cron на `/api/v1/context/jobs/*` (ADR-008) |
| `CONTEXT_SCHEDULER_USER_IDS` | `` → `ADMIN_USER_IDS` | Кого обслуговує scheduler (CSV Telegram id) |
| `CONTEXT_DAILY_HOUR` | `6` | Година UTC щоденного `context_daily`+`context_retention` |
| `CONTEXT_SCHEDULER_INTERVAL` | `1800` | Сек між тіками (summarize + перевірка daily) |

> Збір контексту з паспортами (`kind`+`summary`+namespaced `tags`+embedding 768D, AGENTS.md C1).
> Auth — спільний client-API resolver (JWT/initData/Basic). Колектор без залежностей:
> `scripts/jarvis_context.py` (нотатка/pipe/hotkey/cron). Дані лише в memory користувача (S1).

## Паспортна шина (SY-B, docs/SYNERGY_ROADMAP.md)

| Змінна | За замовч. | Навіщо |
|--------|------------|--------|
| `ENABLE_PASSPORT_BUS` | `false` | (gateway) In-proc Observer: ingest emit ПІСЛЯ store → підписники (перший — push ntfy на `priority:high`). Off = нуль змін поведінки (ADR-008) |
| `PUSH_ENABLED` + `NTFY_URL`/`NTFY_TOPIC` | `false` | Спільний блок `PushCfg` (gateway шина + tools джоби): ntfy UnifiedPush, S1-суверенно |
| `ENABLE_FRICTION_TELEMETRY` | `false` | (tools) SY-1: агент-луп емітить `kind:friction` (tool-fail/unknown-tool/loop-exhausted) → kaizen-backlog з реального болю. Без сирих аргументів (анти-leak) |
| `ENABLE_USAGE_METERING` | `false` | (tools→gateway) SY-6: kind:usage агрегат-паспорти LLM-викликів — один SSOT для `/v1/usage` (tokens-блок), `/platform/api/usage` і kaizen O3 ECO |
| `USAGE_METER_USER_ID` | `-770002` | Синтетичний UID-власник usage-паспортів (партиція стору, прецедент kaizen `-770001`) |
| `ENABLE_CONFIRM_PUSH` | `false` | (tools) SY-5 MVP: confirm-запит → ntfy-push із deep-link + паспорти `kind:confirm_request\|confirm_decision` (аудит S4 ретривом) |
| `CONFIRM_PUSH_CLICK_URL` | `` | Deep-link тапу по confirm-нотифікації (канал апруву, напр. Mini App `https://<tunnel>/app`) |
| `ENABLE_ROUTINES` | `false` | (tools) SY-9: пропозиція → рядок Task Scheduler (`schtasks` через host-agent; task б'є `jarvis_context.py --job`). Потребує `ENABLE_COMPUTER_USE`+`HOSTAGENT_TOKEN` |
| `ROUTINES_HOST_REPO` | `O:\JARVIS` | Шлях до репо НА ХОСТІ (де `scripts/jarvis_context.py`) — обов'язковий для рутин |
| `ROUTINES_PYTHON_EXE` / `ROUTINES_GATEWAY_URL` | `python` / `http://127.0.0.1:8000` | Чим і куди б'є scheduled task (auth — env хоста `JARVIS_PASSWORD`/`JARVIS_TOKEN`) |

## Gateway: старт і локальні тести (R1 «Тонкий шлюз»)

| Змінна | Приклад | Навіщо |
|--------|---------|--------|
| `GATEWAY_STARTUP_NET` | `true` | Стартова мережа gateway: webhook/BotFather-UI (best-effort фонова таска) і фонові поллери. `false` — старт без зовнішнього I/O (локальний `pytest gateway/tests`, offline-dev). Статус реєстрації UI видно у `/health` → `bot_ui_registered` |

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

<!-- GEN:ENV-INVENTORY:BEGIN (scripts/gen_env_docs.py — не редагуй руками) -->

## Повний інвентар env-змінних (216 змінних, code-first)

Згенеровано з Settings-класів сервісів. Оновити: `python scripts/gen_env_docs.py`.
CI (`arch-gates`) падає, якщо таблиця/снапшоти розійшлися з кодом (drift-гейт D1).

| ENV | Сервіси | Дефолт |
|-----|---------|--------|
| `ACCESS_STORE_PATH` | gateway | `"/data/access/users.json"` |
| `ADMIN_PANEL_PASSWORD` | gateway | `""` |
| `ADMIN_PANEL_USER` | gateway | `"admin"` |
| `ADMIN_USER_IDS` | gateway, tools | `""` |
| `AGENT_MODE` | tools | `"hybrid"` |
| `AGENT_TIMEOUT` | gateway | `300.0` |
| `ALBUM_COLLECT_SECONDS` | gateway | `2.0` |
| `ALLOWED_USER_IDS` | gateway, tools | `""` |
| `APK_ARTIFACT_PATH` | gateway | `""` |
| `APK_AUTO_DELIVER` | gateway | `false` |
| `APK_AUTO_DELIVER_INTERVAL` | gateway | `3600` |
| `APK_RELEASE_APK_URL` | gateway | `"https://github.com/gregnevm/JARVIS/releases/download/apk…` |
| `APK_RELEASE_META_URL` | gateway | `"https://github.com/gregnevm/JARVIS/releases/download/apk…` |
| `APK_VERSION` | gateway | `"0.1.0"` |
| `AUTO_COROUTINE_BYPASS_PERMISSIONS` | gateway | `false` |
| `AUTO_COROUTINE_ENABLED` | gateway | `false` |
| `AUTO_COROUTINE_INTERVAL` | gateway | `3600.0` |
| `AUTO_COROUTINE_REPO_PATH` | gateway | `""` |
| `AUTO_COROUTINE_ULTRACODE` | gateway | `false` |
| `AUTO_COROUTINE_USER_ID` | gateway | `0` |
| `BOT_USERNAME` | gateway | `""` |
| `BYPASS_CONFIRMATIONS` | tools | `false` |
| `CALENDAR_ICS_URL` | tools | `""` |
| `CLI_WHITELIST` | tools | `""` |
| `CODE_EXEC_DENY_PATTERNS` | tools | `""` |
| `CODE_EXEC_MEMORY_MB` | tools | `512` |
| `CODE_EXEC_REQUIRE_SANDBOX` | tools | `true` |
| `CODE_EXEC_TIMEOUT` | tools | `8.0` |
| `CODING_FIX_MAX_ROUNDS` | tools | `4` |
| `CODING_GREP_MAX_RESULTS` | tools | `60` |
| `CODING_HEADLESS_APPLY` | tools | `false` |
| `CODING_HEADLESS_TRUST_TTL` | tools | `600` |
| `CODING_PRECOMMIT_GATE` | tools | `false` |
| `CODING_PRECOMMIT_LINT_ARGS` | tools | `"check"` |
| `CODING_PRECOMMIT_LINT_EXE` | tools | `"ruff"` |
| `CODING_PRECOMMIT_PATH` | tools | `""` |
| `CODING_REVIEW_AFTER_FIX` | tools | `false` |
| `CODING_TREE_MAX_ENTRIES` | tools | `300` |
| `COMPUTER_ALLOW_ADMIN` | tools | `false` |
| `COMPUTER_ALLOW_POWER` | tools | `false` |
| `COMPUTER_APPROVAL_POLICY` | tools | `""` |
| `COMPUTER_AUTO_LEARN_WHITELIST` | tools | `true` |
| `COMPUTER_AUTO_TRUST_LEARNED` | tools | `true` |
| `COMPUTER_AUTO_VISION` | tools | `true` |
| `COMPUTER_MAX_ITERS` | tools | `12` |
| `COMPUTER_MODE_ADMINS_ONLY` | gateway, tools | `false` |
| `COMPUTER_OWNER_USER_IDS` | gateway, tools | `""` |
| `COMPUTER_PROFILE` | tools | `"safe"` |
| `COMPUTER_RATE_LIMIT_PER_HOUR` | tools | `120` |
| `COMPUTER_REQUIRE_CONFIRM` | tools | `true` |
| `COMPUTER_SESSION_TRUST_MINUTES` | gateway, tools | `10` |
| `COMPUTER_TIMEOUT` | tools | `30.0` |
| `CONFIRM_PUSH_CLICK_URL` | tools | `""` |
| `CONTEXT_DAILY_HOUR` | gateway | `6` |
| `CONTEXT_INGEST_MAX_BATCH` | gateway | `500` |
| `CONTEXT_RETRIEVAL_TOP_K` | tools | `5` |
| `CONTEXT_SCHEDULER_ENABLED` | gateway | `false` |
| `CONTEXT_SCHEDULER_INTERVAL` | gateway | `1800.0` |
| `CONTEXT_SCHEDULER_USER_IDS` | gateway | `""` |
| `CONTINUE_DEV_TIMEOUT` | tools | `300.0` |
| `CONTINUE_DEV_URL` | tools | `"http://host.docker.internal:65432"` |
| `CONTINUE_VSCODE_CLI` | tools | `"code"` |
| `CURSOR_API_BASE` | tools | `"https://api.cursor.com"` |
| `CURSOR_API_KEY` | tools | `""` |
| `CURSOR_AUTO_CREATE_PR` | tools | `false` |
| `CURSOR_FALLBACK_INBOX` | tools | `true` |
| `CURSOR_HOST_SCRIPT` | tools | `""` |
| `CURSOR_HOST_WORKSPACE` | tools | `""` |
| `CURSOR_MODEL` | tools | `"composer-2.5"` |
| `CURSOR_PYTHON_EXE` | tools | `"python"` |
| `CURSOR_REPO_REF` | tools | `"main"` |
| `CURSOR_REPO_URL` | tools | `""` |
| `CURSOR_RUNTIME` | tools | `"local"` |
| `CURSOR_TASKS_ENABLED` | tools | `true` |
| `CURSOR_TIMEOUT` | tools | `900.0` |
| `DATA_DIR` | gateway, tools | `"/data"` |
| `DEFAULT_ORG_ID` | gateway | `"00000000-0000-0000-0000-000000000001"` |
| `EMBED_CACHE_TTL` | memory | `86400` |
| `EMBED_DIM` | memory | `768` |
| `EMBED_MODEL` | memory | `"nomic-embed-text"` |
| `ENABLE_BROWSER` | tools | `false` |
| `ENABLE_CLAUDE_CODE_BRIDGE` | gateway | `false` |
| `ENABLE_CODE_EXEC` | tools | `false` |
| `ENABLE_CODING_TOOLS` | tools | `false` |
| `ENABLE_COMPUTER_USE` | tools | `false` |
| `ENABLE_CONFIRM_PUSH` | tools | `false` |
| `ENABLE_CONTEXT_API` | gateway | `false` |
| `ENABLE_CONTEXT_RETRIEVAL` | tools | `false` |
| `ENABLE_CONTINUE_DEV` | tools | `false` |
| `ENABLE_FRICTION_TELEMETRY` | tools | `false` |
| `ENABLE_MCP_HUB` | gateway | `false` |
| `ENABLE_OPENAI_API` | gateway | `false` |
| `ENABLE_PASSPORT_BUS` | gateway | `false` |
| `ENABLE_REACTION_REPLIES` | gateway | `true` |
| `ENABLE_ROUTINES` | tools | `false` |
| `ENABLE_STREAMING` | gateway | `true` |
| `ENABLE_USAGE_METERING` | gateway, tools | `false` |
| `ENABLE_VOICE_REPLY` | gateway | `false` |
| `FETCH_MAX_CHARS` | tools | `6000` |
| `GATEWAY_BROWSER_URL` | gateway | `"http://127.0.0.1:8000"` |
| `GATEWAY_STARTUP_NET` | gateway | `true` |
| `GUEST_RATE_LIMIT_PER_MIN` | gateway | `12` |
| `HEALTH_ALERT_USER_IDS` | gateway | `""` |
| `HEALTH_WATCH_INTERVAL` | gateway | `300.0` |
| `HOOKS_ENABLED` | tools | `true` |
| `HORDE_API_KEY` | tools | `"0000000000"` |
| `HOSTAGENT_ALLOW_ADMIN` | hostagent | `false` |
| `HOSTAGENT_ALLOW_POWER` | hostagent | `false` |
| `HOSTAGENT_BIND_HOST` | hostagent | `"127.0.0.1"` |
| `HOSTAGENT_DROP_DIR` | gateway, hostagent, tools | `""` |
| `HOSTAGENT_EDIT_BATCH_MAX` | hostagent | `20` |
| `HOSTAGENT_EDIT_MAX_BYTES` | hostagent | `2097152` |
| `HOSTAGENT_EXEC_TIMEOUT` | hostagent | `30.0` |
| `HOSTAGENT_FS_ROOTS` | hostagent | `""` |
| `HOSTAGENT_MAX_BYTES` | hostagent | `6000` |
| `HOSTAGENT_MAX_DOWNLOAD_BYTES` | hostagent | `50331648` |
| `HOSTAGENT_PORT` | hostagent | `8400` |
| `HOSTAGENT_TOKEN` | hostagent, tools | `""` |
| `HOSTAGENT_URL` | tools | `"http://host.docker.internal:8400"` |
| `HTTP_TIMEOUT` | tools | `20.0` |
| `IGNORE_EDITED_MESSAGES` | gateway | `true` |
| `IMAGE_GEN_MODEL` | tools | `""` |
| `IMAGE_GEN_TIMEOUT` | tools | `180.0` |
| `IMAGE_GEN_URL` | tools | `""` |
| `INDEX_PROJECT_FILES` | memory | `true` |
| `JWT_ACCESS_TTL` | gateway | `3600` |
| `JWT_REFRESH_TTL` | gateway | `604800` |
| `JWT_SECRET` | gateway | `""` |
| `KOBOLD_HOST` | tools, twin | `tools: "http://host.docker.internal:5001" / twin: "http:/…` |
| `LLM_BACKEND` | tools, twin | `"ollama"` |
| `LLM_LOG_PATH` | twin | `null` |
| `LLM_TIMEOUT` | twin | `180.0` |
| `LORA_ACTIVE_DIR` | tools | `""` |
| `LORA_BASE_MODEL` | tools | `""` |
| `LORA_DEPLOY_ENABLED` | tools | `true` |
| `LORA_OLLAMA_MODEL` | tools | `"jarvis-lora"` |
| `MAX_AGENT_ITERS` | tools | `5` |
| `MCP_SERVERS_JSON` | tools | `""` |
| `MEMORY_URL` | gateway, tools | `"http://memory:8100"` |
| `NOTION_DATABASE_ID` | tools | `""` |
| `NOTION_TOKEN` | tools | `""` |
| `NTFY_TOPIC` | gateway, tools | `""` |
| `NTFY_URL` | gateway, tools | `"https://ntfy.sh"` |
| `OLLAMA_COOLDOWN` | tools | `60.0` |
| `OLLAMA_FAIL_THRESHOLD` | tools | `3` |
| `OLLAMA_HOST` | memory, tools, twin | `"http://host.docker.internal:11434"` |
| `OLLAMA_MODEL` | twin | `"qwen2.5:7b-instruct"` |
| `OLLAMA_MODEL_AGENT` | tools | `"qwen2.5:7b-instruct"` |
| `OLLAMA_MODEL_CHAT` | tools | `"gemma3:4b"` |
| `OLLAMA_MODEL_VISION` | tools | `""` |
| `OLLAMA_TIMEOUT` | tools | `180.0` |
| `OLLAMA_VISION_ON_DEMAND` | tools | `false` |
| `OPENAI_API_KEY` | gateway | `""` |
| `OPENAI_DEFAULT_USER_ID` | gateway | `0` |
| `OPENAI_KEY_RATE_LIMIT_PER_MIN` | gateway | `0` |
| `ORCHESTRATOR_ENABLED` | tools | `true` |
| `ORCHESTRATOR_MAX_REVISIONS` | tools | `1` |
| `ORCHESTRATOR_WORKER_BUDGET` | tools | `5` |
| `PLATFORM_PASSWORD` | gateway | `""` |
| `POSTGRES_DB` | memory | `"jarvis"` |
| `POSTGRES_HOST` | memory | `"postgres"` |
| `POSTGRES_PASSWORD` | memory | `"changeme"` |
| `POSTGRES_PORT` | memory | `5432` |
| `POSTGRES_USER` | memory | `"jarvis"` |
| `PROJECT_FILES_MAX_PER_FILE_TOKENS` | memory | `1200` |
| `PROJECT_FILES_MAX_TOTAL_TOKENS` | memory | `3000` |
| `PS_WHITELIST` | tools | `""` |
| `PUBLIC_ADMIN_APP_URL` | gateway | `""` |
| `PUBLIC_APP_URL` | gateway | `""` |
| `PUSH_ENABLED` | gateway, tools | `false` |
| `RATE_LIMIT_PER_MIN` | gateway | `20` |
| `REDIS_URL` | gateway, memory, tools | `"redis://redis:6379/0"` |
| `REMINDER_POLL_SECONDS` | gateway | `20.0` |
| `REMOTE_FILE_MAX_BYTES` | gateway, tools | `50331648` |
| `RESEARCH_MAX_CHARS` | tools | `40000` |
| `RESEARCH_MAX_HOPS` | tools | `3` |
| `RESEARCH_MAX_URLS` | tools | `5` |
| `ROUTINES_GATEWAY_URL` | tools | `"http://127.0.0.1:8000"` |
| `ROUTINES_HOST_REPO` | tools | `""` |
| `ROUTINES_PYTHON_EXE` | tools | `"python"` |
| `SAAS_MODE` | gateway | `false` |
| `SELF_IMPROVE_ENABLED` | tools | `true` |
| `SELF_IMPROVE_JUDGE_MODEL` | tools | `""` |
| `SELF_IMPROVE_SCAN_LIMIT` | tools | `50` |
| `SHORT_TERM_LIMIT` | memory | `10` |
| `SKILLS_MAX_CHARS` | tools | `4000` |
| `SKILLS_SCAN_MODE` | tools | `"block"` |
| `SLACK_BOT_TOKEN` | tools | `""` |
| `SLACK_DEFAULT_CHANNEL` | tools | `""` |
| `SUBAGENT_DEFAULT_BUDGET` | tools | `3` |
| `SUBAGENT_MAX_BUDGET` | tools | `8` |
| `TEAM_MODE` | gateway | `false` |
| `TELEGRAM_API_BASE` | gateway | `"https://api.telegram.org"` |
| `TELEGRAM_BOT_TOKEN` | gateway | `""` |
| `TELEGRAM_INGEST_MODE` | gateway | `"polling"` |
| `TELEGRAM_REPLY_KEYBOARD` | gateway | `true` |
| `TELEGRAM_WEBHOOK_SECRET` | gateway | `""` |
| `TELEGRAM_WEBHOOK_URL` | gateway | `""` |
| `TOOLS_URL` | gateway | `"http://tools:8200"` |
| `TRAIN_RETRAIN_MIN_CURATED` | tools | `200` |
| `TTS_DEVICE` | tts | `"cuda"` |
| `TTS_LANGUAGE` | tts | `"ru"` |
| `TTS_MAX_CHARS` | tts | `800` |
| `TTS_MODEL` | tts | `"tts_models/multilingual/multi-dataset/xtts_v2"` |
| `TTS_SPEAKER_WAV` | tts | `"/app/voices/reference.wav"` |
| `TTS_SYNTH_TIMEOUT` | tts | `120.0` |
| `TTS_URL` | gateway | `"http://tts:8300"` |
| `TWIN_DATA_DIR` | twin | `"/data/twin"` |
| `TWIN_MIN_EVAL_PROMOTE` | twin | `0.0` |
| `TWIN_REGISTRY_DB` | twin | `"/data/twin/registry.db"` |
| `TWIN_URL` | gateway, tools | `"http://twin:8765"` |
| `UPLOAD_DIR` | gateway | `"/data/uploads"` |
| `USAGE_METER_USER_ID` | gateway, tools | `-770002` |
| `WEBAPP_DEV_OPEN` | gateway | `false` |
| `WHISPER_LANGUAGE` | gateway | `""` |
| `WHISPER_URL` | gateway | `"http://whisper:9000"` |

<!-- GEN:ENV-INVENTORY:END -->
