# JARVIS — Пропозиції для покращень

> Генерується/оновлюється циклом `/loop покращуй всі фічі згідно roadmap…`.
> Кожен прохід: перевірка (mypy/tests) → архітектурний огляд → нові пропозиції → позначення закритих.

**Останній прохід:** 2026-06-08

---

## Стан перевірки (цей прохід)

| Перевірка | Результат |
|-----------|-----------|
| `mypy gateway/app` (strict) | ✅ 71 файл, 0 помилок |
| `mypy memory/app` (strict) | ✅ 6 файлів, 0 помилок |
| `pytest gateway/tests` | ✅ 266/266 |
| `pytest memory/tests` | ✅ 46/46 (17 попередніх + 29 нових із проходу 37) |
| `pytest gateway/tests -k "access or admin"` (цільовий, прохід 36) | ✅ 27/27 |
| `grep TODO/FIXME/XXX/HACK` у `app/` усіх сервісів | ✅ 0 знайдено (підтверджено раніше) |

Виправлено в цьому проході:
- **прохід 37** — `memory/tests/test_main_routes.py`: 0%→прямі ASGI-тести
  для всього route-шару `memory/app/main.py` (29 нових тестів, новий
  патерн `httpx.ASGITransport` для FastAPI без запуску `lifespan`);
- **прохід 36** — `gateway/app/bot/access.py`: два мовчазні
  `except Exception: pass` переписані за зразком сусіднього патерну
  `except Exception as exc: # noqa: BLE001 — <причина>` + `logger.warning(...)`
  — без зміни поведінки, лише видимість у логах.

Деталі — нижче, у відповідних пропозиціях "Прохід 2026-06-08
(тридцять шостий/сьомий)".

---

## Пропозиції (нові / відкриті)

### A. CI gate: зафіксувати mypy strict у пайплайні · ✅ вже зроблено (виявлено у проході 25)
**Чому пропозиція виникла:** щойно довели всі сервіси до `mypy --strict` success —
здавалось природним перевірити, чи це закріплено в CI як інваріант, а не одноразове
досягнення.

**Знахідка (прохід 25):** це вже зроблено — і давно. `.github/workflows/ci.yml`
(останній раз торкався комітом `e15e326`, **2026-06-04**, тобто ДО появи цього
proposal-документа) містить job `check` із `matrix.service: [jarvis_core, gateway,
memory, tools, twin, hostagent]` (усі 6 сервісів, не 5), що для кожного запускає
`mypy ${{ matrix.service }}/app` (або `mypy jarvis_core` для core-пакету) — точно
обходячи колізію `Duplicate module named "app"`, як і вимагала пропозиція. Перевірив
`pyproject.toml` — `[tool.mypy] strict = true` на рівні кореня репо, тож ці CI-виклики
автоматично йдуть у strict-режимі (mypy шукає конфіг від CWD вгору, а workflow
запускається з кореня checkout). Failure будь-якого з 6 — red CI, блокує merge.
**DoD виконано без додаткових дій:** CI вже фейлиться red при регресії strict mode
у будь-якому сервісі — саме це й вимагалось. Цю пропозицію закриваю як таку, що
описує вже наявний стан; залишаю запис в історії, щоб не загубити контекст "чому
ми про це думали" (а не видаляти безслідно — як і з ADR-знахідками).
**Урок:** перш ніж додавати "TODO: перевір чи є X у CI" у відкриті пропозиції — варто
спершу прочитати сам CI-файл (30 секунд), а не покладатись на припущення "ймовірно
ще не налаштовано". Сформулював пропозицію без перевірки джерела істини — і вона
виявилась вже закритою на момент написання.

### B. `register_tools_*` proxy helpers — розширити охоплення · ✅ частково зроблено (2026-06-07)
**Зроблено цей прохід:** `jobs_list` (`jobs.py`) і `plans_list` (`plans.py`) — обидва були
1:1 копією шаблону `register_tools_list` (uid resolution + limit + wrap_key) — замінено
на виклик хелпера, −20 рядків boilerplate сумарно. Перевірено: `mypy gateway/app` ✅ 69 файлів,
`pytest gateway/tests/test_platform_{jobs,plans}.py test_platform.py` ✅ 37/37,
повний `pytest gateway/tests` — без регресій.

**Уточнення (прохід 5):** початкова оцінка "*_get мають різну 404-обробку" виявилась
неточною для 4 з них — `jobs_get`/`plans_get`/`skills_get`/`teams_get` були побайтово
ідентичним патерном (`GET /.../{id}` → `tools.get_X(id)` → 404 якщо `None`). Винесено
у новий `register_tools_get_by_id()` у `proxy.py` — див. історію проходу 5 нижче.

**Залишок (й далі свідомо кастомне):** `jobs_create`/`plans_create`/`*_approve`/
`*_deny`/`*_execute`/`projects_get` (інша auth-модель — proxy до memory, `int`-параметр)
мають по-різну сигнатуру виклику tools (різна кількість аргументів, dispatch за
`job_type`) — форсувати їх у generic helper дало б більше складності (нові опції/гілки
в `proxy.py`), ніж користі. Інші 14 модулів (`auth`, `improve`,
`logs`, `memory`, `models`, `overview`, `projects`, `router`, `settings_api`, `users`,
`workbench`, `__init__`) мають по суті унікальну логіку (streaming, агрегація, custom auth) —
залишаються кастомними обґрунтовано.
**DoD:** ✅ виконано — boilerplate усунуто там, де шаблон 1:1 збігався; решта задокументована
як "навмисно кастомне".

### D. Phase 7 — відкриті пункти (з PLATFORM_ROADMAP.md)
| # | Пункт | Пропозиція |
|---|-------|------------|
| 7.3 | Domain LoRA swap (MoE-стиль) | Потребує 2+ LoRA в registry — заблоковано на Critical Path фази 3 (перший реальний training run). Не форсувати — YAGNI поки немає й однієї продакшн LoRA. |
| 7.4 | llama.cpp benchmark vs Ollama/Vulkan | Дешевий експеримент (E1 з ROADMAP.md) — підняти `llama-server` поряд, прогнати ті самі промпти, виміряти tok/s. ~2 год роботи, дає дані для рішення "чи варто мігрувати". |
| 7.5 | WireGuard замість cloudflared | Потрібен лише коли Edge (фаза 4) використовується "з будь-якої точки" — зараз Edge offline/LAN покриває основний сценарій. Відкласти до реального запиту на віддалений доступ. |

### E. C3 live Telegram smoke — закрити останній пункт фази 1-2
**Спостереження:** `PLATFORM_ROADMAP.md` фаза 1-2 (~92%) має один відкритий чекбокс:
"C3 live TG smoke (API smoke ✅, live Telegram ще не перевірено)". Це остання дрібниця
до 100% по фазі, яка вже фактично "завершена". Ручна перевірка ~10 хв: відкрити Telegram,
прогнати `cursor:`, `take_note`, `reminder`, `image gen` командами на реальному боті.
**DoD:** чекбокс [x], запис у ROADMAP.md з датою.

### F. Named tunnel лише для `/app` (opt-in)
**Спостереження:** другий відкритий пункт фази 1-2 — "Named tunnel лише для `/app`
(opt-in Cloudflare, бот лишається на polling)". Низький пріоритет (UX-покращення для
доступу до Mini App ззовні LAN), не блокер. Можна лишити в backlog без дій, поки немає
конкретного запиту "хочу відкрити /app з телефону поза домашньою мережею".

### G. Великий некомічений WIP (151 файлів) — ризик дрейфу · ✅ закрито (PR #6, 2026-06-07)
**Було:** робоче дерево на `main` мало 151+ змінених/нових файлів (платформа P0-P12 +
Alembic + routes/toolkit рефактор), усе протестовано й mypy-чисто, але незакомічене —
ризик дрейфу/конфліктів зростав з кожним проходом цього циклу (151 → 165 → 183 → 226).
**Як закрито:** на запит користувача через `/create-pr` виник конфлікт area: 226 файлів
(WIP + edits проходів 26-28) технічно не розділялись на "лише сесійні зміни" без
розпотрошення цілого рефактору (нові файли типу `_helpers.py`/`plans.py` були ОДНОЧАСНО
і частиною WIP, і відредаговані в цій сесії). Через `AskUserQuestion` користувач
ОБРАВ "Закомітити все одним PR" замість раніше задокументованого фазованого плану —
свідома відмова від обережності на користь швидкого landing. Створено гілку
`feat/platform-p0-p12-and-refactor`, закомічено 226 файлів (14567 insertions, 2311
deletions), відкрито **PR #6** (https://github.com/gregnevm/JARVIS/pull/6),
усі 7 CI-перевірок ✅ green, `mergeable: MERGEABLE`. Очікує рішення користувача про merge.
**Урок:** план "комітити фазами" був правильним, ПОКИ обсяг лишався малим — але WIP
ріс швидше, ніж цикл встигав його розділити (рефактор проходів 27-28 сам додавав нові
файли в ту саму незакомічену купу). Коли розділення стало технічно неможливим без
розпотрошення робочого коду — правильний хід був ескалювати рішення користувачу
(`AskUserQuestion`), а не продовжувати відкладати чи форсувати власний план.

### H. Архітектурний дрейф: `jarvis_core/` створено, але агент-луп його обходить · ✅ R1–R5 виконано (2026-06-16)
**Чому пропозиція виникла:** запит "проаналізуй архітектуру та запропонуй рефактор".
Повний обхід `tools/app/agent.py` (907 рядків), `gateway/app/tools_client.py` (873),
`gateway/app/router.py` (608), `jarvis_core/*` та config/auth усіх 6 сервісів. Архітектура
**здорова за наміром** (статут `AGENTS.md`, модульний моноліт, композиція роутерів,
per-service `app`-пакети, strict mypy + ізольований CI-matrix) — проблема не в дизайні,
а в **дрейфі реалізації від задуму**: спільний «мозок» `jarvis_core/` створено, але код
навколо нього його обходить і паралельно дублює. Три кореневі знахідки:

**H1 — `jarvis_core/` існує, але агент-луп його не використовує (найвищий пріоритет).**
`facade.JARVIS` (`jarvis_core/facade/jarvis.py`, 54 рядки) + `pipeline/*` задумані як єдина
точка входу (DESIGN §5.2), але `AgentRunner.run()` дублює їхню логіку, а `llm.decorators/
adapters/interface` мають **0 використань** з `agent.py`.
- **Tool-loop повторено 3× дослівно**: `_agent()` (`agent.py:607-643`), `_agent_events()`
  (`:529-571`), `_fix_round_edit()` (`:835-848`) — однакова петля `chat → parse tool_calls →
  dispatch → append`. Зміна в одній копії не дзеркалиться в інших → клас багів розсинхрону.
- **Streaming обходить pipeline**: `tools/app/routes/agent.py` для чату йде через `jarvis.chat()`
  → pipeline, а для стріму кличе `agent.run_stream()` **напряму**. Pipeline неповний (немає
  streaming-handler), тож `facade`/`pipeline` — фактично мертва обгортка над `AgentRunner`.
- `decide_mode()` (`agent.py:265-286`) лише обгортає `jarvis_core.routing.classify_mode` —
  зайвий шар.

**H2 — `ToolsClient` (873 рядки) — божественний об'єкт.** `gateway/app/tools_client.py`
поєднує 4 незв'язані домени в одному класі: базовий агент (stream/process), Computer Use
(~15 методів), Jobs/Plans/Tasks (~17), Orchestration (research/cursor/mcp/skills/subagents/
teams/improve, ~20). Будь-яка нова фіча tools роздуває цей файл. Уже зафіксовано в проході 33
("tools_request — єдина точка входу ~30 методів, 0 тестів") — але без розбиття за доменами.

**H3 — дублювання, яке мало б жити в `jarvis_core/`.**
- **Парсинг ID з env**: `jarvis_core/auth_ids.py:parse_comma_separated_ids()` **існує**, але
  `gateway/app/config.py:117-161` тричі вручну робить `split(",")→set[int]`
  (`allowed_ids`/`health_alert_ids`/`admin_ids`), а `tools/app/config.py` не має properties
  взагалі. 11 полів конфігу дубльовано між gateway і tools.
- **`SettingsConfigDict(...)`** скопійовано в усіх 6 сервісах → напрошується `BaseServiceSettings`.
- **Intent-детекція протекла в транспорт**: `gateway/app/router.py:54` має власний
  `_SCREENSHOT_RE`, хоча `jarvis_core/routing/cascade.py:_COMPUTER_RE` уже покриває цей намір —
  порушує принцип S3 (канал ≠ мозок).
- **`router.handle_update()` (`router.py`, ~197 рядків)** змішує парсинг Telegram-JSON з
  авторизацією/rate-limit/маршрутизацією.
