# JARVIS — Roadmap

Стек живий, Telegram E2E доведений, фази 1-7 (skeleton → polish) закриті, фаза 7.5
(зміцнення без Docker: mypy strict + 76 тестів + CI) теж. Цей файл — про те, що
ефективно зробити **далі**, а не про вже зроблене (історія — у `README.md` + `memory/`).

Поділено на **must / nice / explore** і пронумеровано — щоб брати по черзі.

---

## Прогрес (оновлено 2026-06-03)

- ✅ **M1** Persistent Ollama (Vulkan+keep_alive 24h, автозапуск) — зроблено, verified.
- ⏸️ **M2** Named tunnel — потребує Cloudflare-акаунта (інструкція нижче), за користувачем.
- ✅ **M3** Webhook secret_token — зроблено, verified (403/200), `scripts/set_webhook.ps1`.
- ⏸️ **M4** Ротація токена — за користувачем (@BotFather).
- ✅ **N4** Кеш ембедингів у Redis — зроблено, verified (кеш-хіт 0.01с).
- ✅ **N5** Log rotation — зроблено (≤50 МБ/контейнер).
- ✅ **E3** Multi-user — підтверджено (ізоляція по user_id у БД + per-user rate limit).
- ✅ **E4 (нотатки)** take_note/recall_notes + inline tool-call фолбек — зроблено, verified.
  - ⏳ **E4 (reminder)** активне спрацювання — окремий follow-up (Redis ZSET + gateway-поллер).
- ✅ **N1** voice reply (TTS) — новий сервіс `tts/` (piper→OGG/Opus, uk голос), gateway
  шле голосом на голосові (текст-first фолбек, прапор `ENABLE_VOICE_REPLY`). Verified: OggS/Opus.
- ⏳ **N2** admin UI, **N3** streaming — великі білди, попереду.
- ⏳ **E1** llama.cpp benchmark, **E2** Ollama-in-Docker GPU — експерименти, попереду.

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

### M2. Cloudflare named tunnel замість quick tunnel
**Зараз:** `cloudflared tunnel --url http://localhost:8000` дає одноразовий
`<random>.trycloudflare.com`. При перезапуску URL змінюється → треба оновлювати
Telegram webhook руками. Якщо тунель упав посеред дня — бот мовчить.

**Зробити:** іменований тунель `cloudflared tunnel create jarvis`, CNAME на
свій домен (або безкоштовний `.cf` через Cloudflare Zero Trust), `cloudflared
service install` як Windows service. Webhook ставимо **один раз** на постійну
адресу.

**Перевірка:** ребут хоста → бот відповідає без жодного ручного кроку.

---

### M3. setWebhook у скрипт + secret_token
**Зараз:** webhook ставився вручну, без secret_token → будь-хто з URL може
надсилати фейкові апдейти на `/webhook`.

**Зробити:**
1. Додати у `.env` секретний `TELEGRAM_WEBHOOK_SECRET=...`.
2. `setWebhook` передає `secret_token=$SECRET`, Telegram потім шле
   заголовок `X-Telegram-Bot-Api-Secret-Token: $SECRET`.
3. У `gateway/app/main.py` `/webhook` перевіряє заголовок; якщо не збігається — 401.
4. Скрипт `scripts/set_webhook.sh` що читає `.env` і ставить webhook.

**Перевірка:** `curl <tunnel>/webhook` без заголовка → 401. Реальний бот працює.

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

### E3. Multi-user
Зараз `ALLOWED_USER_IDS` — простий whitelist. Для родини/друзів-команди:
- pgvector сесії вже мають `user_id` (готово в БД).
- Додати простий per-user `RATE_LIMIT_PER_MIN`.
- Можливо, per-user history isolation (зараз memory.search фільтрує по user_id — уже ОК).

### E4. Власні інструменти агента
Toolkit має `calc, web_search, web_fetch, parse_file, code_exec`. Очевидні наступні:
- **`take_note`** — записати щось у persistent storage (свій knowledge base).
- **`reminder`** — Cron-style: «нагадай завтра о 9 ранку».
- **`shell_exec`** — небезпечно, але корисно (за whitelistом команд).

Архітектура агент-лупа (фаза 6) робить це питанням 50 рядків Python + JSON-схема
кожен. Додати в `tools/app/toolkit.py` + `TOOL_SCHEMAS`.

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
  Зламає daemon (див. memory/project_jarvis.md).
