# JARVIS — повністю локальний AI-асистент у Telegram

Self-hosted Telegram-бот на мікросервісах. Усе працює локально: LLM через **Ollama**,
агент-луп у **Tools** (Python), пам'ять через **PostgreSQL + pgvector**, голос через **Whisper**,
синхронізація Edge↔Twin через **twin** (SyncServer + ModelRegistry). Жодних зовнішніх AI API.
Запуск — один `docker compose up`. Цільова архітектура PortableAI — `docs/DESIGN.md`.

**Бачення продукту:** JARVIS росте у повноцінну суверенну платформу — **API-платформу розробника**
(як OpenAI/Anthropic), **агента кодування рівня Claude Code**, і **мультиплатформу** (web · Telegram ·
mobile APK). Статут і принципи — [`AGENTS.md`](AGENTS.md); парасолька-roadmap — [`docs/PRODUCT_ROADMAP.md`](docs/PRODUCT_ROADMAP.md).

**Roadmap-и:** статут [`AGENTS.md`](AGENTS.md) → парасолька [`docs/PRODUCT_ROADMAP.md`](docs/PRODUCT_ROADMAP.md);
треки: API [`docs/API_PLATFORM_ROADMAP.md`](docs/API_PLATFORM_ROADMAP.md) · Coding [`docs/CODING_AGENT_ROADMAP.md`](docs/CODING_AGENT_ROADMAP.md) ·
Clients [`docs/CLIENTS_ROADMAP.md`](docs/CLIENTS_ROADMAP.md) · Platform-консоль [`docs/PLATFORM_ROADMAP.md`](docs/PLATFORM_ROADMAP.md) ·
Computer Use [`docs/AGENT_MODE_ROADMAP.md`](docs/AGENT_MODE_ROADMAP.md) · SaaS [`docs/SAAS_DEEP_DIVE.md`](docs/SAAS_DEEP_DIVE.md) · ops-backlog [`ROADMAP.md`](ROADMAP.md).
Бекапи — `docs/BACKUP.md`; перевірка стеку — `scripts/verify_stack.ps1`.

> Статус фундаменту: **усі 7 фаз готові** — скелет, gateway, Ollama-bridge, памʼять/RAG, голос,
> Tools + агент-луп на двох моделях, polish (rate limit, circuit breaker, healthchecks),
> Platform-консоль P0–P12, Computer Use C0–C6. Чеклист — у кінці README.
> **Далі:** 3 продуктові стовпи (API-платформа · coding-агент · мультиплатформа) над цим фундаментом —
> див. [`docs/PRODUCT_ROADMAP.md`](docs/PRODUCT_ROADMAP.md).

---

## Архітектура

```
text ─► Gateway ──► Tools /agent ──┬─► Ollama (ХОСТ)  CHAT | AGENT
       (auth,       route + loop   ├─► Memory  (pgvector RAG)
        rate-limit)                 └─► calc · web_fetch · search · code_exec
voice ─► Whisper (STT) ─┘
Edge ──► Twin SyncServer (ingest JSONL, /latest/lora, ModelRegistry)
        дані: PostgreSQL · Redis · ./data/twin
```

Gateway робить лише I/O (Telegram, auth, rate-limit, STT) і кличе **Tools `/agent`**
напряму (DESIGN: без n8n-проксі). Там живе вся «мозкова» логіка — `AGENT_MODE`,
RAG-контекст із Memory і тул-луп на AGENT-моделі.

| Сервіс     | Порт  | Образ / стек                                   | Роль                                  |
|------------|-------|------------------------------------------------|---------------------------------------|
| gateway    | 8000  | FastAPI (build)                                | Вебхук, auth, роутинг text/voice/file |
| whisper    | 9000  | `onerahmet/openai-whisper-asr-webservice`      | Розпізнавання голосу (STT)            |
| memory     | 8100  | FastAPI (build)                                | RAG: embeddings + retrieval           |
| tools      | 8200  | FastAPI (build)                                | Інструменти + агент-луп (дві моделі)  |
| twin       | 8765  | FastAPI (build)                                | SyncServer, ModelRegistry, Edge ingest |
| n8n        | 5678  | `n8nio/n8n` (profile `legacy`, опційно)        | Застарілий проксі; не потрібен за замовч. |
| postgres   | 5432  | `pgvector/pgvector:pg16`                        | Історія + векторна пам'ять            |
| redis      | 6379  | `redis:7-alpine`                               | Rate limit, short-term, черга         |
| ollama     | 11434 | **на хості** (не в Compose)                    | LLM + embeddings                      |