- Каркас tenant-context (`jarvis_core/context.py`: `RequestContext`, `redis_key()`,
  `to_headers()`) **вже є** (добре), але PR#4 — читання `X-JARVIS-*` у tools/memory — не
  завершено, тож context поки тупиковий.

**Запропонований рефактор (фазами, без зміни поведінки; узгоджено зі статутом P4/P7/S3
і забороною LangGraph/Celery — усе лишається в наявному async-стеку):**

| # | Зміна | Ефект |
|---|-------|-------|
| R1 ✅ | Витягти єдиний `ToolLoop` у `jarvis_core/`; три копії в `agent.py` стають варіантами (sync/stream/fix) над ним | **зроблено (2026-06-16):** `jarvis_core/agent/tool_loop.py` — одна петля; `_agent`/`_agent_events`/`_fix_round_edit` тепер тонкі споживачі `run_tool_loop`. Поведінка незмінна (всі agent-тести green), tool-loop single-sourced; 10 нових юніт-тестів engine на mocked-backend |
| R2 ✅ | Додати streaming через facade, щоб `run_stream` теж ішов через `JARVIS`, а не повз нього | **зроблено (2026-06-16):** `JARVIS.chat_stream()` — єдина точка входу для стріму, safety-скрин спільний із `SafetyHandler` (`screen_text`); `routes/agent.py:/agent/stream` тепер кличе facade, а не `agent.run_stream` напряму. Маршрутизація лишається в `run_stream` (поведінка незмінна). Повний CoR-стрім (Handler→async-gen) свідомо відкладено (YAGNI). 5 нових тестів facade |
| R3 ✅ | Розбити `ToolsClient` на 4 доменні mixin-и (`Agent`/`Computer`/`Jobs`/`Orchestrator`) зі спільною базою; `ToolsClient` лишається тонким агрегатором | **зроблено (2026-06-16):** `tools_client.py` 873→~30 рядків (агрегатор); HTTP-плумбінг у `tools_client_base.ToolsClientBase`; методи у `tools_client_{agent,computer,jobs,orchestrator}.py`. Публічний API (усі методи + `extract_text`/`FALLBACK`) незмінний — call-sites не чіпались. Контракт-тест навчено читати всі split-файли; усі 268 gateway-тестів green |
| R4 ✅ | Замінити ручний парсинг у `gateway/app/config.py` на `parse_comma_separated_ids`; винести `_SCREENSHOT_RE` з транспорту в `jarvis_core/routing` | **зроблено (2026-06-16):** 3 копії split-loop у `gateway/app/config.py` → `parse_comma_separated_ids`; `is_screenshot_request()` тепер у `jarvis_core/routing/cascade.py` (S3: intent-патерн поза транспортом), gateway імпортує. `tools/config` properties — пропущено (tools уже резолвить ID через helper, YAGNI). `BaseServiceSettings` — свідомо НЕ роблено: додало б pydantic у `jarvis_core` і зламало б «core dependency-light» заради 1-рядкового `SettingsConfigDict` (P6). 5 нових тестів; mypy strict |
| R5 ✅ | `classify_update(raw) → (kind, data)` + dispatch; `handle_update` стає тонким диспетчером, message-логіка — в `_handle_message` | **зроблено (2026-06-16):** транспортна класифікація відділена від обробки; `handle_update` 196→~20 рядків (диспетч), решта в `_handle_message`. Поведінка незмінна (всі 17 router-тестів green), `classify_update` чистий і покритий окремо (2 тести) |

**Пріоритет:** R1 (найвищий ROI — три копії в критичному шляху) → R2 → R4 → R3 → R5.
**DoD:** кожна фаза — окремий PR, рефактор без зміни поведінки, `mypy` strict + `pytest`
по відповідних сервісах green, нові юніт-тести на витягнуту логіку (`ToolLoop`, parser).
**Статус:** ✅ **усі фази виконано (2026-06-16).** R1 (єдиний tool-loop) · R2 (стрім через
facade) · R3 (ToolsClient → доменні mixin-и) · R4 (config/intent у `jarvis_core`) ·
R5 (транспорт↔логіка в gateway-router). Усе без зміни поведінки, mypy strict + тести green
посервісно. `BaseServiceSettings` свідомо НЕ робили (тримаємо `jarvis_core` dependency-light).

---

## Закриті пропозиції (історія)

### Прохід 2026-06-07 (тридцять четвертий) — test_redis_util.py: канонічний get_redis() (ціль консолідації проходу 28) сам без тесту
- **Контекст:** переніс "module-vs-test-list" пошук (проходи 30-33,
  завершені для `gateway/app`) на `tools/app`. Непокриті кандидати:
  `bootstrap`, `config`, `image_gen_lock` (вже непрямо), `redis_store`
  (непрямо), **`redis_util`**, `schemas` (непрямо). `bootstrap.py`
  переважно app-wiring (`build_jarvis` створює реальні LLM-стеки — погано
  тестувати ізольовано); `redis_util` — найцікавіше.
- **Іронічна знахідка:** `redis_util.get_redis()`/`aclose_redis()` —
  САМЕ ТОЙ канонічний lazy-singleton, до якого проход 28 звів 8 копій
  дубльованого коду по `tools/app`. Від його lazy-create/cache/reset-
  контракту тепер залежать `bg_jobs`, `metrics`, `confirm`, `reminders`,
  `computer_{rate_limit,trust,confirm}`, `jobs`, `tasks`, `artifacts`,
  `image_gen_lock` — а сам модуль не мав ЖОДНОГО прямого тесту. Усі 9
  тестових файлів роблять `monkeypatch.setattr(<module>, "get_redis",
  lambda: fake)` — що ПОВНІСТЮ обминає реальну singleton-логіку
  (підміняє саму функцію, а не перевіряє її поведінку).
- **Що покрив:** (1) lazy-створення — `aioredis.from_url` НЕ
  викликається до першого `get_redis()`, викликається з правильним
  `settings.redis_url`+`decode_responses=True`; (2) кешування — 3
  послідовні виклики повертають ОДИН і той самий інстанс (singleton, не
  factory); (3) `aclose_redis` закриває клієнт І скидає `_redis` у `None`,
  тож наступний `get_redis()` створює СВІЖИЙ інстанс (а не повертає
  закритий!); (4) `aclose_redis` на ще-не-створеному клієнті — no-op, не
  падає і не створює зайвий інстанс.
- **Виправлення:** `tools/tests/test_redis_util.py` (4 тести,
  `_FakeAsyncRedis` сентинел + `monkeypatch` на `aioredis.from_url`,
  autouse-фікстура скидає глобальний `_redis` між тестами для ізоляції).
- **Верифікація:** `test_redis_util.py` ✅ 4/4 з першого запуску; `mypy
  tools/app` ✅ 77 файлів; повний `pytest tools/tests` ✅ без падінь
  (224 = 220 + 4 нових).
- **Урок:** "ціль консолідації" — не синонім "перевірений код". Коли N
  копій звели до 1 спільного хелпера, саме ця 1 точка тепер несе весь
  ризик регресії для N викликачів — а якщо викликачі тестуються через
  DI-підміну (що правильно для ІЗОЛЯЦІЇ їхньої логіки від Redis), нічого
  не лишає прямого тесту для самого хелпера. Варто прямо запитати:
  "чи хтось взагалі тестує ЦЮ функцію, а не підміняє її?"

### Прохід 2026-06-08 (тридцять сьомий) — test_main_routes.py: route-шар memory/app/main.py (17 ендпоінтів, 0 ASGI-тестів)
- **Контекст:** перевірив `tools_client.py` як можливу ціль "сусіднього
  патерну" (45 `except httpx.HTTPError` сайтів) — але це виявилось
  УЖЕ узгодженою практикою (45 толерантних fallback'ів + 2 логованих для
  критичних шляхів `/agent` і reminders-ics; не інконсистентність, а
  свідомий вибір "тихий fallback за замовчуванням, лог — для важливого").
  Переключився на "module-vs-test-list" по інших сервісах (twin/memory/
  hostagent) — у memory лишались непокритими тільки `__init__`/`main`
  (типово). Але перевірка показала: у `memory/tests/*.py` (6 файлів,
  раніше 17 тестів) — ЖОДЕН не використовує `TestClient`/`AsyncClient`/
  `httpx` і не імпортує `app.main`. Увесь route-шар (259 рядків, ~17
  ендпоінтів: embed/store/search/history/sessions + повний projects CRUD
  + project files) тестувався ЛИШЕ опосередковано через DB/RAG-юніти —
  валідація запитів, 404-guard'и, обрізання полів і толерантна-до-
  часткових-помилок логіка `/store` не мали жодного прямого тесту.
- **Технічний виклик:** `lifespan` створює РЕАЛЬНИЙ `DB(settings.dsn)` +
  Redis-конект — `TestClient(app)` як контекстний менеджер це запустив
  би. Розв'язання: підмінити `app.state.db`/`app.state.embedder` НАПРЯМУ
  одразу після імпорту `app` (без `with TestClient`), і ходити через
  `httpx.ASGITransport` — він НЕ викликає lifespan-події, лише ASGI
  http-scope (аналог `httpx.MockTransport` із проходів 32-33, але для
  ASGI-застосунку, а не зовнішнього HTTP-клієнта). Новий патерн для
  кодової бази — задокументований у docstring файлу.
- **Що покрив:** (1) `/health` — ok/degraded/`schema_warn` через
  `embed_dim_mismatch` (із fake `db.pool.acquire()` за зразком
  `test_sessions.py`); (2) `_embed_or_502` — 200 з dim+embedding, 502
  з detail на помилці ембедера (`/embed`, `/search`); (3) `/store` —
  створення сесії vs використання заданого `session_id`, і ГОЛОВНЕ:
  задокументований у самому хелпері контраст — `/store` ПРОДОВЖУЄ при
  падінні ембедингу одного chunk'а (`continue`+log), а `/embed`/`/search`
  фейляться повністю (502) — тест з 2-чанковим текстом і
  `side_effect=[RuntimeError, vec]` підтверджує `chunks_stored == 1`;
  (4) `/history`/`/sessions` — дефолтний ліміт із `settings`, clamp
  `[1, 30]`; (5) повний `/projects` CRUD — 400 на порожнє ім'я, обрізання
  `name[:200]`/`system_prompt[:8000]`, 404 через `get_project is None`/
  `update_project is None`/`delete_project is False`, `include_content`
  прапорець, `PATCH` передає `None` для невказаних полів; (6) `_require_
  project` — 404 на всіх трьох project-files ендпоінтах ДО виклику
  DB-методу запису (перевірено через `assert_not_awaited`).
- **Виправлення:** `memory/tests/test_main_routes.py` (29 тестів,
  `FakeDB`/`FakeEmbedder` з per-method `AsyncMock`, `_FakePool/_FakeAcquire/
  _FakeCon` сентинели для `db.pool.acquire()` за зразком `test_sessions.py`).
- **Верифікація:** 29/29 з першого запуску; `mypy memory/app` ✅ 6 файлів,
  0 помилок; повний `pytest memory/tests` ✅ 46/46 (17 існуючих + 29 нових),
  без падінь.
- **Урок:** "module-vs-test-list" пошук по basenames (`app/*.py` vs
  `tests/test_*.py`) ловить відсутність ПРЯМОГО тесту МОДУЛЯ, але не
  ловить відсутність тесту ШАРУ — `main.py` мав "індиректне" покриття за
  назвою (бо `test_db.py`/`test_rag.py` фактично покривали залежності, що
  `main.py` імпортує), та насправді сам ASGI-роутинг/валідація/HTTP-
  контракт не торкались жодним тестом. Вартий запит: "чи хоч один тест
  ходить ЧЕРЕЗ HTTP-шар цього сервісу, а не напряму в обхід нього?"

### Прохід 2026-06-08 (тридцять шостий) — access.py: silent except → logger.warning (узгодження з сусіднім патерном у тому ж файлі)
- **Контекст:** після завершення серії тестового покриття (проходи 30-34,
  +48 нових тестів) і чистки застарілої пропозиції G (прохід 35) шукав
  наступну ціль через "очищуй"/"перевіряй архітектуру". Перевірив
  bare-except без анотацій, мутабельні дефолти, SQL-ін'єкції, subprocess
  без list-форми аргументів — нічого не знайшов (усе вже виправлено в
  попередніх проходах). Написав кастомний скрипт `/tmp/silent_except.py`
  для пошуку `except ...: pass` патернів по всіх 5 сервісах — знайшов 11
  кандидатів.
