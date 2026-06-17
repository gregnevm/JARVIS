# AGENTS.md — Статут JARVIS для агентів кодування

> **Версія:** 1.0 (2026-06-15)
> **Статус:** Living charter — читається **першим** будь-яким агентом кодування (Claude Code,
> Cursor, Codex, Continue, а також самим JARVIS, коли він пише код).
> **Призначення:** єдине джерело **місії, принципів і цілей**. Roadmap-и кажуть «що і коли
> будувати»; цей файл каже «що ми будуємо взагалі і за якими правилами».

Цей документ — конституція. Якщо roadmap чи коментар у коді суперечить принципу звідси —
правий цей файл, а суперечність треба виправити (і завести в `docs/IMPROVEMENT_PROPOSALS.md`).

---

## 1. Місія (one-liner)

> **JARVIS** — суверенна, local-first AI-платформа, яка одночасно є **(1) платформою розробника
> з API** (як OpenAI/Anthropic Platform), **(2) агентом кодування рівня Claude Code** (краще за
> Cursor/Codex), і **(3) мультиплатформою** — веб-консоль керування, ендпоїнти через Telegram,
> мобільний застосунок (APK). Inference локальний, дані твої, контроль повний.

Ми **не** будуємо «ще один чат-бот». Ми будуємо інфраструктуру, яку:
- розробник підключає через `Bearer sk-jarvis-…` і ганяє свій код/агентів;
- власник відкриває як **штаб** у браузері або з телефона;
- і яка вміє **сама писати, правити й рев'ювити код** на реальній машині.

---

## 2. Три цілі-стовпи (головні цілі продукту)

Кожен PR має просувати хоча б один стовп — або зміцнювати фундамент під ними.

### 🅰 Стовп A — Платформа розробника з API (OpenAI/Anthropic-style)

**Що це означає конкретно:** не «один глобальний ключ у `.env`», а повноцінний developer platform:
per-org API-ключі зі scopes, повний `/v1/*` surface (chat, embeddings, models, responses,
tool-use), usage-метрика й білінг, rate-limit на ключ, dev-консоль із playground, SDK, ліміти за
планом. Self-hosted інстанс = один synthetic org; cloud = мультитенант.

| Зараз | Ціль |
|-------|------|
| `/v1/chat/completions` + `/v1/models`, opt-in, 1 глобальний ключ | per-org keys, `/v1/embeddings\|responses\|models`, usage, playground, SDK |

**Деталі:** [`docs/API_PLATFORM_ROADMAP.md`](docs/API_PLATFORM_ROADMAP.md) · мультитенант: [`docs/SAAS_DEEP_DIVE.md`](docs/SAAS_DEEP_DIVE.md)

### 🅱 Стовп B — Агент кодування рівня Claude Code (або краще)

**Що це означає конкретно:** repo-aware агент, який читає й редагує файли диффами, тримає в
контексті проєкт, ганяє термінал/тести, робить multi-file рефактор, планує → апрувить →
виконує, рев'ювить власні зміни, працює через MCP і субагентів. Не «обгортка над cursor CLI» —
**рідний** агент-луп (`tools/app/agent.py` + `jarvis_core`), що працює і на хмарі, і офлайн на Edge.

| Зараз | Ціль |
|-------|------|
| мости `cursor_task` + `continue_dev`, computer-mode PS/CLI/browser/UIA | рідний coding-агент: diff-edit, repo-граф, тест-луп, review, CLI/IDE-режим |

**Деталі:** [`docs/CODING_AGENT_ROADMAP.md`](docs/CODING_AGENT_ROADMAP.md) · desktop-керування: [`docs/AGENT_MODE_ROADMAP.md`](docs/AGENT_MODE_ROADMAP.md)

### 🅲 Стовп C — Мультиплатформа (web · Telegram · mobile APK)

**Що це означає конкретно:** один бекенд — багато каналів. **Telegram** лишається primary
каналом споживання. **Web-консоль** (`/platform`) — штаб керування, еволюціонує з server-rendered
HTML у справжній SPA/PWA. **Mobile APK** (Android) — рідний клієнт: чат, voice, push, workbench,
computer-confirm з телефона. Єдина auth і єдиний API під усіма клієнтами.

