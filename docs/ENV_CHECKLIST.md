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
| `CODING_NO_PROGRESS_REPEATS` | `2` | CA-3.4 stop-condition: N однакових поспіль fail від `run_tests`/`run_lint` → агент зупиняє fix-цикл і чесно звітує. `0` = вимкнено |

Залежність на хості: `ripgrep` (`rg`). `repo_tree`/`repo_grep` за дефолтом пропускають
`.git`/hidden/`.gitignore` (тож `.env` не потрапляє у вивід). `code_edit` — мутуючий (T1):
показує diff → confirm у Telegram (як `fs_write`), перед записом зберігає
`.jarvis_backup/<name>.<ts>.bak`. Деталі: [`CODING_AGENT_ROADMAP.md`](CODING_AGENT_ROADMAP.md) CA-1.x/2.x.

## C3 Browser (Playwright)

| Змінна | Приклад | Навіщо |
|--------|---------|--------|
| `ENABLE_BROWSER` | `true` | `browser_*` у computer mode (потрібен rebuild `tools` з Chromium) |
| `COMPUTER_PROFILE` | `standard` | `safe` (T0/T1) · `standard` (+browser, UIA, see_screen) · `full` (+screen_click) |
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
| `REMINDER_POLL_SECONDS` | `5` | Інтервал полера gateway для due reminders |

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