- **Знахідка:** з 11 кандидатів обрав `gateway/app/bot/access.py` (рядки
  ~214 і ~243) — два блоки `except Exception: pass` у потоках `/deny` і
  `/revoke` (сповіщення користувача про відмову/відкликання доступу), що
  МОВЧКИ ковтали помилки (типово: користувач заблокував бота). Вибрав
  саме ці — НЕ через найбільший fan-in чи складність, а через
  **внутрішньофайлову несумісність патернів**: цей самий файл уже має
  встановлений сусідній патерн (рядок ~60-61, `notify_admins_new_request`):
  `except Exception as exc:  # noqa: BLE001 — один адмін не блокує інших`
  + `logger.warning("notify admin %s failed: %s", admin_id, exc)`. А також
  `_notify_user_granted` (рядок ~115) логує так само. Два мовчазні блоки
  лишались єдиними винятками з уже усталеної в ЦЬОМУ Ж файлі практики —
  чиста несумісність "сусідніх патернів", що ускладнює діагностику
  (неможливо побачити в логах, чи `/deny`/`/revoke` сповіщення взагалі
  спрацьовують).
- **Виправлення:** обидва блоки переписані за зразком сусіднього патерну
  (без зміни поведінки — той самий `except Exception`, той самий
  "не зривати адмін-флоу"):
  ```python
  # /deny (було: except Exception: pass)
  except Exception as exc:  # noqa: BLE001 — користувач міг заблокувати бота, не зривати адмін-флоу
      logger.warning("notify denied user %s failed: %s", target_id, exc)

  # /revoke (було: except Exception: pass)
  except Exception as exc:  # noqa: BLE001 — користувач міг заблокувати бота, не зривати адмін-флоу
      logger.warning("notify revoked user %s failed: %s", target_id, exc)
  ```
  `logger = logging.getLogger("jarvis.gateway.access")` уже існував у файлі —
  новий імпорт не знадобився.
- **Верифікація:** `mypy gateway/app` ✅ 71 файл, 0 помилок; цільовий
  `pytest gateway/tests -k "access or admin"` ✅ 27/27; повний
  `pytest gateway/tests -q` ✅ 266/266, exit code 0 — без регресій.
- **Урок:** "узгодженість сусідніх патернів" (sibling-pattern consistency)
  — самостійний клас знахідок, відмінний від "є якийсь гап". Коли в
  ОДНОМУ файлі співіснують і анотований `except ... as exc: # noqa: BLE001
  + logger.warning(...)`, і голий `except: pass` для структурно
  ідентичних випадків ("сповістити когось, не зривати флоу") — це сигнал,
  що другий писався раніше або іншою рукою і просто не підтягнувся до
  усталеної практики. Виправлення тривіальне (чиста косметика логування,
  поведінка та сама), а виграш для діагностики — конкретний: тепер видно
  в логах WARNING, коли сповіщення користувача провалюється, замість
  тихого "нічого не сталося".

### Прохід 2026-06-07 (тридцять третій) — test_tools_client_http.py: tools_request — єдина точка входу ToolsClient (~30 методів), 0 тестів
- **Контекст:** завершив "module-vs-test-list" серію (проходи 30-32) у
  `gateway/app`. Останні непокриті кандидати: `tools_client_http`,
  `tts_client`, `whisper`. Обрав `tools_client_http::tools_request` —
  не за розміром (39 рядків, одна функція), а за топологією: це ЄДИНА
  точка входу, через яку `ToolsClient._request` (а отже й УСІ ~30 методів
  `ToolsClient` — `process`, `create_plan`, `list_plans`, `dashboard`,
  `set_mode`, …) проходять кожен HTTP-запит до tools-сервісу. `tts_client`/
  `whisper` — листові, самодостатні обгортки з fan-in=1; регресія в
  `tools_request` натомість тихо ламає весь gateway↔tools трафік одразу.
- **Що покрив:** умовну побудову kwargs — `json`/`params`/`timeout`
  додаються в `kwargs` ТІЛЬКИ якщо не `None` (а не передаються як
  буквальний `None`, що для деяких httpx-шляхів важливо: порожнє тіло
  запиту `b""` замість `b"null"`); нормалізацію URL (`base.rstrip("/")`+
  `path`); приведення методу до верхнього регістру; толерантний `None`-
  фолбек на `httpx.HTTPError` (мережева помилка, НЕ HTTP-статус); та
  явний контракт "не викликає `raise_for_status` — повертає Response
  навіть для 404, рішення про статус — за викликачем" (легко зламати
  при рефакторингу, додавши `raise_for_status` "про всяк випадок").
- **Виправлення:** додав `gateway/tests/test_tools_client_http.py`
  (8 тестів) через `httpx.MockTransport` (той самий патерн проходів
  31-32). Регресійний тест `test_omits_json_when_none` явно фіксує, що
  тіло запиту порожнє (`b""`), а НЕ `b"null"` — найтонший і найлегше
  ламаний нюанс цієї функції.
- **Верифікація:** `test_tools_client_http.py` ✅ 8/8 з першого запуску;
  `mypy gateway/app` ✅ 71 файл; повний `pytest gateway/tests` ✅ без
  падінь (264 = 256 + 8 нових).
- **Підсумок серії 30-33:** +44 нові юніт-тести (7+15+14+8) для 4 активних
  модулів з нульовим/непрямим покриттям (`thread_context`, `_helpers`,
  `services`, `tools_client_http`). Лишились непокриті лише
  `tts_client`/`whisper` — обидва тонкі листові обгортки з fan-in=1 і
  однією гілкою (запит → толерантний фолбек), де ROI прямого тесту
  низький; "module-vs-test-list" напрямок вичерпано для цих 5 модулів.

### Прохід 2026-06-07 (тридцять другий) — test_services.py: ServicesClient (ретраї, ланцюжок deploy, вилучення detail) — 0 тестів
- **Контекст:** продовжив "module-vs-test-list" пошук (проходи 30-31) у
  `gateway/app`. З решти кандидатів без ЖОДНОГО (ні прямого, ні непрямого)
  покриття — `services`, `tools_client_http`, `tts_client`, `whisper` —
  обрав `services.py::ServicesClient` як найскладніший і найвпливовіший
  (fan-in 11 файлів: `bot/*`, `platform/{models,overview,settings_api}`,
  `admin_panel`, `health_watch`, `main`, `router`).
- **Чому саме він:** на відміну від `tts_client`/`whisper`/
  `tools_client_http` (прості "запит → толерантний фолбек на помилку"),
  `ServicesClient` має ТРИ шари нетривіальної логіки: (1) `dashboard()` —
  ретраї до 3 спроб з `debug`-логуванням проміжних і `error` фінальної
  невдачі; (2) `tools_deploy_lora()` — вкладене вилучення `detail` з
  помилки: спершу пробує `exc.response.json().get("detail", ...)`, при
  `ValueError` падає на `exc.response.text[:200]`; (3)
  `twin_promote_lora`/`twin_rollback_lora` — успіх ланцюжком викликає
  `tools_deploy_lora()` і докладає `out["ollama"]`, АЛЕ тільки якщо
  `deploy=True` І promote/rollback сам не впав з помилкою.
- **Виправлення:** додав `gateway/tests/test_services.py` (14 тестів) —
  через `httpx.MockTransport` (встановлений патерн з `test_tools_client.py`,
  підміна `._client`/`._dash_client`). Покрив: ретраї `dashboard` (рівно 3
  спроби — лічильник у handler-і фіксує точну межу, не "хоча б 1"), усі три
  гілки вилучення `detail` (success/JSON-detail/text-фолбек при не-JSON
  тілі), і ланцюжок `promote/rollback→deploy` у ВСІХ комбінаціях
  (`deploy=True` успіх / `deploy=False` пропуск / помилка-перериває-
  ланцюжок — лічильник підтверджує, що `deploy` НЕ викликається після
  невдалого promote).
- **Верифікація:** `test_services.py` ✅ 14/14 (з першого запуску, без
  ітерацій на форматі MockTransport-handler-ів); `mypy gateway/app` ✅ 71
  файл; повний `pytest gateway/tests` ✅ без падінь (256 = 242 + 14 нових).
- **Урок:** при виборі З КІЛЬКОХ непокритих кандидатів — пріоритизуй за
  складністю логіки, а не лише за fan-in: `tts_client`/`whisper` мають
  схожий fan-in, але є тонкими "проксі+толерантний фолбек" обгортками з
  однією гілкою; `ServicesClient` — єдиний з трьома шарами розгалуженої логіки
  (ретраї, вкладене вилучення помилки, умовний ланцюжок викликів), де
  регресіятихо зламала б дашборд/promote-flow без жодного сигналу.

### Прохід 2026-06-07 (тридцять перший) — test_helpers.py: прямі юніт-тести для _helpers.py (15 імпортерів, 0 прямих тестів)
- **Контекст:** продовжив підхід проходу 30 (звірка модулів проти
  тестів), цього разу для `gateway/app`. Кандидати без `test_<module>.py`:
  `_helpers`, `agent_turn`, `projects`, `services`, `tools_client_http`,
  `tts_client`, `whisper`, `request_id`, `main`. Греп підтвердив непряме
  покриття для `agent_turn`/`projects`/`request_id`. Лишились без жодної
  прямої ЧИ непрямої згадки в тестах: `_helpers`, `services`,
  `tools_client_http`, `tts_client`, `whisper`.
- **Чому саме `_helpers`:** найвищий "блаcт-радіус" — імпортується у
  **15 файлах** (`platform/{jobs,plans,memory,models,settings_api,
  workbench}.py`, `bot/{access,admin,commands,computer,quick_actions,
  remote}.py`, `admin_panel.py`, `webapp.py`, `webapp_ps.py`) і є
  узагальненням консолідацій з проходів 21-27 (`require_text`,
  `require_mode`+`AGENT_MODES`, `require_found`). Кожна функція має
  нетривіальні крайові випадки: `require_text` — strip+порожній рядок vs
  None vs кастомне ім'я поля у `detail`; `require_mode` — нормалізація
  регістру/пробілів ДО звірки (саме це проход 27 виправив для
  `webapp.py::app_set_mode`!) + кастомна множина + кастомне ім'я поля;
  `require_found` — generic `TypeVar`, falsy-але-не-None значення (`0`,
  `""`, `[]`) НЕ мають трактуватись як "не знайдено". Жоден з цих нюансів
  не мав ПРЯМОГО тесту — лише випадкове непряме покриття там, де route-тест
  трапляється проходити через конкретну гілку.
- **Виправлення:** додав `gateway/tests/test_helpers.py` (15 тестів) —
  прямі юніт-тести без FastAPI-додатку (виклик функцій напряму +
  `pytest.raises(HTTPException)` за зразком `test_telegram_webapp_auth.py`).
  Покрив усі три хелпери + канонічність `AGENT_MODES`, включно з
  регресійним тестом саме на той нюанс нормалізації, що проход 27 виправив
  у `app_set_mode` (`require_mode("  Agent ", ...) == "agent"`), і на
  falsy-значення в `require_found` (типова пастка "не None" vs "не falsy").
- **Верифікація:** `test_helpers.py` ✅ 15/15; `mypy gateway/app` ✅ 71
  файл; повний `pytest gateway/tests` ✅ без падінь (242 = 227 + 15 нових).
- **Урок (продовження проходу 30):** хелпер-модулі з високим fan-in —
  пріоритетні кандидати для прямих юніт-тестів: вони консолідують поведінку
  багатьох місць виклику в ОДНУ точку, тож регресія там б'є по всіх 15
  імпортерах одразу, а пряма (а не випадково-непряма) перевірка нюансів
  (нормалізація, falsy-vs-None, custom field) дешевша й надійніша за
  сподівання, що десь серед route-тестів трапиться потрібна гілка.

### Прохід 2026-06-07 (тридцятий) — test_thread_context.py: 0% покриття для активного модуля C0-контексту
- **Контекст:** змінив тип пошуку — після вичерпання guard-дублів (21-27),
  Redis-singleton кластера (28) і внутрішньофайлового httpx-дублю (29)
  пошукав репетативні чанки в `twin/memory/hostagent` (нічого вартого —
  лише тривіальний `logging.basicConfig(...)`, ідентичний у трьох
  незалежно деплойованих `main.py`, що НЕ варто виносити у спільну
  бібліотеку). Перейшов на пошук прогалин у тестовому покритті: звірив
  список модулів `tools/app/*.py` зі списком `test_*.py` у `tools/tests/`.
  Кандидати без прямого `test_<module>.py`: `redis_util`, `thread_context`,
  `runtime`, `image_gen_lock`, `computer_audit`, `tasks` — більшість мають
  непряме покриття через інші тести (греп підтвердив). Та
  `thread_context.py` мав **0 згадок** у будь-якому тестовому файлі.