| Зараз | Ціль |
|-------|------|
| Telegram ✅ · `/platform` HTML ✅ · mobile ❌ | Telegram ✅ · Web SPA/PWA · Android APK · спільна auth/API |

**Деталі:** [`docs/CLIENTS_ROADMAP.md`](docs/CLIENTS_ROADMAP.md)

> **Парасолька над усіма трьома стовпами:** [`docs/PRODUCT_ROADMAP.md`](docs/PRODUCT_ROADMAP.md).

---

## 3. Принципи (у порядку пріоритету)

**Продуктові (що робить JARVIS особливим):**

| # | Принцип | Наслідок для коду |
|---|---------|-------------------|
| S1 | **Sovereignty / local-first** | inference локальний (Ollama/Kobold); зовнішні AI-API лише як явний opt-in, ніколи не дефолт |
| S2 | **Self-hosted ніколи не ламається** | будь-яка SaaS/мультитенант-фіча за прапором; `SAAS_MODE=false` → synthetic org, Telegram-flow без змін |
| S3 | **Telegram — канал, Platform — штаб** | бізнес-логіка не живе в каналі; gateway робить лише I/O, мозок у tools/`jarvis_core` |
| S4 | **Human-in-the-loop для дій** | мутуючі/незворотні дії (FS, PS, admin, гроші) — підтвердження; ніколи не auto-confirm для admin/power |
| S5 | **Tier ladder** | агент ніколи не клікає мишею, якщо задачу можна зробити пряміше (T0 PS → T4 vision) |