---

## Передумови

1. **Docker Desktop** (Windows/Mac) або Docker Engine + Compose v2 (Linux).
   Перевірка: `docker --version` та `docker compose version`.
2. **Ollama на хості** — https://ollama.com. Перевірка: `ollama --version`,
   а API має відповідати на `http://localhost:11434/api/tags`.
   - GPU обслуговує хостовий драйвер напряму — **NVIDIA Container Toolkit не потрібен**.
   - Хочеш Ollama всередині Compose з GPU — розкоментуй блок `ollama` у `docker-compose.yml`
     і постав `OLLAMA_HOST=http://ollama:11434` (тоді Toolkit таки потрібен).

### Які моделі завантажити

```bash
ollama pull gemma3:4b                # OLLAMA_MODEL_CHAT — швидкий non-thinking чат
ollama pull qwen2.5:7b-instruct      # OLLAMA_MODEL_AGENT — надійний tool calling
ollama pull nomic-embed-text         # EMBED_MODEL — ембединги (768 вимірів)
```

> **CPU-only (без NVIDIA GPU):** інференс ~7–8 tok/s. Уникай thinking-моделей
> (`qwen3`, деякі `gemma`) — вони генерують сотні токенів міркувань, тож відповідь
> триває хвилини. Для CPU став non-thinking instruct, напр.:
> `ollama pull qwen2.5:3b-instruct` і `OLLAMA_MODEL_CHAT=qwen2.5:3b-instruct`.

### AMD GPU без ROCm — через Vulkan (експериментально, але працює)

ROCm на Windows для Ollama підтримує тільки **RDNA2/RDNA3** (RX 6000/7000). Старіші
карти (RDNA1 — RX 5700 XT тощо) офіційно «не підтримуються». **Обхід — `OLLAMA_VULKAN=1`**:

```powershell
# зупинити поточну Ollama (якщо крутиться):
Get-Process ollama -EA SilentlyContinue | Stop-Process -Force
# стартувати з Vulkan-бекендом:
$env:OLLAMA_VULKAN=1; $env:OLLAMA_HOST="0.0.0.0:11434"; ollama serve
```

Перевірено наживо на **AMD Radeon RX 5700 XT (8 ГБ VRAM)**: qwen2.5:7b-instruct
дає ~50-60 tok/s — **~8× швидше за CPU** на тій самій машині. Vulkan працює на
будь-якому сучасному GPU включно з RDNA1, тож це найпростіший шлях оживити
не-NVIDIA залізо. На NVIDIA Ollama використовує CUDA автоматично — Vulkan не потрібен.

Моделі можна змінити у `.env`. Але якщо міняєш `EMBED_MODEL` на модель з **іншою
розмірністю** вектора — треба синхронізувати `vector(768)` у `db/init.sql` (це міграція).

> **Зміна `.env` уже після старту:** `docker compose restart <svc>` **НЕ** перечитує
> `env_file`. Щоб новий env підхопився — `docker compose up -d <svc>` (recreate).

---

## Швидкий старт

### FirstSetup (рекомендовано, Windows)

#### Повністю автономно (один клік, без питань)

```powershell
# 1) Секрети (один раз):
copy setup.local.env.example setup.local.env
#    → TELEGRAM_BOT_TOKEN, ALLOWED_USER_IDS

# 2) Запуск:
.\FirstSetup-Auto.bat
```

`-Auto` робить усе сам: **winget** (Docker, Ollama, Python) → GPU-профіль → `.env` →
`ollama pull` → host-agent → **SD Forge** (`setup` + `start`) → `docker compose up -d --build` →
`verify_stack` → `install_autostart.ps1`. Якщо Docker щойно встановився — реєструє resume-задачу на логін.

Альтернатива секретам: змінні `JARVIS_TELEGRAM_BOT_TOKEN`, `JARVIS_ALLOWED_USER_IDS`.

#### Інтерактивно (з питаннями)

```powershell
.\FirstSetup.bat
# або:
powershell -ExecutionPolicy Bypass -File scripts\FirstSetup.ps1
```