- **Чому це важливо:** `build_thread_context()` — не тривіальний форматер:
  тегує ролі (`user`→`U`, `assistant`→`A`, інше→перша літера), обрізає
  кожне повідомлення до `_MAX_MSG=280`, зупиняється за сумарним бюджетом
  `_MAX_TOTAL=2000`, пропускає порожні репліки після `strip()`. Активно
  використовується в `agent.py::_build_messages` (C0 chat-контекст —
  гарячий шлях кожного запиту), тож регресія тут тихо псує контекст для
  LLM без жодного тесту, що впіймав би це.
- **Виправлення:** додав `tools/tests/test_thread_context.py` (7 тестів,
  `FakeMemory` за зразком `test_agent.py::FakeMemory`) — покрив: порожню
  історію, тегування ролей (включно з невідомою роллю), пропуск
  порожніх/whitespace-реплік + `\n`→` `, обрізання за `_MAX_MSG`,
  зупинку за `_MAX_TOTAL`, та повагу до аргументу `limit`.
- **Верифікація:** `pytest tools/tests/test_thread_context.py` ✅ 7/7;
  `mypy tools/app` ✅ 77 файлів (тести в проєкті типізуються НЕ суворо —
  звірив з конвенцією `test_agent.py::FakeMemory`, що так само не
  узгоджується з `MemoryClient` за прямим типом); повний `pytest
  tools/tests` ✅ без падінь.
- **Урок:** "перевір список тестів проти списку модулів" — дешевий і
  швидкий спосіб знайти прогалини покриття, який не вимагає coverage-
  тулінгу; знаходить саме "активний код без тестів", а не "мертвий код
  без тестів" (що було б марною роботою).

### Прохід 2026-06-07 (двадцять дев'ятий) — _post_memory: внутрішньофайловий дубль httpx-проксі в memory.py
- **Контекст:** скрипт детекції повторюваних 5-рядкових чанків (запущений
  на проході 28) повернув ОДНОГО нового кандидата — `auth: PlatformAuth =
  Depends(require_platform_auth), user_id, limit=20, uid = resolve_uid(...)`,
  що зустрічається 3× у `gateway/app/platform/{memory.py,proxy.py}`.
  Перевірив гіпотезу "чи можна `memory_notes`/`memory_history`/
  `memory_profile` переписати через `register_tools_list`" — **ні**:
  `register_tools_list` проксіює виключно до generic `request.app.state.
  tools.<attr>(uid, limit)` і повертає фіксовану форму `{wrap_key: items,
  "user_id": uid}`. А `memory_notes`/`memory_profile` читають напряму з
  файлової системи (`data/{notes,profiles}/{id}.{jsonl,json}`),
  `memory_history` робить прямий `httpx`-запит до ОКРЕМОГО `memory`-сервісу
  (не до `tools`), і всі три повертають структурно різні форми відповіді
  (`{"notes": [...]}`, `{"messages": [...]}`, `{"profile": ..., "exists":
  ...}`). Це підтверджує висновок Пропозиції B: "different call signature
  to tools... форсувати у generic helper дало б більше складності, ніж
  користі" — НЕ нова знахідка, а та сама вже задокументована межа.
- **Та поки читав файл — знайшов СПРАВЖНІЙ внутрішньофайловий дубль**:
  `memory_search` (рядки ~51-67) та `memory_history` (рядки ~109-119) мали
  побайтово ідентичний (з різним лише endpoint/payload) 7-рядковий блок
  `async with httpx.AsyncClient(timeout=12.0) as cli: r = await cli.post(
  f"{settings.memory_url.rstrip('/')}/{endpoint}", json=payload);
  r.raise_for_status(); data = r.json()`, обгорнутий у
  `try/except httpx.HTTPError`.
- **Виправлення:** виніс спільну частину (запит+парсинг, БЕЗ except — у
  кожного виклику різна форма fallback-відповіді/ключів, тож except
  лишився на місці) у приватний хелпер `_post_memory(endpoint, payload) ->
  Any`, що кидає `httpx.HTTPError` назовні. `memory_search`/`memory_history`
  тепер викликають `data = await _post_memory("search"|"history", payload)`
  всередині свого `try`. Скоротив 14 рядків дублю до 2 викликів + 1 хелпер
  з докстрінгом, що пояснює, чому except НЕ узагальнено.
- **Урок:** негативний результат перевірки гіпотези (не консолідовувати
  через generic proxy-helper) не означає "файл чистий" — варто прочитати
  файл ПОВНІСТЮ під час перевірки гіпотези, а не лише ділянки навколо
  кандидата. Справжній дубль знайшовся не в тому місці, де його шукали.
- **Верифікація:** `mypy gateway/app` ✅ 71 файл; `pytest gateway/tests -k
  memory` ✅ 6/6; повний `pytest gateway/tests` ✅ (без падінь).

### Прохід 2026-06-07 (двадцять восьмий) — Redis-singleton: 8 копій замість спільного get_redis()
- **Контекст:** змінив тип пошуку — замість guard-блоків (вичерпано на
  проходах 21-27) шукав репетативні 4-рядкові чанки коду по
  `gateway/app`+`tools/app`+`memory/app`. Знайшов кластер: 8-9 файлів
  `tools/app/{reminders,computer_rate_limit,image_gen_lock,computer_trust,
  jobs,redis_util,tasks,artifacts,computer_confirm}.py` мали майже
  ідентичний 6-рядковий блок lazy-singleton:
  ```python
  _redis: aioredis.Redis | None = None
  def _client() -> aioredis.Redis:
      global _redis
      if _redis is None:
          _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
      return _redis
  ```
- **Знахідка-мірроргеп:** у `tools/app/redis_util.py` ВЖЕ існував канонічний
  `get_redis()`/`aclose_redis()` з докстрінгом "Спільний Redis-клієнт для
  tools (metrics, confirm, reminders…)" — і `bg_jobs`/`metrics`/`projects`/
  `redis_store`/`skills` справді його імпортували. Та САМЕ `confirm` і
  `reminders` (названі в докстрінзі!) мали власні копії — докстрінг описував
  бажану архітектуру, а не реальну. Ще 6 файлів (`computer_rate_limit`,
  `image_gen_lock`, `computer_trust`, `jobs`, `tasks`, `artifacts`) теж
  дублювали той самий патерн. Додатково 3 файли (`reminders`, `artifacts`,
  `computer_confirm`) мали власні мертві `aclose`/`aclose_redis` — copy-paste
  `redis_util.aclose_redis`, який сам ніким не викликається (lifespan
  `tools/app/main.py` його не використовує).
- **Виправлено:** у всіх 8 файлах замінив локальний singleton на
  `from .redis_util import get_redis` + `get_redis()` замість `_client()`;
  прибрав мертві `aclose`/`aclose_redis` (3 копії) і тепер-зайві імпорти
  `redis.asyncio as aioredis`/`from .config import settings` там, де вони
  лишились потрібні лише для singleton-блоку (`artifacts.py` зберіг
  `aioredis` — використовує `aioredis.Redis` у сигнатурах `push_record`/
  `push_artifact`/`get_current`/...; `computer_rate_limit.py`/
  `computer_confirm.py` зберегли `settings` — використовують для інших
  налаштувань). Оновив 9 тестових монкіпатчів `monkeypatch.setattr(<module>,
  "_redis"/"_client", fake)` → `monkeypatch.setattr(<module>, "get_redis",
  lambda: fake)` (точне дзеркало вже усталеного патерну з `test_bg_jobs.py`/
  `test_metrics.py`/`test_skills.py`) у `test_{artifacts,computer_admin,
  computer_confirm,computer_confirm_flow,computer_rate_limit,computer_trust,
  jobs,reminders,reminders_ics,reminders_cancel}.py`.
- **Верифіковано:** `mypy tools/app` ✅ 77 файлів; цільові тести
  `pytest tools/tests -k "reminder or jobs or artifact or computer_trust or
  computer_rate or computer_confirm or computer_admin or image_gen"` ✅
  37/37; повний набір `pytest tools/tests` ✅ 213/213.
- **Урок:** "мірроргеп" буває не лише документ↔код (ADR/roadmap), а й
  докстрінг-модуля↔реальні імпортери — `redis_util.py` чесно НАЗИВАВ
  модулі, які мали б ним користуватись, що й виявило прогалину одразу
  при читанні файлу. Також: дженерик-хелпери для тестових fixture
  (`monkeypatch.setattr(module, "get_redis", lambda: fake)`) масштабуються
  значно краще за прямий патч приватного `_redis`/`_client` — видно одразу,
  що це навмисний публічний контракт для DI в тестах, а не залежність від
  внутрішньої реалізації.

### Прохід 2026-06-07 (двадцять сьомий) — require_found: дзеркало в gateway (×2)
- **Контекст:** після 26-го проходу (де `require_found` з'явився у
  `tools/app/routes/_helpers.py`) перевірив ШИРШИЙ периметр — чи є той
  самий патерн "if rec is None: raise HTTPException(404, ...); return rec"
  деінде в кодовій базі (`memory`, `gateway`, `twin`, `hostagent`), а не
  лише в `tools`. Урок з минулих проходів: вузькі хелпери систематично
  пропускають сусідні входження, тож шукати треба одразу широко.
- **Знахідка:** regex-пошук по AST-подібному патерну `X = await ...; if X
  is None: raise HTTPException(404, "..."); return X` дав 2 нові
  побайтово ідентичні (різниться лише назва виклику `approve_plan`/
  `deny_plan`, `detail` той самий — `"plan not found"`) випадки в
  `gateway/app/platform/plans.py::{plans_approve,plans_deny}` —
  проксі-дзеркало того самого ендпоінта `agent.py::{approve,deny}_plan`,
  що вже отримав `require_found` у `tools` минулого разу. (`memory`,
  `twin`, `hostagent` — нуль збігів: там умови різні — `if not ok`,
  `except KeyError`, інші коди стану.)
- **Виправлено:** додав `require_found(value: _T | None, *, detail: str)
  -> _T` (TypeVar-дженерик, та сама сигнатура) у `gateway/app/_helpers.py`
  — як "дзеркало" `tools/app/routes/_helpers.py::require_found` з
  поясненням у докстрінзі чому дублюємо тонкий хелпер локально (немає
  спільної бібліотеки між `gateway`/`tools`, той самий підхід, що й для
  `require_text`). Замінив обидва виклики на
  `return require_found(await request.app.state.tools.X_plan(plan_id, uid), detail="plan not found")`.
- **Верифіковано:** `mypy gateway/app` ✅ 71 файл; цільові тести
  `pytest gateway/tests -k plan` ✅ 2/2; повний набір
  `pytest gateway/tests` ✅ 227/227. Імпорт `HTTPException` лишається
  потрібним у `plans.py` (502 у `plans_create`, 400 у `plans_execute`).
- **Урок:** "дзеркальні" мікросервіси (`gateway` як проксі-фасад над
  `tools`) часто повторюють той самий guard-патерн на своєму боці —
  після консолідації дублікатів в одному сервісі варто одразу перевірити
  сервіс(и)-дзеркала, а не вважати рефакторинг завершеним локально.

### Прохід 2026-06-07 (двадцять шостий) — require_found: ще один guard-дублікат (×9)
- **Знахідка:** у `tools/app/routes/{agent,bgjobs,orchestrator,skills,
  subagents,teams}.py` знайшов 9 побайтово ідентичних (з різним лише
  `detail`) блоків:
  ```python
  rec = await store.get_x(id)
  if rec is None:
      raise HTTPException(status_code=404, detail="x not found")
  return rec
  ```
  розкиданих по `agent.py` (×3 — get/approve/deny plan), `bgjobs.py`
  (×2 — get_job/finish_job), `orchestrator.py`, `skills.py`,
  `subagents.py`, `teams.py`. Це сьомий за рахунком варіант
  "guard-dedup family" (після `require_text`, `_check_computer_access`,
  `send_denial`, `_require_admin`, `require_admin_or_reply`,
  `require_mode`/`AGENT_MODES`).
- **Виправлено:** додав у `tools/app/routes/_helpers.py` дженерик-хелпер
  `require_found(value: _T | None, *, detail: str) -> _T` через
  `TypeVar` (`_T = TypeVar("_T")`) — generic-параметр потрібен, бо тип
  запису різний у кожному модулі (plan/job/run/skill/team), і без нього
  довелося б ставити `cast`/`Any` на кожному виклику. Замінив усі 9
  викликів на `return require_found(await store.get_x(id), detail="x not found")`.
  Прибрав тепер-невикористаний імпорт `HTTPException` у `skills.py`
  (єдиний файл, де інших використань `HTTPException` не лишилось —
  перевірив `grep -c` перед видаленням; в інших 5 файлах `HTTPException`
  далі активно використовується для 400/404/502/503 з кастомними
  деталями, тож імпорт лишив).