**Інженерні (P1–P10 + C1, з [`docs/DESIGN.md`](docs/DESIGN.md) §1.2 / §1.2.1, обов'язкові):**

| # | Принцип | Наслідок |
|---|---------|----------|
| P1 | Offline-first | Edge працює без мережі як primary сценарій |
| P2 | Fail Fast | валідація на вході, не в середині виконання |
| P3 | Explicit over Implicit | стан явний, залежності явні, ніякої магії |
| P4 | Composition over Inheritance | поведінка збирається з частин (роутери `register()`, адаптери) |
| P5 | Open/Closed | новий транспорт/стратегія = новий клас, не зміна існуючого |
| P6 | YAGNI | будуємо потрібне зараз; не «про запас» (напр. не Celery, поки async справляється) |
| P7 | Single Source of Truth | ModelRegistry — авторитет про версії; цей файл — про принципи |
| P8 | Separation of Concerns | Training ≠ Inference ≠ Sync ≠ UI; gateway ≠ tools ≠ memory |
| P9 | **Context Passport (summarize all)** | жоден артефакт не входить «голим»: кожен несе summary + embedding для контекстної індексації |
| P10 | **Tag Everything** | кожен паспорт має namespaced-теги — для ретриву **і** як адресовний хендл (виклик блоку за тегом) |

**Контекстна культура (наскрізна, критична — деталі [`DESIGN.md`](docs/DESIGN.md) §1.2.1):**

> **C1 — Паспорт + теги всюди.** «Summarize all, tag everything» — це не фіча сервісу, а
> наскрізний контракт. Усе значуще (повідомлення, подія, daily, tool, skill, subagent, файл,
> символ, run, doc, endpoint) отримує **паспорт контексту** (`kind` + `summary` + namespaced
> `tags` + embedding 768D). Теги мають **дві ролі**: індексація (`person:mom AND topic:rent`) і
> **адресація** (виклик `module:scam-shield`). Новий записуваний артефакт без `summary`/тегів — баг.

**Документаційний (критично для здоров'я репо):**

> **D1 — Doc-code sync.** Код і roadmap-и — одне ціле. Закрив задачу → постав `[x]` у
> відповідному roadmap у тому ж PR. Додав фічу → онови `.env.example` і doc-map. Розбіжність
> «код vs doc» = баг, який заводиться в [`docs/IMPROVEMENT_PROPOSALS.md`](docs/IMPROVEMENT_PROPOSALS.md).

---

## 4. Архітектура (мапа для орієнтації)

```
                       ┌──────────── КАНАЛИ / КЛІЄНТИ (Стовп C) ───────────┐
   Telegram  ·  Web /platform (SPA→PWA)  ·  Mobile APK  ·  OpenAI API /v1 (Стовп A)
                       └───────────────────────┬───────────────────────────┘
                                               ▼
   gateway (8000)  — I/O, auth, rate-limit, роутинг, /platform, /v1, Mini App
                                               ▼  (tools_client_http: X-JARVIS-* headers)
   tools (8200)    — агент-луп + інструменти + coding-агент (Стовп B)
        │                jarvis_core/  — facade · pipeline · routing · llm-adapters · bg_jobs
        ├─► Ollama (ХОСТ, Vulkan)      CHAT | AGENT | VISION | EMBED
        ├─► memory (8100)  pgvector RAG · projects · sessions
        ├─► hostagent (8400, на хості) PS/CLI/FS/browser/UIA/screen  (Computer Use)
        └─► twin (8765)    ModelRegistry · LoRA sync · Edge ingest
   whisper(9000) STT · tts(8300) TTS · postgres(5432) · redis(6379)
   edge/  — USB-портативний рантайм (KoboldCPP + SQLite-vec), офлайн → LAN → VPN
```

**Де живе кожен стовп у коді:**
- **A (API):** `gateway/app/openai_api.py`, майбутній `gateway/app/saas/*`, `memory/migrations/`
- **B (Coding agent):** `tools/app/agent.py`, `tools/app/cursor_tasks.py`, `tools/app/tools/continue_tool.py`, `jarvis_core/`, `hostagent/`
- **C (Clients):** `gateway/app/static/platform.html`, `gateway/app/webapp.py`, `gateway/app/bot/`, майбутній `mobile/`

Кожен сервіс — окремий Python-пакет `app` (тести й mypy ганяються **по-сервісно**, інакше колізія
пакета `app`). Спільний код — у `jarvis_core/` (не створювати четвертий shared-пакет).

---

## 5. Як працювати в цьому репо (операційний мануал)

**Перед стартом великої зміни:**
1. Прочитай цей файл + релевантний roadmap. Звір код із doc — якщо дрейф, виправ обидва.
2. Багатофазний білд → виконуй **послідовно, без запитів дозволу, звіт після кожної фази**.

**Тести й типи (по-сервісно, завжди):**
```powershell
pytest gateway/tests ; pytest tools/tests ; pytest memory/tests ; pytest hostagent/tests
mypy gateway/app    # strict; конфіг у pyproject.toml. Те саме для tools/memory/jarvis_core
```
CI (`.github/workflows/ci.yml`) — matrix по `jarvis_core/gateway/memory/tools/twin/hostagent` +
`docker compose config`. PR не мерджиться без green.

**Залізні правила:**
- 🔒 **Секрети лише в `.env`** (він у `.gitignore`). Нічого не хардкодимо, нічого не світимо в логах.
- 🆕 **Нова фіча за прапором.** Дефолт безпечний (`ENABLE_*=false`, `COMPUTER_ALLOW_ADMIN=false`,
  `ENABLE_CODE_EXEC=false`). Додав прапор → опиши в `.env.example` + [`docs/ENV_CHECKLIST.md`](docs/ENV_CHECKLIST.md).
- 🧩 **Композиція роутерів:** новий розділ Platform/tools = новий модуль із `register(router)`, один
  рядок у `router.py`. Не роздувай моноліт.
- 🪟 **Windows/PowerShell:** файли з кирилицею пиши з BOM (UTF-8-BOM) інакше кракозябри; `Get-ScheduledTask`
  висне в дочірньому PS — використовуй COM/`schtasks`; `$Args` не `$args` у деяких контекстах; перевіряй порти через `netstat`.
- 🧪 **Тест-first для логіки:** маршрутизація, парсери, guard-и, tool-схеми — покривай юніт-тестами
  (mocked-клієнти, без мережі/БД), як у наявних `tests/`.
- 📝 **Conventional commits** (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`). Гілка від `main`, не комітимо в `main` напряму.
- 🤖 **Tier ladder в Computer Use:** PS/CLI/FS/browser/UIA — раніше за піксельний клік. Tier пишеться в `data/logs/computer.jsonl`.

**Multi-tenant дисципліна (готуємо ґрунт під Стовп A навіть зараз):**
- Новий Redis-ключ → закладай org-префікс (`jarvis:{org_id}:…`), навіть якщо зараз org синтетичний.
- Новий `get_by_id` → перевіряй ownership (`rec["user_id"]`/`org_id`), інакше IDOR. Див. SAAS §4.0.
- Tenant-логіка — у `jarvis_core/`, не дублюй gateway↔tools.

---

## 6. Guardrails / Свідомо НЕ робимо

- ❌ **Зовнішній AI-API як дефолт для inference** — лише явний opt-in; ламає S1.
- ❌ **`ENABLE_CODE_EXEC=true` без sandbox-ізоляції** — поточний `subprocess -I` не повний sandbox.
- ❌ **Зміна embed-моделі без міграції** — `nomic-embed-text`=768D жорстко; зміна = повний re-embed (Alembic).
- ❌ **Ollama в Docker на AMD/Windows** — немає `/dev/dri`/`/dev/kfd` у WSL2 (ADR-E2). Ollama лишається на хості.
- ❌ **Auto-confirm для admin/power computer-дій** — завжди double confirm (C5).
- ❌ **SaaS-фіча, що ламає self-hosted** — усе за `SAAS_MODE`; synthetic org backfill обов'язковий.
- ❌ **Переписати агент-луп на LangGraph/CrewAI** чи бекенд на Celery/FastStream — поточний async достатній (P6).
- ❌ **n8n як оркестратор** — legacy `profiles: ["legacy"]`; агент-луп живе в Python.
- ❌ **Записувати значущий артефакт без паспорта** — `summary`+теги обов'язкові (P9/P10/C1); «голий» store/event = баг.

---

## 7. Doc-map (звідки що читати)

| Документ | Роль | Рівень |
|----------|------|--------|
| **`AGENTS.md`** (цей) | Місія, принципи, цілі, мануал агента | Конституція |
| [`docs/PRODUCT_ROADMAP.md`](docs/PRODUCT_ROADMAP.md) | **Парасолька** повного продукту: 3 стовпи + фундамент, фази, KPI | Стратегія |
| [`docs/CODING_AGENT_ROADMAP.md`](docs/CODING_AGENT_ROADMAP.md) | Стовп B детально (CA-0…CA-n) | Трек |
| [`docs/API_PLATFORM_ROADMAP.md`](docs/API_PLATFORM_ROADMAP.md) | Стовп A детально (AP-0…AP-n) | Трек |
| [`docs/CLIENTS_ROADMAP.md`](docs/CLIENTS_ROADMAP.md) | Стовп C детально (web/TG/mobile, CL-0…CL-n) | Трек |
| [`docs/PLATFORM_ROADMAP.md`](docs/PLATFORM_ROADMAP.md) | Web-консоль `/platform` P0–P12 (done) + Phase 7 | Трек |
| [`docs/AGENT_MODE_ROADMAP.md`](docs/AGENT_MODE_ROADMAP.md) | Computer Use / desktop-керування AM-0…AM-4 | Трек |
| [`docs/SAAS_DEEP_DIVE.md`](docs/SAAS_DEEP_DIVE.md) | Мультитенант impl-blueprint (PR#0…#7) | Трек (enabler) |
| [`ROADMAP.md`](ROADMAP.md) | Короткий ops-backlog (M/N/E/S) | Ops |
| [`docs/DESIGN.md`](docs/DESIGN.md) | Архітектура PortableAI (Edge+Twin+LoRA), ADR | Архітектура |
| [`docs/GAP_ANALYSIS.md`](docs/GAP_ANALYSIS.md) | PortableAI vs поточний стек | Аналіз |
| [`docs/THREAT_MODEL.md`](docs/THREAT_MODEL.md) · [`docs/ENV_CHECKLIST.md`](docs/ENV_CHECKLIST.md) · [`docs/COMPUTER_USE.md`](docs/COMPUTER_USE.md) | Безпека · env · tier-контракт | Ops |
| [`docs/IMPROVEMENT_PROPOSALS.md`](docs/IMPROVEMENT_PROPOSALS.md) | Інженерний лог дедуплікації/тестів (не продуктовий) | Інженерний |

**Правило статусів (проти дрейфу):** task-level чекбокси `[x]/[ ]` живуть у **трек-roadmap-ах**.
Парасолька (`PRODUCT_ROADMAP`) тримає лише **фазовий** статус. `ROADMAP.md` — лише ops. Цей файл —
**без статусів** (тільки принципи й цілі). Один факт — одне місце.

---

*Оновлюй цей статут, коли змінюється місія/принципи/цілі — не частіше. Дрібний прогрес іде в roadmap-и.*
