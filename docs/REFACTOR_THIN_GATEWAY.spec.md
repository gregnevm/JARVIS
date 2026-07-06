# Специфікація: Великий рефакторинг «Тонкий шлюз» (Hexagon 2.0)

> Цикл: Specify → Plan → Tasks → Implement. Виконується kaizen-лупом як квартальна програма
> (кандидат на новий OKR після закриття попереднього на 100%, цикл 19).
> Статус: draft · Дата: 2026-07-06 · Автор: CTO-аудит

## 1. Specify

- **Мета (навіщо):** зняти накопичену *випадкову складність* у gateway і довести архітектуру до
  власного ж принципу S3 («gateway робить лише I/O, мозок у tools/`jarvis_core`»). Після
  рефакторингу: повний `pytest gateway/tests` проходить локально без hang-у, внутрішній RPC —
  одна точка істини, автопілот-логіка живе в ядрі, конфіг і env-доки не дрейфують.

- **Проблема зараз (верифіковано аудитом 2026-07-06):**
  1. **Стартап-I/O в lifespan:** `gateway/app/main.py:152` — `await register_bot_ui(...)`
     безумовно б'є Telegram API (setMyCommands/Description/MenuButton); + `set_webhook` у
     webhook-mode; + до 7 фонових тасок стартують одразу. Наслідок: TestClient висне локально →
     повний прогін тестів gateway можливий лише на CI (петля зворотного зв'язку = хвилини→години).
  2. **Рукописний внутрішній RPC:** 26 входжень `httpx.AsyncClient(` у 19 файлах gateway
     (client_api/*, platform/*, projects.py, services.py, openai_api.py, admin_panel.py…) поруч
     із «правильним» шаром `tools_client_*.py` (~1 209 LOC міксинів). Два конкуруючі патерни,
     різнобій таймаутів/помилок, кожен новий проксі-ендпоїнт = копіпаст.
  3. **Мозок у каналі (S3-дірка):** `gateway/app/auto_coroutine.py` (460 LOC, стейт-машина
     6-фазного автопілота) — чиста логіка без gateway-залежностей (імпортує лише
     `jarvis_core.okr` + stdlib), але живе в gateway. Аналогічно: redaction/store-building у
     `client_api/context.py`, два паралельні auth-резолвери
     (`client_api/deps.py::resolve_client_context` vs `platform/auth.py::require_platform_auth`),
     дубль хелпера `_uid()` у `client_api/apps.py` і `client_api/context.py`.
  4. **Конфіг-розповзання:** 121 env-змінна в `.env.example`; gateway config = 73 поля,
     tools = 104; ~11 змінних читаються у 2–3 сервісах (redis_url, ollama_host, data_dir,
     twin_url, memory_url, admin/allowed/computer-ids…). `.env.example` і `ENV_CHECKLIST.md`
     синхронізуються руками (D1 — вручну).
  5. **Гігієна артефактів:** kaizen-паспорти накопичуються в git (166 файлів / ~356K, +~200/тиждень
     при щоденних вікнах); ruff/секрет-скану в CI нема (єдиний статичний гейт — mypy strict).

- **Не-цілі (out of scope):**
  - ❌ Розпил tools на кілька сервісів (P6 YAGNI — болю нема, оверхед є).
  - ❌ LangGraph/CrewAI/Celery/FastStream (заборонено AGENTS.md §6).
  - ❌ SPA-переписування `platform.html` (окремий трек CL, не цей рефакторинг).
  - ❌ Рефакторинг hostagent-моноліта (1k LOC, host-trusted, стабільний).
  - ❌ Зміна зовнішніх контрактів: `/v1/*`, `/api/v1/*`, `/platform/*`, Telegram-flow — байт-у-байт.

- **Обмеження:**
  - Кожен PR — атомарний, зелений (mypy strict + pytest по-сервісно), мерджиться окремо;
    репо ніколи не в зламаному стані (правило kaizen).
  - Self-hosted не ламається (S2): жодних нових обов'язкових env; нові прапори — safe-default.
  - Doc-sync у тому ж PR (D1): roadmap-чекбокси, `.env.example`, цей spec.
  - Сумісність тестів: наявні 521 gateway-тест мають лишитися зеленими без переписування задумів
    (правки лише в фікстурах/wiring).

- **Критерії прийняття:**
  - [ ] `pytest gateway/tests` повністю проходить **локально** (Windows, без мережі) < 5 хв.
  - [ ] У lifespan немає жодного безумовного мережевого `await` до зовнішніх API; BotFather-UI
        реєструється фоновою best-effort таскою з таймаутом (лог warning при фейлі, не падіння).
  - [ ] `grep httpx.AsyncClient gateway/app` → лише виділені клієнти-адаптери
        (telegram/whisper/tts/tools_client_base + ≤2 обґрунтовані винятки); проксі-модулі
        client_api/* і platform/* використовують спільний helper.
  - [ ] `from jarvis_core.autopilot import plan_cycle, render_dashboard, run_cycle` працює;
        `gateway/app/auto_coroutine.py` — лише thin-лупер/wiring (< 80 LOC) або видалений.
  - [ ] Один auth-резолвер у `jarvis_core` (або спільному модулі gateway) з двома тонкими
        адаптерами; функція `_uid()` існує в одному місці.
  - [ ] `.env.example` + `docs/ENV_CHECKLIST.md` генеруються скриптом з code-first джерела;
        CI падає, якщо згенероване ≠ закомічене (drift-гейт).
  - [ ] Retention-політика паспортів: у git лишаються останні N=50 + агрегатний summary;
        старші архівуються (`data/artifacts/self-improve/archive/*.tar.gz` поза git або LFS).
  - [ ] ruff (базовий профіль) + gitleaks у CI-matrix; обидва зелені.

- **Файли/модулі в скоупі:**
  - `gateway/app/main.py` (lifespan → composition root), `gateway/app/bot_ui.py` (реєстрація UI)
  - `gateway/app/client_api/*`, `gateway/app/platform/*`, `gateway/app/services.py`,
    `gateway/app/projects.py`, `gateway/app/openai_api.py`, `gateway/app/admin_panel.py`
  - `gateway/app/tools_client_*.py` → фасади над спільним helper-ом
  - `gateway/app/auto_coroutine.py` → `jarvis_core/autopilot/`
  - `gateway/app/client_api/deps.py` + `gateway/app/platform/auth.py` → спільний резолвер
  - `jarvis_core/` (нові: `service_client.py` або `http/`, `autopilot/`, `settings/`)
  - `gateway/app/config.py`, `tools/app/config.py`, `memory/app/config.py`, `twin/app/config.py`
    (композиція з `jarvis_core/settings/`), `.env.example`, `docs/ENV_CHECKLIST.md`, `scripts/`
  - `.github/workflows/ci.yml` (ruff, gitleaks, env-drift гейт)
  - `data/artifacts/self-improve/` (retention), `.gitignore`/`.gitattributes`

## 2. Plan

П'ять воркстрімів, у порядку ICE (Impact × Confidence ÷ Effort). Кожен = 1–2 kaizen-вікна,
кожне вікно — мерджабельні PR-и.

1. **R1 · Composition root і чистий старт.** Розділити wiring (чисте створення клієнтів/стейту)
   і ефекти (мережа, фонові таски). `register_bot_ui` і `set_webhook` → фонова best-effort
   таска з таймаутом (як `apk_autodeliver`); прапор `GATEWAY_STARTUP_NET=false` (safe-default
   true у проді, false у тестових фікстурах) глушить усі стартові мережеві дії. Фікс
   TestClient-hang → знімає пам'ятку «повний ган лише на CI».
   *Ризик мінімальний: поведінка в проді ідентична, зміна лише в порядку/умовності запуску.*

2. **R2 · Один внутрішній RPC-helper.** `jarvis_core/service_client.py`:
   `async def call(base_url, method, path, *, json=None, timeout=..., headers=..., ctx=...)` з
   уніфікованим error-envelope, ретраями й X-JARVIS-* заголовками. Міграція 19 файлів gateway
   на нього механічна (по модулю за PR). `tools_client_*` міксини стають типізованими фасадами
   над helper-ом (зовнішній інтерфейс для викликачів не змінюється).

3. **R3 · Мозок у ядро (S3).** (a) `auto_coroutine` стейт-машина → `jarvis_core/autopilot/`
   (перенос майже дослівний — залежностей від gateway нема; тести `test_auto_coroutine` — 21 шт —
   переїжджають у `jarvis_core/tests`). (b) Redaction/store-building з `client_api/context.py` →
   `jarvis_core.passport`. (c) Єдиний auth-резолвер (`RequestContext` уже спільний) + прибрати
   дубль `_uid()`. Gateway після цього — справді канали: Telegram, HTTP API, platform-HTML,
   chrome-міст.

4. **R4 · Config SSOT.** `jarvis_core/settings/` з композитними блоками
   (`RedisCfg`, `OllamaCfg`, `ServiceUrls`, `ComputerCfg`, `AuthIdsCfg`); сервісні `config.py`
   збирають потрібні блоки (pydantic-settings, env-імена не змінюються — сумісність .env 100%).
   Скрипт `scripts/gen_env_docs.py` генерує `.env.example` + таблицю `ENV_CHECKLIST.md` з
   докстрінгів полів; CI-гейт на drift.

5. **R5 · Гігієна і дешеві гейти.** Retention паспортів (keep-50 + архів; правка kaizen-профілю,
   щоб сам ротував); ruff (E/F/I + isort-профіль, без стилістичних воєн) і gitleaks у CI;
   опційно `pytest --cov` артефактом. Extension: мінімальний smoke (jest на `isFailure`/schema-парсер)
   — без Playwright поки.

**Мітигація ризиків міграції RPC (R2):** порядок — спершу helper + тести на нього, потім по
одному модулю за PR зі снапшот-порівнянням поведінки (наявні module-level тести вже покривають
handler-и напряму). Відкат — revert одного PR, бо міграція помодульна.

## 3. Tasks

- [x] **R1.1** Витягти `register_bot_ui`/webhook-setup у best-effort фонову таску з таймаутом 10s
- [x] **R1.2** Прапор `GATEWAY_STARTUP_NET` (+ .env.example, ENV_CHECKLIST) — глушить стартову мережу
- [x] **R1.3** Фікстура тестів: дефолтно `startup_net=false`; прибрати обхідні милиці з conftest
- [ ] **R1.4** Верифікація: повний `pytest gateway/tests` локально < 5 хв (записати в AGENTS.md §5)
- [ ] **R2.1** `jarvis_core/service_client.py` + юніт-тести (ретраї, таймаути, error-envelope)
- [ ] **R2.2–R2.6** Міграція: client_api/* → platform/* → services/projects → openai_api/admin_panel
      → tools_client_base (по PR на групу)
- [ ] **R2.7** Гейт: grep-перевірка в CI (список дозволених місць `httpx.AsyncClient`)
- [ ] **R3.1** `jarvis_core/autopilot/` (перенос stage machine + 21 тест)
- [ ] **R3.2** Gateway-лупер → thin wiring поверх ядра
- [ ] **R3.3** Redaction/store-building → `jarvis_core.passport`; context.py — лише I/O
- [ ] **R3.4** Єдиний auth-резолвер + адаптери client_api/platform; вбити дубль `_uid()`
- [ ] **R4.1** `jarvis_core/settings/` блоки + міграція gateway/tools config (env-імена незмінні)
- [ ] **R4.2** `scripts/gen_env_docs.py` + CI drift-гейт; згенерувати .env.example/ENV_CHECKLIST
- [ ] **R5.1** Retention паспортів (kaizen-профіль ротує; архів поза git)
- [ ] **R5.2** ruff + gitleaks у CI (базові профілі)
- [ ] **R5.3** Extension: jest-smoke на background.js хелпери
- [ ] Тести під усі критерії прийняття §1

## 4. Implement

*(заповнюється по ходу kaizen-вікон: посилання на PR-и, відхилення від плану, нотатки для рев'ю)*

- **2026-07-06 · R1 (R1.1–R1.3)** — гілка `claude/tg-r1-composition-root`: lifespan розділено на
  wiring (чисте створення клієнтів/стейту) та умовні ефекти; webhook + BotFather-UI → best-effort
  фонова таска `_startup_net` (wait_for 10s, warning при фейлі, `/health` → `bot_ui_registered`);
  `GATEWAY_STARTUP_NET` глушить і поллери (reminders/health-watch/job-runners/autopilot/apk).
  Autouse-фікстура `_no_startup_net` у conftest; милиця `health_watch_interval=0` прибрана.
  Відхилення: `asyncio.wait_for` замість `asyncio.timeout` (локальний dev-Python 3.10).
  Перший повний локальний прогін: **проходить** (раніше — hang), ~7 хв на холодному старті —
  до критерію < 5 хв див. R1.4.

## Ризики й відкат

- **Ризик:** регресія стартап-поведінки в проді (R1: webhook не зареєструвався тихо) →
  **Мітигація:** best-effort таска логує ERROR + health-endpoint показує `bot_ui_registered`;
  відкат = один revert.
- **Ризик:** тонкі розбіжності таймаутів/помилок після міграції на спільний helper (R2) →
  **Мітигація:** helper приймає per-call timeout (переносимо наявні значення 1:1), міграція
  помодульна, наявні тести — регресійна сітка.
- **Ризик:** перенос autopilot ламає import-шляхи автопілота в проді (R3) →
  **Мітигація:** тимчасовий re-export shim у старому модулі на 1 реліз; смок через
  `AUTO_COROUTINE_ENABLED` на стенді до видалення shim-а.
- **Ризик:** config-міграція змінює семантику env (R4) → **Мітигація:** env-імена й дефолти
  фіксуються тестом-снапшотом «settings до/після» перед мерджем.
- **Ризик:** retention зачепить аудиторський слід (R5) → **Мітигація:** архів створюється до
  видалення з git; summary.json тримає агрегат за весь час.