- **Верифіковано:** `mypy tools/app` ✅ 77 файлів (TypeVar-дженерик не
  створив проблем з типами); цільові тести
  `pytest tools/tests -k "agent or bgjobs or orchestrator or skills or subagents or teams"`
  ✅ 49/49; повний набір `pytest tools/tests` ✅ 213/213.
- **Урок:** перед видаленням імпорту після рефакторингу — спершу
  перевірити `grep -c "HTTPException" <file>`, а не покладатись на
  припущення "цей файл більше не кидає HTTP-помилок напряму"; у 4 з 5
  файлів припущення було б хибним (502 для exception-обгорток, 400 для
  ValueError, 503 для feature-flag, "not cancellable" для bgjobs-cancel —
  усе це НЕ той самий патерн "X not found", тож лишається кастомним).

### Прохід 2026-06-07 (двадцять п'ятий) — Proposal A виявився вже закритим
- **Змінив фокус**: замість чергового пошуку дублікатів — переглянув список
  "Відкритих пропозицій" (A, D, E, F, G), щоб прогресувати щось звідти
  замість накопичувати нові знахідки без закриття старих.
- **Знахідка:** Proposal A ("CI gate: зафіксувати mypy strict у пайплайні,
  якщо ще не там") виявився ВЖЕ ЗРОБЛЕНИМ — `.github/workflows/ci.yml`
  містить job `check` із matrix на 6 сервісів (`jarvis_core, gateway,
  memory, tools, twin, hostagent`), що запускає `mypy <service>/app`
  (з обходом `Duplicate module named "app"` через per-service ізоляцію —
  саме так, як вимагала пропозиція), а `pyproject.toml` має `[tool.mypy]
  strict = true` глобально. CI вже фейлиться red при регресії strict mode
  у будь-якому сервісі. Перевірив дату останньої зміни `ci.yml` —
  `e15e326`, **2026-06-04** — ДО того, як з'явився сам файл пропозицій.
  Тобто пропозицію сформулював, не звірившись із джерелом істини (CI-файлом),
  хоча перевірка зайняла б 30 секунд.
- **Виправлено:** позначив Proposal A як "✅ вже зроблено (виявлено у
  проході 25)" з повним описом знахідки й DoD; залишив запис в історії
  пропозицій (а не видалив) — щоб зберегти контекст "чому ми про це
  думали", за аналогією з тим, як не видаляються закриті ADR-знахідки.
- **Верифіковано:** документація-only (читання `.github/workflows/ci.yml`
  + `pyproject.toml`, без змін коду) — mypy/pytest не потрібні.
- **Урок:** п'ятий за каунтом клас "розбіжність документ↔реальність", але
  тепер у НОВОМУ напрямку — не "документ застарів відносно коду" (як
  mirror gaps 1-4), а "пропозиція в документі описує роботу, яку код уже
  виконує" (тобто документ "відстає" від уже завершеного стану). Перш ніж
  додавати "TODO: перевір чи є X" у відкриті пропозиції — варто спершу
  прочитати джерело істини (тут — CI workflow), а не формулювати на основі
  припущення "ймовірно ще не зроблено". Раджу так само звірити D/E/F/G —
  можливо, частина вже теж закрита фактично.

### Прохід 2026-06-07 (двадцять четвертий) — bot/_helpers: require_admin_or_reply
- **Продовжив "guard-дедуплікацію"** (4-й різновид після `require_text`,
  `_check_computer_access`, `send_denial`, `_require_admin`): пошук
  `if not is_admin(user_id):` ширшим периметром по `gateway/app/bot/*`
  знайшов 8 збігів, із них РІВНО 3 побайтово ідентичні — `if not
  is_admin(user_id): await tg.send_message(chat_id, "⛔ Admin only.");
  return True` — у `bot/access.py` (двічі: `acc:list`-callback і
  `_ACC_RE`-callback) та `bot/admin.py::handle_admin_callback` (`adm:Y`/
  `adm:N`).
- **Свідомо НЕ зачепив 5 інших** — той самий `if not is_admin(...)`,
  але з РІЗНИМ кастомним текстом: `bot/admin.py::handle_admin_command`
  ("⛔ Ця команда лише для адмінів (ADMIN_USER_IDS)."), `bot/access.py:151`
  (інше повідомлення-пояснення), `bot/commands.py` ×2 ("⛔ Лише для
  адмінів (ADMIN_USER_IDS)."), `bot/quick_actions.py` ("⛔ Cursor — лише
  для адмінів.") — точно як із `send_denial` у проході 17/18: форсувати
  різний UX-текст у спільний рядок заради DRY означало б змінювати
  повідомлення користувачу, а не просто прибирати дублювання коду.
- **Виправлено:** додав `require_admin_or_reply(tg, chat_id, user_id) ->
  bool` у вже існуючий `gateway/app/bot/_helpers.py` (поряд із
  `send_denial` — той самий "guard перед відповіддю боту" жанр), замінив
  3 виклики на `if await require_admin_or_reply(tg, chat_id, user_id):
  return True`.
- **Верифіковано:** `mypy gateway/app` ✅ 71 файл; таргетовані `-k
  "access or admin"` ✅ 27/27; повний `pytest gateway/tests` ✅ 227/227.
- **Урок:** "guard-дублікат перед відповіддю боту" — це не один клас, а
  СІМ'Я споріднених патернів (`send_denial`, `require_admin_or_reply`,
  `_check_computer_access`, `_require_admin` — кожен про свою умову й
  повідомлення), які варто шукати РАЗОМ одним проходом по `is_X(user_id)`-
  предикатах; і так само важливо щоразу відсіювати кастомні тексти —
  справжній дублікат лише там, де повідомлення байтово однакове.

### Прохід 2026-06-07 (двадцять третій) — webapp.py: _require_admin (ще один guard-дублікат)
- **Продовжив тему дедуплікації guard-блоків** (та сама форма, що
  `_check_computer_access` у проході 16 та `send_denial` у проходах
  17–18): пошук інших копій `raise HTTPException(status_code=403, ...)`
  ширшим периметром по `gateway/app` виявив 4 побайтово ідентичні
  2-рядкові блоки `if not can_change_agent_mode(user_id): raise
  HTTPException(403, "admin only")` у `webapp.py::{app_set_flag,
  app_lora_versions, app_lora_promote, app_lora_rollback}` — усі
  ендпоінти зміни режиму/LoRA, що вимагають прав адміна. Перевірив
  `grep can_change_agent_mode` по всьому `gateway/app` — інших копій
  немає (на відміну від `send_denial`, тут периметр = один файл).
- **Виправлено:** додав `_require_admin(user_id: int) -> None` одразу
  після `authorize()` у `webapp.py` (локальний helper — за зразком
  `_check_computer_access` із `webapp_ps.py`, бо периметр не виходить
  за межі файлу), замінив усі 4 виклики на `_require_admin(user_id)`.
- **Самовиправлена помилка під час застосування:** використав
  `sed`-подібну regex-заміну (`python -re.subn`) для масової підстановки —
  вона побайтово збіглася і з ТІЛОМ щойно написаного хелпера (бо я
  написав його реалізацію тим самим патерном, який заміняю), перетворивши
  `if not can_change_agent_mode(...): raise ...` усередині самого
  `_require_admin` на рекурсивний виклик `_require_admin(user_id)` —
  миттєва нескінченна рекурсія при першому ж виклику. Помітив одразу
  по diff'у в результаті інструменту (рядок 53 у виводі `Edit`),
  виправив до запуску тестів. **Урок про масові regex-заміни: коли
  патерн, що заміняється, і тіло щойно доданого узагальнюючого хелпера
  структурно ідентичні — заміна зачепить і сам хелпер; правильний
  порядок — спершу застосувати заміни до викликів, ПОТІМ дописати тіло
  хелпера (або явно виключити рядки нового визначення з area заміни).**
- **Верифіковано:** `mypy gateway/app` ✅ 71 файл; таргетовані `-k
  "webapp or app_set or lora or flag"` ✅ 26/26; повний `pytest
  gateway/tests` ✅ 227/227 — включно з кейсом, який спіймав би
  рекурсію (вона дала б `RecursionError`/timeout у тестах
  `app_set_flag`/`app_lora_*`, тож регресія неможливо пройшла б непоміченою).
- **Урок:** клас "guard-дублікат перед HTTP-помилкою" (4-й виявлений
  різновид після `require_text`, `_check_computer_access`, `send_denial`)
  — стабільно продуктивне джерело знахідок; і водночас масові
  текстові заміни під час рефакторингу несуть ризик self-match —
  варто або застосовувати їх ДО написання нового узагальнюючого коду,
  або звужувати область заміни явним номером рядків/якорями.

### Прохід 2026-06-07 (двадцять другий) — bot/admin.py: останній літерал AGENT_MODES
- **Замикання "ширшого периметра" з проходу 21**: коли шукав копії
  `{"chat", "agent", "hybrid", "computer"}`, бачив п'яте місце —
  `gateway/app/bot/admin.py:166` `parts[2] in ("chat", "agent", "hybrid",
  "computer")` — але це не "bad mode"-валідація з 400 (інша форма: фільтр
  у command-парсері `/admin mode <x>`), тож не зачепив його у проході 21,
  щоб не змішувати дві різні зміни. Повернувся до нього окремо.
- **Виправлено:** замінив кортеж-літерал на щойно введену константу
  `AGENT_MODES` з `gateway/app/_helpers.py` (`from .._helpers import
  AGENT_MODES`) — `parts[2] in AGENT_MODES`. Це останнє місце в кодовій
  базі, де набір режимів агента був записаний як магічний літерал
  (перевірив: `grep "chat.*agent.*hybrid.*computer"` тепер не показує
  жодного дубльованого літерала за межами визначення константи й
  оригінального джерела істини `tools/app/runtime.py`).
- **Чому окремий прохід, а не частина 21-го:** мав готову гіпотезу одразу
  (бачив рядок ще тоді), але свідомо відклав — у 21-му це додало б "ще
  одну незв'язану зміну" до й без того щільного коміту (новий хелпер +
  виправлення бага + 4 заміни); крихітний рефактор на одне слово краще
  верифікувати й задокументувати окремо, ніж розмивати фокус попереднього
  proposal.
- **Верифіковано:** `mypy gateway/app` ✅ 71 файл; таргетовані `-k "admin"`
  ✅ 22/22; повний `pytest gateway/tests` ✅ 227/227.
- **Урок:** коли під час пошуку "ширшим периметром" натрапляєш на схожий,
  але СТРУКТУРНО ІНШИЙ збіг (тут — членство у множині для парсингу команд,
  а не валідація з HTTP 400) — правильно відкласти його до окремого
  проходу, а не форсувати в поточний рефактор. Це й тримає кожен proposal
  сфокусованим на одній ідеї, і дає привід повернутись та "замкнути"
  периметр повністю — що й сталося тут.

### Прохід 2026-06-07 (двадцять перший) — require_mode: уніфікація + прихований баг нормалізації
- **Повернувся до дедуплікації** після двох документаційних проходів (19, 20):
  пошук інших патернів `raise HTTPException(status_code=400, ...)` ширшим
  периметром по `gateway/app` + `tools/app` виявив 4–5 байтово майже
  ідентичних блоків `m = (x or "<default>").strip().lower(); if m not in
  {...}: raise HTTPException(400, "bad mode")` — `admin_panel.py::admin_set_mode`,
  `platform/settings_api.py::settings_mode` (через `_MODES`),
  `platform/workbench.py::{workbench_ask,workbench_resume}` (через інший
  `_MODES`, що додає `"auto"`), `webapp.py::app_set_mode`.
- **Знахідка — прихований БАГ, не лише дублювання:** на відміну від трьох
  сусідів, `webapp.py::app_set_mode` НЕ нормалізував `body.mode` перед
  звіркою (`if body.mode not in {...}`, без `.lower().strip()`). Тобто
  Mini App ендпоінт `/app/mode` повертав 400 "bad mode" на `"Agent"` чи
  `" agent "`, хоча бекенд (`tools/app/runtime.py::set_agent_mode`, який
  теж робить `.lower().strip()`) їх би прийняв — реальна, хай і дрібна,
  поведінкова розбіжність між дзеркальними ендпоінтами одного продукту
  (Telegram Mini App vs Platform Web Console vs Admin Panel).
