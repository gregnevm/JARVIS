# JARVIS — Roadmap

Стек живий, Telegram E2E доведений, фази 1-7 (skeleton → polish) закриті, фаза 7.5
(зміцнення без Docker: mypy strict + 76 тестів + CI) теж.

**Статут (місія, принципи, 3 цілі-стовпи):** [`AGENTS.md`](AGENTS.md) — читається першим.  
**Парасолька повного продукту (фундамент + 3 стовпи, KPI, editions):** [`docs/PRODUCT_ROADMAP.md`](docs/PRODUCT_ROADMAP.md).  
**Треки стовпів:** API [`docs/API_PLATFORM_ROADMAP.md`](docs/API_PLATFORM_ROADMAP.md) · Coding [`docs/CODING_AGENT_ROADMAP.md`](docs/CODING_AGENT_ROADMAP.md) · Clients [`docs/CLIENTS_ROADMAP.md`](docs/CLIENTS_ROADMAP.md).  
**Platform (консоль `/platform`, Memory, Projects, MCP…):** [`docs/PLATFORM_ROADMAP.md`](docs/PLATFORM_ROADMAP.md).  
**Agent Mode / Computer Use (повний план AM-0…AM-4):** [`docs/AGENT_MODE_ROADMAP.md`](docs/AGENT_MODE_ROADMAP.md).  
**Мультитенант / SaaS (enabler для API + Clients):** [`docs/SAAS_DEEP_DIVE.md`](docs/SAAS_DEEP_DIVE.md).

Цей файл — **короткий ops-backlog** (must / nice / explore), а не повний product roadmap.
Історія зробленого — у `README.md` + `memory/`.

---

## Post-audit fixes (2026-06-04)

Після другого проходу аудиту: паритет streaming/deliver, origin для Computer confirm,
`agent_turn` модуль, `/start canvas` → Mini App `?canvas=1`, hybrid routing для скріншотів.
Операційний чеклист змінних: [`docs/ENV_CHECKLIST.md`](docs/ENV_CHECKLIST.md).

---

## Прогрес (оновлено 2026-06-04)

- ✅ **M1** Persistent Ollama (Vulkan+keep_alive 24h, автозапуск) — зроблено, verified.
- ✅ **M2** Long polling (getUpdates) як дефолт — **без публічного URL/тунелю**, переживає
  рестарти сам. Прибрано quick-tunnel машинерію (cloudflared/`tunnel`/хостові скрипти).
  `TELEGRAM_INGEST_MODE=polling|webhook`.
- ⏸️ **M2b** Webhook-режим для прода — named tunnel / домен + reverse proxy,
  `TELEGRAM_INGEST_MODE=webhook` + одноразовий setWebhook. За потреби.
- ✅ **M3** Webhook secret_token — `/webhook` перевіряє `X-Telegram-Bot-Api-Secret-Token` (403/200).
- ✅ **M4** Ротація токена — новий бот @BotFather, `.env` + recreate gateway (2026-06-05).
- ✅ **N4** Кеш ембедингів у Redis — зроблено, verified (кеш-хіт 0.01с).
- ✅ **N5** Log rotation — зроблено (≤50 МБ/контейнер).
- ✅ **E3** Multi-user — підтверджено (ізоляція по user_id у БД + per-user rate limit).
- ✅ **E4 (нотатки)** take_note/recall_notes + inline tool-call фолбек — зроблено, verified.
- ✅ **E4 (reminder)** активні нагадування — `set_reminder`/`list_reminders` (Redis ZSET) +
  gateway-поллер (`deliver_due`), час інжектиться в agent-промпт. Покрито тестами (на live чека ребілд).
- ✅ **N1** voice reply (TTS) — новий сервіс `tts/` (piper→OGG/Opus, uk голос), gateway
  шле голосом на голосові (текст-first фолбек, прапор `ENABLE_VOICE_REPLY`). Verified: OggS/Opus.
