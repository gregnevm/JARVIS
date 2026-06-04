# JARVIS — повністю локальний AI-асистент у Telegram

Self-hosted Telegram-бот на мікросервісах. Усе працює локально: LLM через **Ollama**,
агент-луп у **Tools** (Python), пам'ять через **PostgreSQL + pgvector**, голос через **Whisper**,
синхронізація Edge↔Twin через **twin** (SyncServer + ModelRegistry). Жодних зовнішніх AI API.
Запуск — один `docker compose up`. Цільова архітектура PortableAI — `docs/DESIGN.md`.

> Статус: **усі 7 фаз готові** — скелет, gateway, Ollama-bridge, памʼять/RAG, голос,
> Tools + агент-луп на двох моделях, polish (rate limit, circuit breaker, healthchecks).
> Чеклист — у кінці README.

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
curl http://localhost:8100/health     # memory
docker compose ps                     # статуси + healthcheck
```

---

## Telegram: токен і user_id

1. **Токен:** напиши [@BotFather](https://t.me/BotFather) → `/newbot` → отримаєш `TELEGRAM_BOT_TOKEN`.
2. **Свій user_id:** напиши [@userinfobot](https://t.me/userinfobot) — він поверне твій числовий ID.
   Впиши його в `ALLOWED_USER_IDS` (кілька — через кому). Бот ігнорує всіх, кого нема у списку.

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

Те саме для `memory` і `tools`. Тести покривають чисту логіку: маршрутизацію агента,
інструменти (`calc`/`coerce_args`/парсер DDG), rate-limit, circuit breaker, парсинг
whitelist, роутинг text/voice. У CI (`.github/workflows/ci.yml`) усе це йде matrix-ом
по трьох сервісах + валідація `docker compose config`.

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
`web_fetch` (текст сторінки), `code_exec` (лише якщо `ENABLE_CODE_EXEC=true`).
Кожен доступний і окремим ендпойнтом Tools-сервісу (`/calc`, `/search`, `/web_fetch`, …).

**Стрім відповіді** (`ENABLE_STREAMING=true`, дефолт): Tools віддає інференс як
NDJSON-стрім (`/agent/stream`), gateway шле плейсхолдер «✍️ думаю…» і поступово
редагує його через `editMessageText` — текст «друкується», як у ChatGPT. У режимі
agent між цим показуються мітки інструментів («🧮 рахую…», «🔍 шукаю…»). Будь-який
збій стріму → тихий фолбек на класичний `/agent` тим самим повідомленням.

**Надійність:** rate-limit на `user_id` через Redis (`RATE_LIMIT_PER_MIN`, fail-open),
circuit breaker на Ollama (N помилок підряд → пауза, fail-fast замість зависань),
fallback-повідомлення на кожному зовнішньому виклику, healthchecks на всіх сервісах.

---

## Безпека

- Усі секрети — лише в `.env` (він у `.gitignore`). Нічого не хардкодимо.
- Доступ до бота — тільки whitelist `ALLOWED_USER_IDS`.
- `ENABLE_CODE_EXEC=false` за замовчуванням; вмикай виконання коду свідомо.