- **Виправлено:** додав `AGENT_MODES` (канонічна множина, дзеркало
  `tools/app/runtime.py::set_agent_mode`) і `require_mode(value, valid,
  *, field="mode")` у `gateway/app/_helpers.py` — нормалізує + перевіряє
  належність явно переданій множині (множина — параметр, бо вони різняться:
  `workbench.py` додає `"auto"`). Замінив усі 4 точки виклику; `webapp.py`
  тепер теж нормалізує (і передає нормалізоване значення в `svc.set_mode`,
  замість сирого `body.mode`) — баг автоматично зник як побічний ефект
  уніфікації. `platform/settings_api.py::_MODES` видалив — тепер імпортує
  спільний `AGENT_MODES`; `workbench.py::_MODES` залишив — інша множина
  (з `"auto"`), не false positive.
- **Розглянув і свідомо НЕ чіпав:** `_FLAGS`/`("streaming", "voice_reply")`
  у `settings_api.py`/`webapp.py` — той самий "звірка з множиною" патерн,
  але семантично інша річ (назва прапорця, не режим), і обидва вже
  нормалізовані однаково (прямий `in`, без `.lower()` — імена прапорців не
  потребують регістронезалежності). Форсувати їх у `require_mode` (навіть
  з `field="flag"`) означало б додати нормалізацію там, де її нема й не
  мало бути — нова поведінкова розбіжність замість усунутої.
- **Верифіковано:** `mypy gateway/app` ✅ 71 файл (після виправлення —
  типізація `valid: AbstractSet[str]` замість надто вузького `frozenset[str]`,
  бо `workbench._MODES`/`settings_api`-набори — звичайні `set[str]`-літерали);
  таргетовані тести `-k "mode or flag or admin or settings or workbench or
  webapp"` ✅ 56/56; повний `pytest gateway/tests` ✅ 227/227.
- **Урок:** "ширший периметр" (validation-блоки навколо `HTTPException(400)`)
  знову окупився — і цього разу виявив не просто дублювання, а РЕАЛЬНУ
  поведінкову розбіжність між дзеркальними API одного продукту. Варто й
  надалі при пошуку дублікатів звіряти не лише структуру блоків, а й
  фактичну поведінку (нормалізація, дефолти) — найцінніші знахідки часто
  ховаються саме в "майже однакових, але не зовсім" копіях.

### Прохід 2026-06-07 (двадцятий) — Фаза 4: найбільший "mirror gap" — ціла фаза 0% vs 100%
- **Продовжив тему проходу 19** (систематична звірка заголовків фаз і
  чекбоксів між roadmap-документами — "варто періодично прогонювати цю
  звірку"): прогнав підрахунок `[ ]`/`[x]` по діапазонах рядків кількох
  фаз `PLATFORM_ROADMAP.md` (Фази 3, 4, 5, 7).
- **Знахідка — четвертий і НАЙГІРШИЙ досі екземпляр класу "mirror gap"
  (після ADR-005 проходу 8, ADR-008 проходу 11, P12 проходу 19):**
  `PRODUCT_ROADMAP.md` секція "## Фаза 4 — Edge MVP (USB)" показувала
  ВСІ 5 підпунктів (4.1–4.5) як `[ ]` (0% виконано) і заголовок без
  позначки прогресу — тоді як `PLATFORM_ROADMAP.md` секція "Фаза 4 —
  Edge USB" показує ТІ Ж САМІ 5 підпунктів усі `[x]` з конкретними
  посиланнями на реалізацію (`edge/rag.py`, `edge/edge_sync.py`,
  `run_win.bat`/`run_linux.sh`, `jarvis_core` + `LLM_BACKEND=kobold`)
  і заголовок "**активна (~70%)**". Це не дрібна розбіжність формулювань
  (як P12), а пряма суперечність "0/5 зроблено" проти "5/5 зроблено" —
  цілий розділ "живого" документа показував стан, застарілий мінімум на
  одну повну ітерацію розробки.
- **Виправлено в `PRODUCT_ROADMAP.md`:** усі 5 чекбоксів `[ ]` → `[x]`
  з тими самими посиланнями на реалізацію, що й у `PLATFORM_ROADMAP.md`;
  заголовок секції доповнив міткою "· **активна (~70%)**" (синхронізовано
  з джерелом істини); рядок "Вихід фази 4" розширив з "флешка офлайн;
  LAN → проксі на Twin" до повного "флешка офлайн → LAN → проксі на
  Twin; LoRA sync автоматичний" (відображає реалізований 4.4 SyncAgent).
  Додав примітку-якір під таблицею: "Деталі та поточний % —
  `docs/PLATFORM_ROADMAP.md` → 'Фаза 4 — Edge USB' (тут і там — той
  самий перелік 4.1–4.5; тримайте чекбокси в синхроні)" — щоб наступного
  разу розбіжність впадала в очі одразу під час редагування.
- **Розглянув і свідомо НЕ чіпав:** заголовок `PLATFORM_ROADMAP.md`
  "**активна (~70%)**" попри всі 5 `[x]` — за аналогією з Proposal E
  (C3 потребує живого TG smoke-тесту) ~70% імовірно відображає реальну
  валідацію "в полі" (живе тестування на USB-флешці), не описану
  чекбоксами; підвищувати % без підтвердження було б новою вигадкою
  поверх існуючої, а не виправленням розбіжності.
- **Верифіковано:** документація-only, код не змінювався — mypy/pytest
  не потрібні (як і прохід 19).
- **Урок:** клас "mirror gap" продовжує траплятися (4 рази за 20
  проходів) і масштаб росте — від одного ADR-індексу до цілої фази
  під замовчуванням "0% готово". Додана примітка-якір — перший крок
  до системного запобігання: коли редактор бачить пряме посилання на
  дзеркальний документ просто під таблицею, шанс розсинхронізації
  падає. Варто розглянути аналогічні якорі для решти спільних секцій
  (Фази 3, 5, 6 — уже звірено цього проходу і узгоджені).

### Прохід 2026-06-07 (дев'ятнадцятий) — "архітектура/документація": P12 mirror gap
- **Перемкнувся з дедуплікації на архітектурну перевірку** (циклічно
  застосовую усі дієслова `/loop`, не лише "рефактори") — звірив
  ADR-індекс `DESIGN.md` ↔ `PLATFORM_ROADMAP.md` (мирно, обидва
  ADR-001..008, без прогалин — закрито у проходах 8/11) і пройшовся
  по заголовках фаз/лічильниках можливостей у roadmap-документах.
- **Знахідка — P12 "mirror gap" (третій випадок цього класу багів,
  після ADR-005 у проході 8 і ADR-008 у проході 11):** `PLATFORM_ROADMAP.md`
  заголовок "## Фаза 6 — Platform Web Console" стверджував "**P0–P11
  done (~95%)**", хоча в тій самій секції нижче `### P12 — Cursor tasks`
  має статус **done** з усіма 4 підпунктами `[x]`, і в таблиці
  "P4+ — Майбутні можливості" P12 теж `[x]`. Жодного незакритого
  чекбоксу в усій секції Фази 6 (перевірив — 0 збігів `[ ]`). Те ж
  саме "12 можливостей (P0–P11)" розповсюджено copy-paste'ом ще у 2
  місцях: `PRODUCT_ROADMAP.md` (опис посилання на `PLATFORM_ROADMAP.md`)
  і `README.md` (рядок 7, опис `docs/PLATFORM_ROADMAP.md`). А в
  changelog (`## Історія оновлень`) запису про додавання P12 не було
  взагалі — версії стрибали з 1.5 одразу "в нікуди" (без 1.6).
- **Виправлено:** заголовок Фази 6 → "**P0–P12 done (100%)**";
  "12 можливостей (P0–P11)" → "13 можливостей (P0–P12)" у
  `PRODUCT_ROADMAP.md` і `README.md`; додав запис у changelog
  `| 2026-06-07 | 1.6 | P12 Cursor tasks ... — Фаза 6 закрита (P0–P12,
  100%) |`. Старий запис 1.0 ("12 можливостей, Platform P0–P11")
  навмисно НЕ чіпав — це історичний знімок стану на дату початкового roadmap,
  а не жива метрика.
- **Верифіковано:** документація-only, код не змінювався — mypy/pytest
  не потрібні.
- **Урок:** заголовки фаз/лічильники можливостей — ще один "дзеркальний"
  клас, який варто звіряти з фактичним станом checkbox'ів так само
  систематично, як ADR-індекс; виявив третій екземпляр того самого
  класу багів за 19 проходів — варто періодично прогонювати цю звірку.

### Прохід 2026-06-07 (вісімнадцятий) — send_denial: підняв на рівень bot/_helpers
- **Знахідка (продовження проходу 17 — урок про "ширший периметр" знову
  спрацював):** одразу перевірив, чи побайтовий блок `if denied: await
  tg.send_message(chat_id, denied); return True` (щойно винесений у
  `remote.py::_send_denial`) зустрічається і в СУСІДНІХ `bot/*`-модулях —
  так і виявилось: іще 6 копій у `commands.py` (мод callback `mode_` і
  команда `/mode`), `computer.py` (`cmp:Y`/`cmp:N` confirm) і
  `quick_actions.py` (×3 — BTN_COMPUTER/BTN_SCREEN/BTN_CLIPBOARD). Разом
  11 копій по 4 файлах — `_send_denial`, локальний для `remote.py`,
  виявився занадто вузько розташованим (як і `require_text` у проході 13).
- **Виправлено (підняв рівень одразу, без проміжного кроку):** створив
  `gateway/app/bot/_helpers.py::send_denial` (публічний, бо тепер спільний
  для всього `bot/`), переніс туди логіку й докстрінг із локального
  `_send_denial`, прибрав останній із `remote.py`. Додав імпорт +
  замінив усі 11 викликів: 5 у `remote.py` (перейменування виклику),
  по 2 у `commands.py`, 1 у `computer.py`, 3 у `quick_actions.py`.
  Докстрінг хелпера явно документує межі застосовності — НЕ охоплює
  компаунд-умову `denied and len(parts) >= 2` (`commands.py` /mode,
  рядок ~491) і callback-варіант через `tg.answer_callback_query`
  (`commands.py:606`) — інша форма відповіді, форсування дало б
  розгалуження хелпера заради 2 нетипових місць.
- **Верифіковано:** `mypy gateway/app` ✅ 71 файл (0 помилок), цільові
  тести (`-k "commands or computer or quick or remote or bot"`) ✅ 22/22,
  повний `pytest gateway/tests` ✅ 227/227 — без регресій.
- **Урок підтверджено вдруге:** перевірка ширшого периметра одразу при
  виявленні дублікату (а не "закриваю питання локально, перевірю пізніше")
  — це те, що варто робити щоразу, бо рідко буває, що дублікат живе лише
  в одному файлі. Тепер `send_denial` — єдина точка істини для "повідом
  про відмову й вийди" у всьому `gateway/app/bot/`.

### Прохід 2026-06-07 (сімнадцятий) — bot/remote.py: _send_denial
- **Знахідка:** продовжуючи "ширший периметр" із проходу 16 — у тому ж
  `gateway/app/bot/remote.py::handle_remote_command` побайтово повторювався
  3-рядковий блок `if denied: await tg.send_message(chat_id, denied);
  return True` — по одному разу в гілках `/file`, `/macro`, `/tasks`, `/see`,
  `/clipboard` (5 копій). Інша форма того самого "повідом про відмову й
  вийди", ніж у проході 16 (там — `raise HTTPException(403, ...)`, тут —
  Telegram-відповідь + early-return сигнал "оброблено").
- **Чому саме тут лишив `denied` обчисленим один раз на початку функції,
  а перевірку — в кожній гілці:** команда, що не збігається з жодним
  префіксом, не повинна відмовлятись (функція повертає `False` —
  "не моя команда"); підняти перевірку нагору означало б відмовляти і в
  нерелевантних повідомленнях.
- **Виправлено:** додав `_send_denial(tg, chat_id, denied) -> bool` —
  тонкий хелпер "якщо є відмова — надіслати і повернути True", замінив
  усі 5 копій на `if await _send_denial(tg, chat_id, denied): return True`.
  −10 рядків чистого дублювання (3→2 рядки на місці виклику + 1 спільний
  хелпер з докстрінгом замість 5 копій логіки надсилання).
- **Верифіковано:** `mypy gateway/app` ✅ 70 файлів (0 помилок), цільові
  тести (`-k "remote"`) ✅ 5/5, повний `pytest gateway/tests` ✅ 227/227 —
  без регресій.
- **Спостереження для майбутніх проходів:** "відмова в доступі до Computer
  Use" тепер має 3 різні втілення по кодовій базі (`HTTPException(403)` у
  webapp/platform, `tg.send_message` у bot, генерація denied-рядка в
  `auth.py`) — кожне дзеркалить контекст виклику (HTTP API vs Telegram bot)
  і наразі коректно лишається роз'єднаним; уніфікація через спільний
  protocol/callback дала б абстракцію заради абстракції.