- ✅ **N2** web-діагностика → **Telegram Mini App** (`/app` + JSON-API, initData-HMAC,
  cloudflared-tunnel). Merged (PR #2), live на :8000/app.
- ✅ **N3** streaming-відповіді — Ollama `/api/chat` stream → Tools NDJSON (`/agent/stream`) →
  gateway `editMessageText`. Покрито тестами (на live чека ребілд `gateway`+`tools`).
- ⏳ **E1** llama.cpp benchmark, **E2** Ollama-in-Docker GPU (вердикт: НІ на цій машині) — експерименти.
- ⏳ **Twin Етап B/C/D** (Edge MVP · курація даних+eval · RunPod-training) — `docs/GAP_ANALYSIS.md`.

---

## Must — без цього в продакшені не запускати

### M1. Persistent Ollama з Vulkan + keep_alive
**Зараз:** Ollama стартую вручну з `OLLAMA_VULKAN=1` щоразу. Без `OLLAMA_KEEP_ALIVE`
моделі вивантажуються через 5 хв → cold-start ~55с при наступному запиті.

**Зробити:** Windows-сервіс або scheduled task, що піднімає Ollama з env vars:
```
OLLAMA_VULKAN=1
OLLAMA_HOST=0.0.0.0:11434
OLLAMA_KEEP_ALIVE=24h
```
Альтернатива простіше — `.bat` у `shell:startup` + `nssm install`.

**Перевірка:** ребут → `curl localhost:11434/api/tags` одразу відповідає; перший
TG-запит < 5с (модель уже в VRAM).

---

### M2. Long polling замість webhook+тунель ✅
**Було:** `cloudflared tunnel --url http://localhost:8000` дає одноразовий
`<random>.trycloudflare.com`; при перезапуску URL змінюється → webhook протухає,
530, бот мовчить. Спроба автоматизувати quick tunnel (сервіс `tunnel` + хостовий
cloudflared + парсинг URL із логів) виявилась крихкою: `api.trycloudflare.com`
у мережі періодично недоступний, URL нестабільний.

**Зроблено:** gateway отримує апдейти через **getUpdates (long polling)** —
`TELEGRAM_INGEST_MODE=polling` (дефолт). Жодного публічного URL, тунелю чи домену;
потрібен лише вихідний HTTPS до `api.telegram.org`. На старті gateway сам знімає
старий webhook. Quick-tunnel код/скрипти видалені.

**Чому це не блокує масштаб:** Telegram віддає апдейти лише одному споживачу на
токен — webhook теж «один прийом». Масштабована вісь — обробка, не прийом:
*ingestion → черга (Redis) → N воркерів* (див. нижче, S1). Перехід на webhook у
проді — це `TELEGRAM_INGEST_MODE=webhook` + одноразовий setWebhook, без змін логіки.

**Перевірка:** ребут хоста → бот відповідає без жодного ручного кроку.

### S1. Масштаб обробки: ingestion → черга → воркери (коли знадобиться)
**Ідея (YAGNI — не зараз):** `router.handle_update(update, ...)` уже приймає чистий
dict, тож джерело прийому відв'язане від обробки. Коли навантаження виросте:
ingestion (polling **або** webhook) кладе апдейт у Redis-чергу; N stateless-воркерів
споживають і обробляють паралельно. Це і є «винести модуль у сервіс без
рефакторингу логіки» з DESIGN. Зараз конкурентність дає `asyncio.create_task`
на апдейт у межах одного процесу — достатньо для особистого бота.

---

### M3. webhook secret_token (лише webhook-режим) ✅
**Контекст:** актуально тільки коли `TELEGRAM_INGEST_MODE=webhook`. У дефолтному
polling публічного `/webhook` не існує як вектора атаки (Telegram не шле POST).

**Зроблено:**
1. `.env`: `TELEGRAM_WEBHOOK_SECRET=...`.
2. `setWebhook` передає `secret_token`, Telegram шле `X-Telegram-Bot-Api-Secret-Token`.
3. `gateway/app/main.py` `/webhook` звіряє заголовок (`hmac.compare_digest`); не збігся → 403.

**Перевірка:** `curl <url>/webhook` без заголовка → 403. Реальний бот працює.

---

### M4. Rotate Telegram-токена
**Чому:** під час сесії 2026-06-03 токен світився у логах через httpx INFO ~10
хвилин до фікса. Технічно він міг потрапити в моніторинг/бекапи логів. Параноя ≠
шкода.

**Зробити:** [@BotFather](https://t.me/BotFather) → `/revoke` → новий токен у `.env`
→ recreate gateway.

---

## Nice — суттєво покращить UX/надійність

### N1. Voice reply (TTS) для Telegram
Whisper STT уже працює (фаза 5). Симетрично — TTS назад. Варіанти:
- **piper-tts** (локально, CPU, дуже швидко, є український голос) → ставимо в окремий
  Docker-сервіс, gateway після `sendMessage` тригерить `sendVoice`.
- **Coqui XTTS** — якісніше, але потребує GPU і VRAM нема (qwen2.5 займає 4.7 ГБ з 7.2).

Рекомендую piper — пишемо новий сервіс `tts/` за тим самим патерном що `whisper/`.

---

### N2. UI для діагностики (без Telegram)
Маленький web-UI на gateway (`/admin`) з basic-auth (як n8n):
- стан 7 контейнерів,
- останні 20 сесій з відповідями,
- кнопка "повторно ембеддингувати все" (для зміни моделі),
- pgvector top-K пошук вручну.

Зекономить багато `docker compose logs -f`.

---

### N3. Streaming-відповіді для довгих агент-запитів
Зараз `/agent` чекає 15-25с і вивантажує всю відповідь разом. Telegram дозволяє
`editMessageText` — можна показати «✍️ думаю…», потім частинами оновлювати.

Зробити: переробити `OllamaClient.chat` у генератор (stream=True), gateway шле
проміжні `editMessageText`. UX наближається до "як у ChatGPT".

---

### N4. Кеш ембедингів
Зараз кожне повідомлення (включно з типу "ок", "так", "дякую") йде через `nomic-embed-text`.
Це 50-100 мс, але набивається. Швидкий хеш-кеш у Redis: `SET emb:<sha256(text)>
<vector_bytes> EX 86400`. Економимо разів у 3-5 на повторюваному тексті.

---

### N5. Структуроване логування + log rotation
Зараз uvicorn пише plain INFO у stdout, Docker пише все у файл без ліміту → growing
forever. Додати:
- `loguru` або вбудоване `structlog` → JSON-лінії.
- `docker-compose.yml` → кожному сервісу:
  ```yaml
  logging:
    driver: json-file
    options: { max-size: "10m", max-file: "5" }
  ```

---

## Explore — варто перевірити, чи треба

### E1. Замість Ollama — llama.cpp напряму з Vulkan
Ollama зручна, але крутиться як окремий процес із власним керуванням пам'яттю.
llama.cpp на тих самих vulkan-runtimes іноді **на 20-30% швидше** + дає OpenAI-сумісне
API через `llama-server`. Drop-in заміна (`OLLAMA_HOST` → llama-server URL).

Експеримент: підняти llama.cpp поряд, прогнати ті самі моделі, виміряти tok/s.

### E2. Перенести Ollama в Docker з GPU — ✅ ДОСЛІДЖЕНО, ВЕРДИКТ: НІ (на цій машині)

**Перевірено 2026-06-03:** у Docker-контейнері (Windows/WSL2-бекенд) **немає ні `/dev/dri`,
ні `/dev/kfd`** → AMD GPU фізично недоступний усередині контейнера. Ні Vulkan, ні ROCm
у контейнері не запрацюють. Тобто контейнеризований Ollama тут рахував би **на CPU** —
гірше, ніж поточний хостовий Ollama з Vulkan (~8x швидше).

**Рішення: лишаємо Ollama на ХОСТІ (поточний дизайн правильний).** Це не борг, а свідомий
вибір під залізо. Контейнеризований GPU-Ollama має сенс ЛИШЕ на:
- Linux-хості (там `/dev/dri`+`/dev/kfd` пробрасуються нативно, AMD ROCm працює), або
- будь-де з **NVIDIA** (NVIDIA Container Toolkit + `/dev/dxg` у WSL2 — підтримується).

Закоментований блок `ollama` у `docker-compose.yml` лишається для саме таких сценаріїв.

### E3. Multi-user ✅ (базово)
- **Погодження через бота:** `/allow`, `/pending`, inline ✅/❌; збереження `data/access/users.json`.
- **Базовий whitelist** у `.env` + динамічні друзі; `ADMIN_USER_IDS` — лише власник.
- **Ізоляція:** RAG/нотатки/нагадування по `user_id`; `GUEST_RATE_LIMIT_PER_MIN` для друзів.
- **Безпека:** `/mode` і computer-режим — лише адміни (`can_change_agent_mode`).

### E4. Власні інструменти агента
Toolkit має `calc, web_search, web_fetch, parse_file, code_exec`. Очевидні наступні:
- **`take_note`** — записати щось у persistent storage (свій knowledge base).
- **`reminder`** — Cron-style: «нагадай завтра о 9 ранку».
- **`shell_exec`** — небезпечно, але корисно (за whitelistом команд).

Архітектура агент-лупа (фаза 6) робить це питанням 50 рядків Python + JSON-схема
кожен. Додати в `tools/app/toolkit/` (пакет) + `TOOL_SCHEMAS`.

### E5. Computer Use (Agent Mode) — керування реальним комп'ютером ✅ інфра · ⏳ автономність

**Зроблено (C0–C6 інфра):** host-agent, toolkit T0–T4, confirm+audit, Playwright,
UIA lite, admin gate, vision/screenshot, cursor_task, cascade routing.
Деталі: [`docs/COMPUTER_USE.md`](docs/COMPUTER_USE.md), PRODUCT фаза 2.

**Наступний етап — «справжній Agent Mode»** (розриви G1–G11, фази AM-0…AM-4):
- AM-0: динамічний промпт, `see_screen` у лупі, `COMPUTER_PROFILE`, session trust
- AM-1: keyboard/hotkey/scroll, справжній UIA (pywinauto), vision-action loop
- AM-2: computer planning (один ✅ на план), bg jobs, observation buffer
- AM-3: Platform Computer tab, session replay
- AM-4: policy engine, native bridges, edition matrix

**Повний розгорнутий план:** [`docs/AGENT_MODE_ROADMAP.md`](docs/AGENT_MODE_ROADMAP.md).

**Безпека (без змін):** дефолт вимкнено; admin — double confirm; audit `computer.jsonl`.

---

## Звідки знаю, що це правильні наступні кроки

- **M1-M2** — поточна установка не переживає ребуту без ручної роботи. Це блокер
  для будь-якого "ну, тепер просто користуватись".
- **M3-M4** — security debt з реального інциденту цієї сесії.
- **N1-N3** — UX. JARVIS уже "працює", але якщо ти будеш ним користуватись —
  TTS + streaming роблять його приємним.
- **E1-E4** — це питання "куди це може вирости". Робиться, коли є конкретний
  use case, не "про запас".

---

## Що НЕ робити (свідомо)

- **Не міняти модель ембедингів** без міграції pgvector. `nomic-embed-text` = 768D,
  таблиця жорстко на `vector(768)`. Зміна = повний re-embed усього історії.
- **Не вмикати `ENABLE_CODE_EXEC=true`** без sandbox-isolation. Зараз код виконується
  через `subprocess [sys.executable, "-I", "-c", code]` у tools-контейнері — це
  обмежений, але не повний sandbox.
- **Не починати "переписати на FastStream/Celery/тощо"** — поточний async-стек на
  FastAPI + httpx обробляє Telegram-навантаження одного користувача із запасом 100x.
- **Не вмикати `EnableDockerAI=true`** у Docker Desktop ≤4.76 без фіксу від Docker.
  Зламає daemon.