Профіль заліза: `data/hardware_profile.json`. Лог: `data/firstsetup.log`, статус: `data/firstsetup.status.json`.

Параметри: `-Auto`, `-InstallMissing`, `-NonInteractive`, `-TelegramToken`, `-AllowedUserIds`, `-SkipCompose`, `-SkipModels`.

### Вручну

```bash
# 1. Конфіг
cp .env.example .env          # Windows: copy .env.example .env
#   → впиши TELEGRAM_BOT_TOKEN та свій ALLOWED_USER_IDS

# 2. Переконайся, що Ollama на хості піднята і моделі pull-нуті (див. вище)

# 3. Підняти стек
docker compose up -d --build

# 4. Логи
docker compose logs -f gateway
```

Перевірка здоров'я:

```bash
curl http://localhost:8000/health     # gateway
curl http://localhost:8200/health     # tools
curl http://localhost:8100/health     # memory
curl http://localhost:8300/health     # tts (якщо ENABLE_VOICE_REPLY=true)
curl http://127.0.0.1:8400/health     # host-agent (процес на Windows, не в Compose)
curl http://localhost:11434/api/tags  # Ollama на хості
docker compose ps                     # статуси + healthcheck
docker compose logs gateway --tail 5  # ingest=polling, whitelist, "Long polling started"
```

### Перевірка після змін `.env`

1. **Не використовуй** `docker compose restart` для підхоплення env — лише recreate:
   `docker compose up -d gateway tools` (або `--build` після змін коду).
2. Після змін computer-use / токена host-agent — перезапусти процес на хості
   (`hostagent/run.bat` або scheduled task з `scripts/install_autostart.ps1`).
3. Прогони health-перевірки з блоку вище; gateway-лог має містити `ingest=polling`
   і непорожній whitelist.
4. Юніт-тести (по одному сервісу, інакше колізія пакета `app`):
   `pytest gateway/tests`, `pytest tools/tests`, `pytest hostagent/tests`, …

### Computer Use (швидкий старт)

Керування Windows-хостом з Telegram (PowerShell/CLI/FS). Повний план: `docs/COMPUTER_USE.md`.

1. У `.env`: `ENABLE_COMPUTER_USE=true`, `HOSTAGENT_TOKEN=<secrets.token_hex(24)>`
   (той самий рядок — tools і host-agent читають `HOSTAGENT_TOKEN`).
2. Whitelist: `PS_WHITELIST`, `CLI_WHITELIST`. Admin вимкнено за замовч. (`COMPUTER_ALLOW_ADMIN=false`).
3. На хості (поза Docker):

```powershell
cd O:\JARVIS\hostagent
.\run.bat
# або: pip install -r requirements.txt
#      $env:HOSTAGENT_TOKEN = "..." ; python -m uvicorn app.main:app --host 127.0.0.1 --port 8400
```

4. Перевірка: `curl http://127.0.0.1:8400/health` → `{"status":"ok"}`.
5. `docker compose up -d gateway tools` — tools ходить на `http://host.docker.internal:8400`.
6. У чаті: `/mode computer` або `AGENT_MODE=computer`; мутуючі дії — підтвердження ✅/❌ у Telegram.

#### Standard Agent Mode (рекомендований пресет)

Для повноцінного desktop-агента на одному trusted ПК:

```env
AGENT_MODE=hybrid
ENABLE_COMPUTER_USE=true
COMPUTER_PROFILE=standard
COMPUTER_SESSION_TRUST_MINUTES=10
COMPUTER_MAX_ITERS=12
ENABLE_BROWSER=true
OLLAMA_MODEL_VISION=llava:7b
COMPUTER_AUTO_VISION=true
HOSTAGENT_TOKEN=<той самий на хості>
COMPUTER_OWNER_USER_IDS=<твій Telegram ID>
```

`standard` дає browser (T2), UIA (T3) і `see_screen` (vision). Для піксельного кліку (T4):
`COMPUTER_PROFILE=full`. Детальний план: `docs/AGENT_MODE_ROADMAP.md`.

#### Програмування з Telegram (Cursor + Continue)

| Шлях | Команда в Telegram | Що потрібно |
|------|-------------------|-------------|
| **Cursor** | `/cursor …` або `cursor: …` | `CURSOR_TASKS_ENABLED=true` (дефолт) |
| **Continue.dev** | звичайний текст у `/mode computer` | `ENABLE_CONTINUE_DEV=true` + `cn serve` |