### Прохід 2026-06-07 (шістнадцятий) — webapp_ps.py: _check_computer_access
- **Знахідка:** у `gateway/app/webapp_ps.py` (5 ендпоінтів — ask/pending/
  confirm/cancel/resume) побайтово повторювався 4-рядковий блок:
  `if user_id: denied = computer_denied_message(user_id); if denied: raise
  HTTPException(403, denied)`. Шукав ширше — за патерном
  `denied = .*_denied_message` по всьому `gateway/app` (35 збігів), але
  більшість — у `bot/*` (інша дія при відмові: текстова відповідь у Telegram,
  не HTTPException) або з різними `*_mode_denied_message`-комбінаціями
  (`agent_mode_denied_message or computer_mode_denied_message`, інша
  природа). Лише `webapp_ps.py` мав 5 побайтово ідентичних копій.
- **Чому не об'єднав із `platform/workbench.py::_check_computer`:** та версія
  не має `if user_id:`-гарду — там завжди справжній `auth.user_id`
  (`PlatformAuth`, обов'язкова автентифікація). У `webapp_ps.py` ж
  `authorize()` може повернути `0` (dev-режим `WEBAPP_DEV_OPEN`, без
  реального Telegram-користувача) — і тоді перевірку треба пропустити.
  Спільний хелпер означав би або зайву гілку для `workbench`, або ризик
  випадково забути гард в іншому місці — лишив локальним, з докстрінгом, що
  пояснює, чому це навмисно не той самий хелпер.
- **Виправлено:** додав `_check_computer_access(user_id)` у
  `webapp_ps.py` (поруч із вже наявним `_ndjson_sse`), замінив усі 5
  чотирирядкових блоків на один виклик. −15 рядків дублювання.
- **Верифіковано:** `mypy gateway/app` ✅ 70 файлів (0 помилок), цільові
  тести (`-k "webapp or ps"`) ✅ 27/27, повний `pytest gateway/tests`
  ✅ 227/227 — без регресій.

### Прохід 2026-06-07 (п'ятнадцятий) — require_text: останні 3 у tools/app
- **Застосував урок проходу 14 одразу:** перш ніж шукати нову ціль,
  прогнав широкий grep по `raise HTTPException(status_code=400,
  detail=f?"[a-z_]* required")` ОДНОЧАСНО по `tools/app` і `gateway/app`
  (виключивши самі `_helpers.py`) — щоб перевірити, чи не лишилось ще
  десь не-консолідованих `require_text`-патернів за межами вже
  оброблених областей.
- **Знахідка:** 8 кандидатів. З них 3 — справжні побайтові збіги
  патерну `x = (req.X or "").strip(); if not x: raise HTTPException(400,
  "X required")`, досі НЕ використовували вже наявний (з проходу 6!)
  `tools/app/routes/_helpers.py::require_text`:
  - `agent.py:60-62` (`text`, ендпоінт `/agent/plan`)
  - `computer.py:30-32` (`code`, ендпоінт `/computer/confirm` —
    додатково викликав `.strip()` ДВІЧІ: і в умові, і при передачі;
    `code: str = ""` у схемі — `None` неможливий, тож behavior
    ідентична)
  - `research.py:17-19` і `:30-32` (`query` — двічі в одному файлі,
    `/research` і `/research/run`)
  Решта 5 — НЕ збіги (форма інша, рефакторити шкідливо чи нема сенсу):
  `improve.py`×2 і `gateway/app/platform/improve.py` перевіряють
  порожність СПИСКУ (`if not body.item_ids`), `openai_api.py:108`
  перевіряє результат `_extract_text(messages)` (теж не рядкове поле
  тіла), а `platform/projects.py:85` — той самий behavior-sensitive
  кейс, що й знайдений у проході 10 (`if not body.name.strip()` без
  переприсвоєння — рефакторинг змінив би що йде у `_mem()`: stripped
  чи raw `body.name`; лишив як є).
- **Виправлено:** замінив 4 виклики (5 рядків коду, бо `code` ще й мав
  зайвий повторний `.strip()`) на `require_text(...)`. Додав
  `require_text` в імпорти `agent.py` (вже імпортував `_helpers` для
  `ndjson` — додав до існуючого рядка), `computer.py` і `research.py`
  (нові рядки `from ._helpers import require_text`, з дотриманням
  порядку `..` перед `.`). Прибрав непотрібний `HTTPException`-імпорт
  із `research.py` (після заміни обох викликів він там більше не
  використовується).
- **Верифіковано:** `mypy tools/app` ✅ 77 файлів (0 помилок), цільові
  тести (`-k "agent or computer or research"`) ✅ 71/71, повний
  `pytest tools/tests` ✅ 207/207 — без регресій.
- **Підсумок:** широкий grep одразу на старті (а не "звужено" по
  `gateway/`, як у проході 13) дав повну картину за один прохід — і
  знайшов справжні збіги, і одразу відсіяв 5 хибних спрацювань з чіткою
  аргументацією чому кожен — не кандидат. `require_text`-консолідація
  тепер охоплює увесь `tools/app` (з проходу 6) і весь `gateway/app`
  (проходи 13-14), нових кандидатів не лишилось.

### Прохід 2026-06-07 (чотирнадцятий) — require_text: підняв на рівень gateway/app
- **Знахідка (продовження проходу 13):** одразу після створення
  `platform/_helpers.py::require_text` виявив, що той самий патерн
  (`x = (body.X or "").strip(); if not x: raise HTTPException(400, "X
  required")`) живе **і поза `platform/`** — у `webapp.py` (`version`,
  той самий `twin_promote_lora`-ендпоінт що й `platform/models.py`,
  продубльований у двох місцях API!), `webapp_ps.py` (`text`/`code`/`result`
  — 3 рази) і `platform/models.py` (`version`). Разом іще 5 повторів
  — хелпер з проходу 13 був занадто вузько розташований (бачив лише
  `platform/`, не охоплював top-level `gateway/app/`).
- **Виправлено (підняв рівень):** переніс хелпер із
  `platform/_helpers.py` у `gateway/app/_helpers.py` (спільний для
  `platform/*` і top-level `webapp*`), розширив докстрінг переліком усіх
  місць використання. Оновив імпорти у вже відрефакторених `jobs/plans/
  workbench/memory.py` (`._helpers` → `.._helpers`). Додав виклики у
  `models.py` (`version`), `webapp.py` (`version` — той самий
  promote-ендпоінт), `webapp_ps.py` (`text`/`code`/`result` — додатково
  параметризував `field=`), і ще 2 у `workbench.py` (`code`/`result`,
  пропущені проходом 13 — різні назви полів змусили їх не впасти у перший
  grep). Прибрав непотрібний `HTTPException`-імпорт із `models.py`.
  Сумарно (прохід 13+14): −9 + −15 = −24 рядки дублювання, єдина точка
  істини для "{field} required"-валідації по всьому `gateway/app`.
- **Верифіковано:** `mypy gateway/app` ✅ 70 файлів (0 помилок), цільові
  тести (`-k "webapp or platform_models or platform_workbench or models"`)
  ✅ 23/23, повний `pytest gateway/tests` ✅ 227/227 (фоновий прогін) —
  без регресій.
- **Урок на майбутнє:** при виявленні дублікату варто одразу перевіряти
  ширший periметр (не лише сусідні файли в одному під-пакеті) — саме так
  знайшлась решта 5 повторів одразу після "закритого" проходу 13.

### Прохід 2026-06-07 (тринадцятий) — gateway/platform: require_text-дзеркало
- **Знахідка:** у `gateway/app/platform/{jobs,plans,workbench,memory}.py` —
  4 рази побайтово (для `text`) чи майже побайтово (для `query`) повторений
  патерн `x = (body.X or "").strip(); if not x: raise HTTPException(400, "X
  required")`. Це той самий патерн, який прохід 6 вже усунув у
  `tools/app/routes/` через `require_text()` — але тут інший сервіс/пакет
  (`gateway`, не `tools`), спільної бібліотеки між ними немає.
- **Рефактор:** створив `gateway/app/platform/_helpers.py` з
  `require_text(value, *, field="text") -> str` — дзеркало
  `tools/app/routes/_helpers.py::require_text` (з докстрінгом, що пояснює,
  чому це дублікат-хелпер, а не імпорт зі спільного місця — окремі
  деплой-юніти). Замінив усі 4 виклики: `jobs_create`/`plans_create`/
  `workbench_ask` → `require_text(body.text)`, `memory_search` →
  `require_text(body.query, field="query")`. У `memory.py` прибрав
  непотрібний імпорт `HTTPException` (більше не використовується напряму).
  −9 рядків дублювання.
  **[прохід 14]:** виявив ще 5 повторів цього ж патерну поза `platform/`
  (`webapp.py`/`webapp_ps.py`/`models.py`) — переніс хелпер на рівень
  `gateway/app/_helpers.py` (видаливши `platform/_helpers.py`) і покрив усі
  9 місць; див. запис проходу 14 нижче.
- **Верифіковано:** `mypy gateway/app` ✅ 70 файлів (0 помилок), цільові тести
  (`test_platform_{jobs,plans}.py` + `test_platform.py -k "create or search or
  ask or workbench"`) ✅ 20/20, повний `pytest gateway/tests` ✅ 227/227
  (фоновий прогін) — без регресій.

### Прохід 2026-06-07 (дванадцятий) — memory/app: дедуплікація embed-помилок
- **Знахідка:** у `memory/app/main.py` ендпоінти `embed`/`search` мали побайтово
  ідентичний блок `try: vec = await app.state.embedder.embed(X) except Exception
  as exc: raise HTTPException(502, f"embed failed: {exc}") from exc` — 2 рази.
  (Третій схожий випадок у `store` — НЕ ідентичний: там помилка ембедингу одного
  chunk'а нефатальна, обробляється `logger.error(...)+continue`, інша семантика —
  лишив його кастомним.)
- **Рефактор:** виніс у `_embed_or_502(text: str) -> list[float]` — приватний
  helper поряд з ендпоінтами, з докстрінгом, що пояснює, чому `store` НЕ
  використовує той самий хелпер (різна fault-tolerance семантика). Замінив обидва
  виклики на `vec = await _embed_or_502(req.text/query)`. −6 рядків дублювання.
- **Верифіковано:** `mypy memory/app` ✅ 6 файлів (0 помилок), `pytest memory/tests`
  ✅ 17/17 (повний прогін) — без регресій.

### Прохід 2026-06-07 (одинадцятий) — ADR-008 (ще одна mirror-прогалина)
- **Закрив Proposal C** (рекомендація з проходу 2: self-improve scan — задокументувати
  як навмисно ручний human-in-the-loop процес рішенням ADR). Під час пошуку місця для
  запису виявив, що **рядок `ADR-008` уже існує** в індекс-таблиці
  `PLATFORM_ROADMAP.md:402` (`Self-improve scan — навмисно ручний тригер...`) — але
  **повного ADR-запису в `DESIGN.md` не було** (там ADR обривався на ADR-007). Точно
  та сама "mirror-прогалина" архітектури документації, яку зафіксував прохід 8 для
  ADR-005 (тільки навпаки: тоді existed повний запис без рядка в індексі, тепер —
  рядок в індексі без повного запису).
- **Виправлено:** додав `### ADR-008: Self-improve scan — навмисно ручний тригер
  (human-in-the-loop)` у `DESIGN.md` (Context/Decision/Alternatives/Consequences —
  за форматом ADR-001..007), з описом, узгодженим зі змістом рядка індексу:
  `POST /improve/scan` — єдина точка входу, без `JOB_TYPES`/cron/scheduler,
  людина обов'язково review'ить кандидатів перед `/improve/export`.
- **Висновок (для майбутніх проходів):** ADR index↔record mirror — повторюваний
  клас прогалин (вже 2 знахідки за 11 проходів); варто за нагоди пройтись по всіх
  ADR-001..008 одним проходом і звірити обидва боки таблиці/записів комплексно,
  а не по одному при нагоді.
- **Верифіковано:** документація-only зміна, код не змінювався — перевірка
  mypy/pytest не потрібна (узгоджено з підходом проходу 8).

### Прохід 2026-06-07 (десятий) — тести gateway/platform
- **Знахідка (архітектурна неузгодженість тестів):** у `gateway/tests/conftest.py`
  існує спільний фікстур `platform_client` (monkeypatch 7 налаштувань
  `platform_password/admin_panel_user/admin_user_ids/allowed_user_ids/
  telegram_bot_token/data_dir/health_watch_interval` + `TestClient(app)`), яким
  коректно користуються 6 файлів (`hooks/improve/mcp/orchestrator/research/
  subagents`). Але ще ~7 файлів (`test_platform_{jobs,teams,skills,connectors,
  plans,projects,test_platform}`) визначали **власний** локальний `client`
  фікстур, що подекуди побайтово, подекуди ні дублював той самий
  `monkeypatch.setattr(settings, …)`-блок — класичний "скопіював і трохи
  змінив" дрейф, що ускладнює підтримку (зміна формату `settings` вимагала б
  правок у ~13 місцях замість одного).
- **Аналіз безпечності консолідації:** порівняв набори налаштувань усіх 7
  файлів проти `platform_client`. Знайшов 4, де локальний набір — або
  **ідентичний** (`test_platform_connectors`, `test_platform_plans` — рівно ті
  самі 7 ключів), або **строгий підмножина** (`test_platform_teams`,
  `test_platform_skills` — 5 із 7, решта 2 (`allowed_user_ids`/
  `telegram_bot_token`) безпечні додаткові override'и, бо ці файли тестують
  Platform API, а не Telegram-специфічну поведінку). Інші 3
  (`test_platform_jobs` має зайвий `access_store_path`, `test_platform_projects`
  не виставляє `data_dir` і додає кастомні monkeypatch для `get_active/
  set_active`+fake memory client, `test_platform.py` — суперсет із
  `access_store_path`+`memory_url`+кастомні overview/flags-моки) — їхні набори
  **не** є строгими підмножинами/копіями `platform_client`, форсована
  консолідація змінила б поведінку тестового оточення. Лишив їх кастомними
  свідомо (як і Proposal B раніше — "не уніфікувати, якщо це додає ризику
  більше, ніж прибирає дублювання").
- **Рефактор (4 файли — безпечна частина):** `test_platform_teams.py`,
  `test_platform_skills.py`, `test_platform_connectors.py`,
  `test_platform_plans.py` тепер мають локальний `client(platform_client)` —
  тонку обгортку, що бере готовий `TestClient` зі спільного фікстура й додає
  лише свої `AsyncMock`-стаби на `tools.*`, замість повторення 5-7 рядків
  `monkeypatch.setattr`. Прибрано тепер-непотрібні імпорти `TestClient/settings/
  app/monkeypatch/tmp_path` з усіх чотирьох файлів. −24 рядки дублювання,
  сигнатури тестів (`def test_X(client)`) не змінились — diff локальний до
  фікстурів.
- **Верифіковано:** `mypy gateway/app` ✅ 69 файлів (0 помилок); цільові тести
  (5 тестів у 4 файлах) ✅ 5/5; повний `pytest gateway/tests` ✅ 227/227 —
  без жодної зміни в кількості/результатах, лише внутрішня структура
  фікстурів.

### Прохід 2026-06-07 (дев'ятий)
- **Новий refactor (jarvis_core — продовжив проходити по сервісах):** у
  `jarvis_core/bg_jobs.py::normalize_payload` знайшов
  `task = str(payload.get("task") or payload.get("text") or "").strip(); if not
  task: raise ValueError("task required")` — побайтово **4 рази** у гілках
  `subagent`/`agent_team`/`orchestrator`/`cursor_task` (диспетчеризація за
  `job_type` для Background Jobs). Виніс у приватний `_require_task(payload:
  dict[str, Any]) -> str` поряд з `normalize_payload` (єдина крапка входу для
  всіх типів завдань — природне місце для guard'а саме цього поля). Гілки
  `agent_turn`/`deep_research` лишив кастомними обґрунтовано — інші ключі/назви
  полів (`text`/`text required`, `query`/`query required`), форсування у спільний
  хелпер дало б менш читабельний generic API заради 2 рядків економії.
  −9 рядків дублювання.
- **Верифіковано:** `mypy jarvis_core` ✅ 20 файлів (0 помилок),
  `pytest jarvis_core/tests` ✅ 26/26 (повний прогін), `pytest tools/tests -k
  "bg_job"` ✅ 5/5 (downstream-споживач `tools/app/bg_jobs.py`) — без регресій.

### Прохід 2026-06-07 (восьмий) — "архітектура/документація"
- **Знайдено документаційний розрив (gap), не код-дублікація:** таблиця "Архітектурні
  рішення (ADR)" у `docs/PLATFORM_ROADMAP.md` (рядок 391+) — це індекс/дзеркало
  повних ADR-записів з `docs/DESIGN.md`. Послідовність номерів стрибала
  ADR-004 → ADR-006, **пропускаючи ADR-005** ("Event Bus для внутрішньої координації
  Twin"), хоча сам запис існує і повний у `DESIGN.md:1240`. Ймовірно, випадково
  пропущений при якомусь з попередніх редагувань таблиці.
- **Виправлено:** додав рядок `| ADR-005 | Event Bus для внутрішньої координації
  Twin | Підписник додається без зміни publisher; уникає tight coupling прямих
  викликів і зайвої залежності від Redis Pub/Sub |` — стисле резюме Decision/
  Consequences з повного запису, у стилі сусідніх рядків таблиці. Перевірив
  послідовність ADR-001…008 — тепер усі 7 пронумерованих ADR з `DESIGN.md`
  представлені в індексі (+ окремий тег `E2`, що не є класичним ADR).
- **Чому це важливо:** індекс ADR — це "карта рішень" для швидкого огляду
  архітектури; пропущений запис означає, що читач, який сканує лише таблицю
  (а не повний `DESIGN.md`), пропустить рішення про Event Bus у Twin —
  ризик повторного "відкриття" вже закритого питання в майбутньому.
- Код не змінювався — `mypy`/`pytest` не потребувались (документаційна правка).

### Прохід 2026-06-07 (сьомий)
- **Новий refactor (memory/app — продовжив розширювати зону огляду по сервісах):**
  у `memory/app/main.py` знайшов guard `if await app.state.db.get_project(project_id,
  user_id) is None: raise HTTPException(404, "project not found")`, повторений
  **побайтово 3 рази** у `project_file_{add,list,delete}` (різнилось лише ім'я
  user_id-аргументу: `req.user_id` vs `user_id`). Виніс у приватний хелпер
  `async def _require_project(db: DB, project_id: int, user_id: int) -> None`
  (поряд з ендпоінтами — єдиний файл сервісу, окремого helpers-модуля тут нема,
  на відміну від `tools/app/routes/_helpers.py`). −6 рядків дублювання,
  +1 self-documenting guard з явним докстрінгом про походження.
- **Верифіковано:** `mypy memory/app` ✅ 6 файлів (0 помилок),
  повний `pytest memory/tests` ✅ 17/17 — без регресій (сервіс малий, повний прогін
  замість фонового).

### Прохід 2026-06-07 (шостий)
- **Новий refactor (tools/app, не gateway — розширив зону огляду):** знайшов
  той самий клас "тривіальної валідаційної дублікації", але в `tools/app/routes/`:
  - `task = (body.task or "").strip(); if not task: raise HTTPException(400, "task
    required")` — побайтово **6 разів** у 4 файлах (`cursor.py` ×2, `orchestrator.py`,
    `subagents.py` ×2, `teams.py`);
  - `budget = max(1, min(body.budget_X, settings.subagent_max_budget))` — **2 рази**
    (`subagents.py`, `teams.py`, різнилось лише ім'я поля).
  Виніс обидва у `tools/app/routes/_helpers.py` (вже існував спільний модуль для
  route-helpers — природне місце): `require_text(value, *, field="task") -> str`
  і `clamp_budget(value: int) -> int`. Замінив усі 8 входжень; прибрав осиротілі
  імпорти (`HTTPException` у `cursor.py`, `settings` у `subagents.py`/`teams.py`).
  −14 рядків дублювання, +2 однорядкові переважно self-evident хелпери.
- **Верифіковано:** `mypy tools/app` ✅ 77 файлів (0 помилок),
  `pytest tools/tests -k "cursor or orchestrator or subagent or teams"` ✅ 12/12,
  повний `pytest tools/tests` — без регресій (запущено у фоні, підтверджено).

### Прохід 2026-06-07 (п'ятий)
- **Новий refactor (продовження теми B):** виявив, що `jobs_get`/`plans_get`/
  `skills_get`/`teams_get` у `gateway/app/platform/{jobs,plans,skills,teams}.py`
  були побайтово ідентичним патерном — `GET /platform/api/X/{x_id}` →
  `await tools.get_X(x_id)` → `404 "X not found"`, якщо результат `None` (різнились
  лише шлях/ім'я методу/текст помилки). Раніше (прохід 2, Proposal B) це було
  помилково віднесено до "має різну 404-обробку" — насправді 4 з них збігались 1:1.
  Виніс у новий generic-хелпер `register_tools_get_by_id(router, path, tools_attr,
  *, id_name, not_found)` у `proxy.py` — читає path-параметр через
  `request.path_params[id_name]` (FastAPI резолвить його як `str` із шаблону шляху,
  тому явний типізований параметр не потрібен). Замінив усі 4 виклики на однорядкові
  декларації; прибрав осиротілі імпорти (`Depends`/`HTTPException`/`Request`/
  `require_platform_auth`) у `skills.py`/`teams.py`. −33 рядки дублювання, +1 generic
  proxy-хелпер (консистентно з `register_tools_{list,get,spawn,post_call}`).
- **Верифіковано:** `mypy gateway/app` ✅ 69 файлів (0 помилок),
  `pytest gateway/tests/test_platform_{jobs,plans,skills,teams}.py test_platform.py`
  ✅ 39/39, повний `pytest gateway/tests` — без регресій.

### Прохід 2026-06-07 (другий)
- **B (частково):** `jobs_list`/`plans_list` рефакторено на `register_tools_list` —
  −20 рядків boilerplate, `mypy gateway/app` ✅ 69, `pytest gateway/tests` ✅ 227/227
  (без регресій). Решта `jobs.py`/`plans.py` лишена кастомною — обґрунтовано
  (різні сигнатури/dispatch, форсування ускладнило б `proxy.py` більше, ніж зекономило).
- **C:** підтверджено — `tools/app/routes/improve.py` має лише явні API-ендпоінти
  (`/improve/{scan,status,pending,review,export}`), жодного `JOB_TYPES`/cron-запису.
  Це навмисний human-in-the-loop дизайн. Додано **ADR-008** у
  `docs/PLATFORM_ROADMAP.md` ("Self-improve scan — навмисно ручний тригер"),
  щоб зафіксувати рішення і не дати майбутній ітерації "автоматизувати" його помилково.

### Прохід 2026-06-07 (третій)
- **Новий refactor (виявлено самостійно, не з попереднього списку):** знайшов
  `uid = int(user_id) if user_id is not None else auth.user_id` (і `body.user_id`
  варіант) повторений **16 разів у 9 файлах** `gateway/app/platform/*.py`
  (jobs, memory, orchestrator, plans, proxy, research, skills, subagents, teams).
  Виніс у `resolve_uid(auth: PlatformAuth, user_id: int | None) -> int` в `auth.py`
  (поряд з `PlatformAuth` — природне місце, бо це саме "як інтерпретувати auth.user_id
  vs явний override"). Замінив усі 16 входжень. `mypy gateway/app` ✅ 69 файлів,
  `pytest gateway/tests` ✅ 227/227 — без регресій. −16 рядків дублювання,
  +1 точка для майбутніх змін логіки (напр. якщо колись знадобиться обмежити,
  хто саме може запитувати "від імені" іншого user_id).

### Прохід 2026-06-07 (четвертий) — "очищуй"
- **Знайдено форматинг-артефакт:** 9 файлів `gateway/app/platform/*.py`
  (`connectors`, `hooks`, `mcp`, `orchestrator`, `research`, `skills`, `subagents`,
  `teams` + частково `__init__`) мали **60–70% порожніх рядків** — порожній рядок
  після майже кожного оператора/імпорту/поля класу (схоже на артефакт автогенерації
  чи невдалого автоматичного редагування). Приклад: `teams.py` — 86 рядків, з них 53
  порожні, по одному порожньому рядку між `task: str` і `budget_per_role: int = 3`
  усередині того самого `class TeamBody`.
- **Перероблено всі 9 файлів** на чистий PEP8-форматинг (логіка/код побайтово той
  самий — лише прибрано зайві порожні рядки): `connectors.py` 20→10,
  `hooks.py` 20→10, `mcp.py` 20→10, `teams.py` 86→43, `skills.py` 86→43,
  `orchestrator.py` 65→32, `research.py` 65→32, `subagents.py` 65→32 рядків.
  Сумарно **−286 рядків** шуму.
- **Верифіковано:** `mypy gateway/app` ✅ 69 файлів, повний `pytest gateway/tests`
  ✅ 227/227 (exit code 0, без регресій) — підтверджує, що зміни суто форматингові.