**Continue — один раз:**

```powershell
# Локальна Ollama (OLLAMA_MODEL_AGENT) — без API ключів:
powershell -File scripts/setup_continue.ps1
# Опційно: Continue Hub акаунт (-Login) або CONTINUE_API_KEY у .env
```

Після логону `scripts/autostart.ps1` / watchdog піднімають `cn serve` на порту з
`CONTINUE_DEV_URL` (дефолт `:65432`). Перевірка: `.\scripts\verify_stack.ps1`.

Приклади в чаті (computer mode): `cursor: додай тести до agent.py` ·
`Відкрий O:\JARVIS\tools\app\agent.py і через Continue додай docstring`.

> **Безпека:** ротуй `TELEGRAM_BOT_TOKEN` у @BotFather, якщо токен світився в логах/чаті
> (див. `ROADMAP.md` M4). Після revoke — онови `.env` і `docker compose up -d gateway`.

### Windows: автозапуск усього стеку (завжди)

Щоб **Ollama, Docker Compose, host-agent, SD Forge** (і Continue, якщо увімкнено)
піднімались після логону і відновлювались кожні 5 хв (watchdog), один раз:

```powershell
powershell -File scripts/install_autostart.ps1
```

У `.env` для локальних картинок:

```
IMAGE_GEN_URL=http://host.docker.internal:7860
```

Перший раз: `scripts/setup_sd_forge.ps1` (або `FirstSetup -Auto` зробить сам).
Autostart підніме Forge на `:7860` і дочекається API перед `verify_stack`.

У кореневому `.env` має бути `HOSTAGENT_TOKEN` (той самий, що для `ENABLE_COMPUTER_USE`).
Лог: `data/autostart.log`. Перевірка: `scripts/verify_stack.ps1`. Видалити: `install_autostart.ps1 -Uninstall`.

---

## Telegram: токен і user_id

1. **Токен:** напиши [@BotFather](https://t.me/BotFather) → `/newbot` → отримаєш `TELEGRAM_BOT_TOKEN`.
2. **Свій user_id:** напиши [@userinfobot](https://t.me/userinfobot) — він поверне твій числовий ID.
   Впиши його в `ALLOWED_USER_IDS`. Друзів можна додавати вручну в `.env` або **погоджувати через бота**:
   друг пише боту будь-що → тобі приходить запит з кнопками ✅/❌ → `/allow ID` або `/pending`.
   Погоджені зберігаються в `data/access/users.json` (переживає рестарт). У `.env` лиши лише
   `ADMIN_USER_IDS` = свій ID, якщо не хочеш давати друзям `/admin`.

### Як заходять апдейти (long polling — за замовчуванням)

Gateway сам опитує Telegram через `getUpdates` (**long polling**). Це означає:

- ✅ **нічого не треба налаштовувати** — підняв стек, бот працює;
- ✅ **не потрібен публічний URL, тунель, домен чи сертифікат**;
- ✅ переживає будь-який рестарт сам — жодного ручного `setWebhook`;
- потрібен лише **вихідний** HTTPS до `api.telegram.org`.

```bash
docker compose up -d
docker compose logs -f gateway   # "Long polling started (getUpdates)"
```

На старті gateway сам знімає будь-який старий webhook (бо `getUpdates` і webhook
взаємовиключні для одного токена).

### Webhook-режим (опціонально, для прода)

Якщо є стабільний публічний HTTPS-домен (reverse proxy / named tunnel) — можна
перейти на push-модель. У `.env`:

```env
TELEGRAM_INGEST_MODE=webhook
TELEGRAM_WEBHOOK_SECRET=<token_hex(24)>   # захист /webhook від підробок (403)
```

Потім один раз зареєструвати адресу (URL не змінюється → робиться раз):

```bash
curl -X POST "https://api.telegram.org/bot$TOKEN/setWebhook" \
  -d url="https://your-domain/webhook" \
  -d secret_token="$TELEGRAM_WEBHOOK_SECRET" \
  -d allowed_updates='["message","edited_message","callback_query"]'
```

> Масштаб «вшир» (багато воркерів) не залежить від polling vs webhook: Telegram
> віддає апдейти одному споживачу на токен. Масштабована вісь — обробка:
> *ingestion → черга (Redis) → N воркерів*. Див. `ROADMAP.md`.

---

## Telegram Mini App (веб-дашборд)

Дашборд — це справжній веб-апп (`gateway/app/static/app.html`), а не текст у чаті:
статус сервісів, моделі, перемикач режиму роутингу наживо, Twin/LoRA. Подається
gateway-ом на `GET /app`, дані — `GET /app/data`, зміна режиму — `POST /app/mode`.
Доступ авторизується через Telegram `initData` (HMAC від bot-token + whitelist).

**Локально (одразу):** відкрий у браузері **http://localhost:8000/app**
(`WEBAPP_DEV_OPEN=true` пускає без Telegram-підпису).

**Усередині Telegram (Mini App).** Telegram відкриває апп лише по **HTTPS**, тож
потрібен публічний домен. Найпростіше — cloudflared-контейнер (профіль `tunnel`):

1. Cloudflare Zero Trust → **Networks → Tunnels → Create tunnel**, скопіюй токен.
2. У тунелі **Public Hostname**: `<домен>` → Service `http://gateway:8000`.
3. У `.env`: `CLOUDFLARE_TUNNEL_TOKEN=...` та `PUBLIC_APP_URL=https://<домен>/app`.
4. `docker compose --profile tunnel up -d` — gateway сам поставить кнопку-меню
   «📊 Dashboard» (зліва від поля вводу) і inline-кнопку в `/start`.

Named tunnel дає стабільний URL (на відміну від quick tunnel, який «стрибає»).
У проді постав `WEBAPP_DEV_OPEN=false` — тоді `/app` пускає лише з Telegram.

**Quick tunnel (без домену, автоматично).** Тимчасовий `*.trycloudflare.com` — URL
змінюється після рестарту контейнера, але скрипт сам оновлює `.env` і gateway:

1. У `.env`: `ENABLE_QUICK_TUNNEL=true` (і порожній `CLOUDFLARE_TUNNEL_TOKEN`).
2. `powershell -File scripts/setup_quick_tunnel.ps1` — підніме тунель, пропише
   `PUBLIC_APP_URL`, перезапустить gateway (кнопка «📊 Dashboard»).
3. Autostart/watchdog (кожні 5 хв) повторює синхронізацію, якщо URL змінився.

Зупинити: `powershell -File scripts/setup_quick_tunnel.ps1 -Stop`.

**Named tunnel (стабільний домен):** `powershell -File scripts/setup_tunnel.ps1` після
`CLOUDFLARE_TUNNEL_TOKEN` + `PUBLIC_APP_URL=https://<домен>/app` у `.env`.
У чаті: команда `/app` або кнопка «Dashboard»; deep links: `/start app`, `/start mode_agent`.

---

## Структура проєкту

```
.
├── docker-compose.yml      # усі сервіси, мережа jarvis-net, volumes, healthchecks
├── .env.example            # шаблон конфігу
├── README.md
├── pyproject.toml          # конфіг mypy (strict) + pytest
├── requirements-dev.txt    # dev/CI-залежності (mypy, pytest)
├── .github/workflows/      # CI: mypy + pytest (matrix) + compose-validate
├── gateway/                # FastAPI: long polling (getUpdates) + /webhook, auth, роутинг + tests/
├── whisper/                # STT (готовий образ, без коду)
├── memory/                 # RAG: embeddings + retrieval + tests/   (Фаза 4)
├── tools/                  # агентські інструменти + tests/         (Фаза 6)
├── hostagent/              # Computer Use: FastAPI на Windows-хості + tests/
├── db/
│   └── init.sql            # схема: sessions, messages, embeddings(vector)
├── n8n/
│   └── workflows/
│       └── agent_loop.json # експортований воркфлоу                (Фаза 3/6)
└── data/
    └── uploads/            # файли від користувача
```

---

## Корисні команди

```bash
docker compose up -d --build      # підняти/перебудувати
docker compose ps                 # статуси
docker compose logs -f <service>  # логи сервісу
docker compose down               # зупинити (дані лишаються у volumes)
docker compose down -v            # зупинити + ВИДАЛИТИ дані (скине БД, перезапустить init.sql)
```

---

## Розробка (типи + тести)

Кожен сервіс — окремий пакет `app`, тож статичні перевірки й тести ганяємо **по-сервісно**
(інакше три пакети `app` колізують в одному процесі). Залежності розробника — у `requirements-dev.txt`.

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r gateway/requirements.txt -r requirements-dev.txt

mypy gateway/app          # strict-типізація (конфіг у pyproject.toml)
pytest gateway/tests      # юніт-тести: mocked-клієнти, без мережі/БД
```

Те саме для `memory`, `tools` і `hostagent`. Тести покривають чисту логіку: маршрутизацію агента,
інструменти (`calc`/`coerce_args`/парсер DDG), rate-limit, circuit breaker, computer-use,
парсинг whitelist, роутинг text/voice. У CI (`.github/workflows/ci.yml`) matrix по
`jarvis_core`, `gateway`, `memory`, `tools`, `twin`, `hostagent` + `docker compose config`.

---

## Фази розробки

- [x] **Фаза 1 — Скелет:** структура, docker-compose, `.env.example`, `init.sql`, README.
- [x] **Фаза 2 — Gateway MVP:** вебхук → echo (без LLM).
- [x] **Фаза 3 — Ollama bridge:** gateway → n8n → Ollama (CHAT) → відповідь.
- [x] **Фаза 4 — Memory:** pgvector + RAG, контекст у промпті.
- [x] **Фаза 5 — Voice:** Whisper pipeline для голосових.
- [x] **Фаза 6 — Tools + дві моделі:** агент-луп з tool calling на AGENT-моделі.
- [x] **Фаза 7 — Polish:** rate limit (Redis), circuit breaker, healthchecks, фінал README.

---

## Режими, інструменти, надійність

**Маршрутизація моделей** (`AGENT_MODE` у `.env`):
- `chat` — завжди легка `OLLAMA_MODEL_CHAT`, без інструментів (найшвидше).
- `agent` — завжди `OLLAMA_MODEL_AGENT` із тул-лупом (макс 5 ітерацій).
- `hybrid` — евристика: математика / URL / пошукові ключі → agent, решта → chat.

**Інструменти агента:** `calc` (simpleeval), `web_search` (DuckDuckGo),
`web_fetch` (текст сторінки), `take_note`/`recall_notes` (персональні нотатки),
`set_reminder`/`list_reminders` (нагадування), `code_exec` (лише якщо `ENABLE_CODE_EXEC=true`).
Кожен доступний і окремим ендпойнтом Tools-сервісу (`/calc`, `/search`, `/web_fetch`, …).

**Нагадування:** «нагадай через 2 години / завтра о 9 …» → агент кладе нагадування
в Redis ZSET (спільний tools↔gateway). Gateway-поллер щохвилини-двадцять дістає
прострочені й шле «⏰ Нагадування: …». Поточний час інжектиться в agent-промпт,
тож модель сама рахує `delay_minutes` для конкретного часу.

**Стрім відповіді** (`ENABLE_STREAMING=true`, дефолт): Tools віддає інференс як
NDJSON-стрім (`/agent/stream`), gateway шле плейсхолдер «✍️ думаю…» і поступово
редагує його через `editMessageText` — текст «друкується», як у ChatGPT. У режимі
agent між цим показуються мітки інструментів («🧮 рахую…», «🔍 шукаю…»). Будь-який
збій стріму → тихий фолбек на класичний `/agent` тим самим повідомленням.

**Ops:** [`docs/THREAT_MODEL.md`](docs/THREAT_MODEL.md) · [`docs/IMAGE_GEN.md`](docs/IMAGE_GEN.md) · [`docs/COMPUTER_ROLLBACK.md`](docs/COMPUTER_ROLLBACK.md)

**Надійність:** rate-limit на `user_id` через Redis (`RATE_LIMIT_PER_MIN`, fail-open),
circuit breaker на Ollama (N помилок підряд → пауза, fail-fast замість зависань),
fallback-повідомлення на кожному зовнішньому виклику, healthchecks на всіх сервісах.

---

## Безпека

- Усі секрети — лише в `.env` (він у `.gitignore`). Нічого не хардкодимо.
- Доступ до бота — тільки whitelist `ALLOWED_USER_IDS`.
- `ENABLE_CODE_EXEC=false` за замовчуванням; вмикай виконання коду свідомо.
