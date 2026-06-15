# JARVIS — Agent Mode & Computer Use Roadmap

> **Версія:** 1.0 (2026-06-11)  
> **Статус:** Living document — оновлюється після кожного milestone.  
> **Мета:** довести `AGENT_MODE=computer` від «обмеженого пульта з Telegram» до **справжнього Agent Mode** з повноцінним керуванням Windows-хостом — безпечно, автономно, з прозорим аудитом.

> **Місце в ієрархії:** трек **desktop-керування** під парасолькою [`docs/PRODUCT_ROADMAP.md`](PRODUCT_ROADMAP.md).
> Host-agent FS/PS/UIA, який тут будується, — фундамент під **Стовп B** (coding-агент, [`CODING_AGENT_ROADMAP.md`](CODING_AGENT_ROADMAP.md) CA-1). Принципи — [`AGENTS.md`](../AGENTS.md).

**Пов’язані документи**

| Документ | Роль |
|----------|------|
| [`AGENTS.md`](../AGENTS.md) | Статут: принципи (S4 confirm, S5 tier-ladder), цілі |
| [`docs/PRODUCT_ROADMAP.md`](PRODUCT_ROADMAP.md) | **Парасолька** — фундамент (Computer Use) + 3 стовпи |
| [`docs/CODING_AGENT_ROADMAP.md`](CODING_AGENT_ROADMAP.md) | Стовп B — споживач host-agent (diff-edit, test-loop) |
| [`docs/COMPUTER_USE.md`](COMPUTER_USE.md) | Архітектура tier ladder, host-agent контракт (C0–C6) |
| [`ROADMAP.md`](../ROADMAP.md) | Короткий ops-backlog (M/N/E/S) |
| [`docs/PLATFORM_ROADMAP.md`](PLATFORM_ROADMAP.md) | `/platform` Workbench, Planning, Jobs |
| [`docs/COMPUTER_ROLLBACK.md`](COMPUTER_ROLLBACK.md) | Runbook відкату шкоди |
| [`docs/ENV_CHECKLIST.md`](ENV_CHECKLIST.md) | Операційний чеклист `.env` |
| [`docs/THREAT_MODEL.md`](THREAT_MODEL.md) | Модель загроз |

---

## 1. Позиціонування

### 1.1 Що таке Agent Mode у JARVIS

| Режим | Модель | Інструменти | Призначення |
|-------|--------|-------------|-------------|
| `chat` | CHAT | — | Швидкі відповіді без tools |
| `agent` | AGENT | calc, web, notes, reminders, image, MCP… | Інтернет + файли + памʼять |
| `hybrid` | евристика | як вище | Дефолт: розумна маршрутизація |
| **`computer`** | AGENT | **+ host-agent** (PS, CLI, FS, browser, UIA, screen) | Керування Windows-хостом |

Computer Use — не окремий продукт, а **надбудова** над наявним тул-лупом (`tools/app/agent.py` → `AgentRunner._agent`).

### 1.2 North Star (Agent Mode)

> Пишу в Telegram: *«Відкрий VS Code, знайди помилку в тестах, виправ і запусти pytest»* — агент сам обирає tier (cursor_task → PS → CLI), показує план, після одного ✅ виконує 5–15 кроків, звітує зі скрінами й логами. Я можу зупинити в будь-який момент. Увесь шлях — в `computer.jsonl`.

### 1.3 Capability ladder (принцип, не змінюється)

```
T0  PowerShell / FS / clipboard / cursor_task / continue_dev  — найпряміше
T1  CLI (git, winget, curl, python …)                         — готові утиліти
T2  Playwright (DOM, селектори)                               — веб без пікселів
T3  UI Automation (вікна, контроли за ім’ям)                  — десктоп-застосунки
T4  Screenshot → vision → click/type                          — останній резерв
```

Агент **ніколи не клікає мишею**, якщо задачу можна зробити пряміше. Це вшито в промпт і аудит (tier у `computer.jsonl`).

---

## 2. Baseline (стан на 2026-06-11)

### 2.1 Реалізовано (інфраструктура ✅)

| Компонент | Фаза | Файли / ендпойнти |
|-----------|------|-------------------|
| host-agent на Windows | C0 | `hostagent/` — `/health`, `/powershell`, `/cli`, `/fs/*` |
| Toolkit T0/T1 | C1 | `run_powershell`, `run_cli`, `fs_*` |
| Confirm + audit | C2 | `cmp:Y/N`, `cmpA:Y` (admin), `data/logs/computer.jsonl` |
| Browser T2 | C3 | `browser_*`, `ENABLE_BROWSER`, Playwright у tools |
| UIA lite T3 | C4 | `window_*`, `uia_invoke` (focus + Enter) |
| Admin PS | C5 | `COMPUTER_ALLOW_ADMIN`, подвійне підтвердження |
| Vision / screen | C6 частково | `capture_screenshot`, `describe_image`, `/see`, `screen_click` |
| Trust model | 2.5 | `computer_access.py`, rate limit, `computer_learned.json` |
| Resume після confirm | — | `gateway/app/agent_turn.py` → `computer_resume` |
| Cascade routing | — | `jarvis_core.routing.cascade` → hybrid → computer |
| Coding bridges | P12 | `cursor_task`, `continue_dev` |
| Platform Workbench | P0 | SSE stream + computer confirm у `/platform` |
| Planning mode | P3 | plan → approve → execute (загальний, не computer-specific) |
| Background jobs | P2 | `cursor_task`, `subagent`, `deep_research` |

### 2.2 Оцінка зрілості (чесно)

| Критерій | Оцінка | Коментар |
|----------|--------|----------|
| Архітектура | **8/10** | host-agent + tier ladder — правильний фундамент |
| Покриття OS API | **5/10** | UIA примітивний; немає keyboard/scroll/drag |
| Автономність | **4/10** | confirm-per-action; 8 ітерацій; Telegram-only UX |
| Планування | **5/10** | P3 Planning є, але не інтегрований у computer loop |
| Модель | **5/10** | qwen2.5:7b — слабка для складних multi-step desktop |
| Безпека | **8/10** | whitelist, audit, owner gate — добре за замовчуванням |
| Промпт ↔ код | **3/10** | `system_computer()` каже «browser/UIA недоступні», хоча tools є |
| UX | **5/10** | Mini App `/app/ps`, але немає live desktop console |

### 2.3 Відомі розриви (gap list)

| # | Gap | Вплив |
|---|-----|-------|
| G1 | `system_computer()` суперечить `agent_tool_schemas()` | Модель не використовує T2–T4 або галюцинує |
| G2 | `see_screen` не в тул-лупі (лише `/see` API) | Vision не в автономному циклі агента |
| G3 | UIA = focus + Enter, не pywinauto | Excel, діалоги, кнопки за ім’ям — не працюють |
| G4 | Немає `screen_type`, hotkeys, scroll | T4 неповний |
| G5 | Немає vision→координати loop | «Подивись і клікни» — вручну |
| G6 | PS whitelist блокує `\|`, `&&`, складні скрипти | T0 обмежений для power users |
| G7 | `ENABLE_*` вимкнені за замовчуванням | «Повний доступ» потребує 10+ змін у `.env` |
| G8 | Confirm на кожну мутуючу дію | Багатокрокові сценарії — багато ✅ у Telegram |
| G9 | `COMPUTER_MAX_ITERS=8` | Складні workflow обриваються |
| G10 | Немає computer-specific task runner | Довгі задачі без progress/cancel |
| G11 | `HOSTAGENT_FS_ROOTS` може обрізати ФС | Не «весь диск» без явної конфігурації |

---

## 3. Фази розвитку

Загальна схема залежностей:

```
Фаза AM-0 (швидкі фікси) ──► AM-1 (desktop control) ──► AM-2 (автономність)
         │                           │                          │
         └───────────────────────────┴──────────────────────────┘
                                     ▼
                          AM-3 (архітектура «як Cursor для ОС»)
                                     │
                                     ▼
                          AM-4 (policy + editions + KPI)
```

---

## Фаза AM-0 — Вирівнювання та профілі · **наступний спринт (1–2 тижні)**

**Мета:** прибрати суперечності, зменшити friction, дати передбачувані пресети без зміни архітектури.

| # | Задача | DoD | Пріоритет | Статус |
|---|--------|-----|-----------|--------|
| AM-0.1 | **Динамічний `system_computer()`** — перелік tools/tier з `agent_tool_schemas(computer=True)` | Промпт відображає реальні `ENABLE_*`; тест у `test_computer_profile.py` | P0 | [x] |
| AM-0.2 | **`see_screen` як tool** у computer mode | Схема + dispatch + confirm tier read-only | P0 | [x] |
| AM-0.3 | **`COMPUTER_PROFILE`** пресет: `safe` \| `standard` \| `full` | `safe`=PS+FS; `standard`+browser+UIA; `full`+screen+vision; документація в `.env.example` | P0 | [x] |
| AM-0.4 | Розширити **hybrid `_COMPUTER_RE`** | «відкрий Excel», «що на екрані», «натисни кнопку», «cursor:» → computer | P1 | [x] |
| AM-0.5 | **`COMPUTER_SESSION_TRUST_MINUTES`** | Після ✅ — session trust T0/T1; cmp:YT = full trust | P1 | [x] |
| AM-0.6 | Підняти дефолт **`COMPUTER_MAX_ITERS`** до 12 | Config + README; cap у `_max_iters` | P2 | [x] |
| AM-0.7 | **Smoke matrix** у `verify_stack.ps1` | host-agent + screenshot + PS read + profile/vision | P1 | [x] |
| AM-0.8 | Документ **«Standard Agent Mode»** у README | Блок `.env` для типового single-user сетапу | P2 | [x] |

**Вихід AM-0:** увімкнув `COMPUTER_PROFILE=standard` — агент знає свої tools, vision у лупі, менше ручних confirm.

---

## Фаза AM-1 — Повноцінний desktop control · **4–6 тижнів**

**Мета:** T3/T4 стають реально корисними; агент керує десктопом, не лише PS/CLI.

### AM-1.1 Input toolkit (host-agent)

| # | Задача | DoD | Статус |
|---|--------|-----|--------|
| AM-1.1.1 | `POST /screen/type` `{text, interval?}` | SendKeys / clipboard paste для довгих рядків | [x] |
| AM-1.1.2 | `POST /screen/hotkey` `{keys[]}` | Ctrl+S, Alt+Tab тощо | [x] |
| AM-1.1.3 | `POST /screen/scroll` `{clicks, x?, y?}` | Колесо миші | [x] |
| AM-1.1.4 | Toolkit: `screen_type`, `screen_hotkey`, `screen_scroll` | Схеми + dispatch + confirm T4 | [x] |
| AM-1.1.5 | Contract tests host-agent ↔ tools | `hostagent_contract.py` + `test_screen_input.py` | [x] |

### AM-1.2 Справжній UIA (T3)

| # | Задача | DoD | Статус |
|---|--------|-----|--------|
| AM-1.2.1 | Залежність `pywinauto` або `uiautomation` у hostagent | Windows-only optional deps | [ ] |
| AM-1.2.2 | `GET /uia/tree?window=` — дерево контролів (обрізане) | JSON для моделі | [ ] |
| AM-1.2.3 | `POST /uia/find` + `POST /uia/click` + `POST /uia/set_value` | За `name` / `automation_id` | [ ] |
| AM-1.2.4 | Замінити lite `uia_invoke` або зберегти як fallback | ADR у `docs/adr/` | [ ] |
| AM-1.2.5 | Golden trace: Notepad «введи текст і збережи» | `tools/tests/golden/` | [ ] |

### AM-1.3 Vision-action loop (C6 повний)

| # | Задача | DoD | Статус |
|---|--------|-----|--------|
| AM-1.3.1 | Tool **`observe_screen`** → screenshot + vision JSON `{summary, elements[]}` | Структурована відповідь, не лише prose | [ ] |
| AM-1.3.2 | **`act_on_screen`** — click/type за координатами або element id | Max 3 retry в одній ітерації лупа | [ ] |
| AM-1.3.3 | VRAM policy: `OLLAMA_VISION_ON_DEMAND` + unload agent | Документовано для RX 5700 XT 8GB | [ ] |
| AM-1.3.4 | Заборона T4, якщо vision model не задана | Graceful message агенту | [ ] |

### AM-1.4 FS і шляхи

| # | Задача | DoD | Статус |
|---|--------|-----|--------|
| AM-1.4.1 | Документувати **`HOSTAGENT_FS_ROOTS`** для «повного» профілю | `C:\`, `O:\JARVIS`, user profile | [ ] |
| AM-1.4.2 | `fs_glob` / `fs_search` (обмежений glob) | Read-only, ліміт entries | [ ] |

**Вихід AM-1:** ≥70% desktop-задач через T0–T3; T4 лише для canvas/legacy UI.

---

## Фаза AM-2 — Автономність і довгі задачі · **6–10 тижнів**

**Мета:** один ✅ на план; фонові computer-job; зупинка з Telegram/Platform.

### AM-2.1 Computer Planning (інтеграція P3)

| # | Задача | DoD | Статус |
|---|--------|-----|--------|
| AM-2.1.1 | `POST /agent/computer/plan` — steps з tier, risk, mutating flag | JSON schema | [ ] |
| AM-2.1.2 | Confirm **плану** одним ✅ (не кожен крок) | Redis TTL як P3 plans | [ ] |
| AM-2.1.3 | Execute plan step-by-step з progress у Telegram | editMessageText / Platform Jobs | [ ] |
| AM-2.1.4 | Dry-run mode: показати план без виконання | `/computer plan --dry` | [ ] |

### AM-2.2 Computer Task Runner

| # | Задача | DoD | Статус |
|---|--------|-----|--------|
| AM-2.2.1 | bg job type **`computer_task`** | Redis queue + worker | [ ] |
| AM-2.2.2 | Progress: `{step, total, last_tool, last_result_preview}` | Platform Jobs tab + TG status | [ ] |
| AM-2.2.3 | **Cancel / pause** — `POST /bgjobs/{id}/cancel` | host-agent noop safe | [ ] |
| AM-2.2.4 | **Observation buffer** — останні N tool results + 1 screenshot | Контекст для наступних ітерацій | [ ] |

### AM-2.3 Trust zones (розширення confirm)

| # | Задача | DoD | Статус |
|---|--------|-----|--------|
| AM-2.3.1 | Zone 0: read-only без confirm (screenshot, fs_read, browser_read, uia/tree) | Config map у `computer_confirm.py` | [ ] |
| AM-2.3.2 | Zone 1: session trust (AM-0.5) | Redis key `computer:trust:{user_id}` | [ ] |
| AM-2.3.3 | Zone 2: GUI actions — confirm plan | AM-2.1 | [ ] |
| AM-2.3.4 | Zone 3: admin/power — double confirm (існує) + audit tier `admin` | Без змін C5 | [x] |
| AM-2.3.5 | **`COMPUTER_EMERGENCY_STOP`** — глобальний kill switch | Redis flag; tools відхиляють mutating | [ ] |

### AM-2.4 Модель і ітерації

| # | Задача | DoD | Статус |
|---|--------|-----|--------|
| AM-2.4.1 | Рекомендований **`OLLAMA_MODEL_AGENT=14b+`** для computer | README + hardware_profile.json | [ ] |
| AM-2.4.2 | Опційний **cloud planner** (OpenAI API / Cursor) лише для plan step | `ENABLE_COMPUTER_CLOUD_PLANNER` | [ ] |
| AM-2.4.3 | LoRA fine-tune на computer traces | Датасет з `computer.jsonl` + sessions | [ ] |

**Вихід AM-2:** задача на 10–20 кроків виконується з одним підтвердженням плану; користувач бачить progress і може зупинити.

---

## Фаза AM-3 — Agent Console та спостережуваність · **8–12 тижнів**

**Мета:** Telegram — канал команд; **Desktop Agent Console** — канал спостереження.

| # | Задача | DoD | Статус |
|---|--------|-----|--------|
| AM-3.1 | **Platform tab «Computer»** | Live tail `computer.jsonl`, останній screenshot, active job | [ ] |
| AM-3.2 | SSE stream tool trace для computer mode (як Workbench) | tier + args preview + result | [ ] |
| AM-3.3 | **Session replay** — кроки computer-задачі з timestamps | З `sessions.jsonl` + computer audit | [ ] |
| AM-3.4 | Mini App `/app/ps` — parity з Platform Computer tab | Єдиний API | [ ] |
| AM-3.5 | Локальний **tray indicator** (опційно) | host-agent icon: idle / working / confirm pending | [ ] |
| AM-3.6 | Windows Service для host-agent (NSSM) + health watchdog | Autostart + auto-restart on crash | [ ] |

**Вихід AM-3:** повна прозорість дій агента на хості без читання логів у терміналі.

---

## Фаза AM-4 — Policy engine та editions · **паралельно з AM-2/3**

**Мета:** замість flat whitelist — керовані політики; чіткі edition boundaries.

### AM-4.1 Policy engine

| # | Задача | DoD | Статус |
|---|--------|-----|--------|
| AM-4.1.1 | `data/computer_policy.json` — rules per user/zone/app | JSON schema + validator | [ ] |
| AM-4.1.2 | Rules: `allow_paths`, `deny_paths`, `allow_apps`, `max_file_bytes` | Enforce у tools + hostagent | [ ] |
| AM-4.1.3 | Per-app mode: `browser_only`, `jarvis_repo_only`, `full_desktop` | Platform UI edit | [ ] |
| AM-4.1.4 | Rollback checkpoint перед mutating FS у workspace | git stash / copy to `.jarvis_backup/` | [ ] |

### AM-4.2 Native bridges (T0 розширення)

| # | Задача | DoD | Статус |
|---|--------|-----|--------|
| AM-4.2.1 | WMI/CIM info tool (`get_system_info`) | OS, disk, GPU, running services | [ ] |
| AM-4.2.2 | `winget_search` / `winget_install` (confirm) | Обгортка над CLI whitelist | [ ] |
| AM-4.2.3 | COM bridge для Office (read-only спочатку) | ADR + opt-in flag | [ ] |
| AM-4.2.4 | Process manager: `list_processes`, `stop_process` (confirm) | PS whitelist extension | [ ] |

### AM-4.3 Edition matrix (оновлення)

| Edition | Agent Mode |
|---------|------------|
| **Core** | chat, agent, hybrid; без computer |
| **Pro** | + Computer Use AM-0..AM-1 (`COMPUTER_PROFILE=standard`) |
| **Studio** | + AM-2..AM-4 (`full`), LoRA computer traces, Platform Computer tab |

**Вихід AM-4:** «повний доступ до ПК» = свідомий вибір edition + policy, не випадковий `.env`.

---

## 4. Конфігураційні пресети (ціль)

### 4.1 `COMPUTER_PROFILE=safe` (за замовчуванням для нових install)

```env
ENABLE_COMPUTER_USE=true
ENABLE_BROWSER=false
COMPUTER_ALLOW_ADMIN=false
COMPUTER_ALLOW_POWER=false
COMPUTER_REQUIRE_CONFIRM=true
COMPUTER_PROFILE=safe
PS_WHITELIST=Get-ChildItem,Get-Content,Test-Path,Get-Process,Get-Service
CLI_WHITELIST=git,curl,docker,python
```

Tools: `fs_*`, `capture_screenshot`, `run_powershell`, `run_cli`, `clipboard_read`.

### 4.2 `COMPUTER_PROFILE=standard` (рекомендований для власника)

```env
COMPUTER_PROFILE=standard
ENABLE_BROWSER=true
COMPUTER_MAX_ITERS=12
COMPUTER_SESSION_TRUST_MINUTES=10
OLLAMA_MODEL_VISION=llava:7b
COMPUTER_AUTO_VISION=true
HOSTAGENT_FS_ROOTS=C:\Users\you,O:\JARVIS
```

+ browser_*, window_*, uia_*, see_screen tool, cursor_task.

### 4.3 `COMPUTER_PROFILE=full` (power user, один trusted owner)

```env
COMPUTER_PROFILE=full
# + screen_type, screen_hotkey, observe_screen, act_on_screen
# COMPUTER_ALLOW_ADMIN=false  # admin лишається окремим свідомим кроком
COMPUTER_MAX_ITERS=15
```

---

## 5. KPI та метрики успіху

| KPI | Baseline (2026-06) | Ціль AM-0 | Ціль AM-2 | Як міряти |
|-----|-------------------|-----------|-----------|-----------|
| Computer task success rate | ~85% (whitelist tasks) | 90% | 95% | `computer.jsonl` outcome |
| Avg confirms per 5-step task | ~5 | 3 | 1 (plan) | audit + Redis |
| P95 computer turn (warm) | ~20–30 с | <25 с | <20 с | `tools/app/metrics.py` |
| T4 usage share | <5% | <5% | <3% | tier у audit |
| Vision VRAM OOM rate | ? | <1% | <1% | ollama logs |
| User abort rate | ? | baseline | ↓30% | cancel job count |
| False prompt (hallucinated tool) | є (G1) | 0 | 0 | golden traces |

---

## 6. Пріоритетна черга — наступні 4 тижні

```
Тиждень 1 — AM-0 foundations
  ① AM-0.1: динамічний system_computer()
  ② AM-0.2: see_screen у toolkit
  ③ AM-0.3: COMPUTER_PROFILE пресети

Тиждень 2 — friction + routing
  ④ AM-0.4: розширити hybrid computer heuristics
  ⑤ AM-0.5: session trust (Redis TTL)
  ⑥ AM-0.7: smoke matrix у verify_stack

Тиждень 3 — AM-1 start (host-agent input)
  ⑦ AM-1.1.1–1.1.4: screen_type, hotkey, scroll
  ⑧ Contract tests + документація HOSTAGENT_FS_ROOTS

Тиждень 4 — UIA spike
  ⑨ AM-1.2.1–1.2.3: pywinauto POC (Notepad + Calculator)
  ⑩ Golden trace + оновити COMPUTER_USE.md статус
```

---

## 7. Залежності та ризики

| Ризик | Ймовірність | Мітигація |
|-------|-------------|-----------|
| VRAM 8GB — agent + vision | Висока | `OLLAMA_VISION_ON_DEMAND`, on-demand unload |
| LLM слабко планує desktop | Висока | 14b model, cloud planner opt-in, P3 planning |
| UIA крихкий на різних DPI/locales | Середня | T0/PS fallback, golden traces |
| Security incident (mutating PS) | Низька при defaults | policy engine, emergency stop, audit |
| Telegram UX для 20-step task | Висока | Platform Computer tab + bg jobs |
| pywinauto deps на host | Середня | optional install, graceful degrade to lite UIA |

---

## 8. Архітектурні рішення (ADR — заплановані)

| ADR | Питання | Статус |
|-----|---------|--------|
| ADR-AM-001 | `COMPUTER_PROFILE` vs окремі `ENABLE_*` flags | [ ] draft |
| ADR-AM-002 | pywinauto vs uiautomation vs PowerShell-only UIA | [ ] draft |
| ADR-AM-003 | Plan-level confirm vs session trust vs per-action | [ ] draft |
| ADR-AM-004 | Vision structured output (JSON) vs free text | [ ] draft |
| ADR-AM-005 | Cloud planner для computer (opt-in) | [ ] draft |

---

## 9. Свідомо не робимо

- **Повний admin-shell за замовчуванням** — `COMPUTER_ALLOW_ADMIN=false` залишається
- **Автоматичний screen_click без vision або UIA** — T4 лише з observe step
- **Computer Use у Docker на Windows** — host-agent лишається на хості (DESIGN)
- **Заміна Telegram на єдиний канал** — TG лишається primary; Platform — console
- **Auto-confirm для admin/power** — завжди double confirm (C5)
- **Перепис agent loop на LangGraph/CrewAI** — поточний `AgentRunner._agent` достатній

---

## 10. Мапінг на існуючі roadmap-и

| Цей документ | PRODUCT_ROADMAP | PLATFORM_ROADMAP | COMPUTER_USE |
|--------------|-----------------|------------------|--------------|
| AM-0 | Фаза 2 доповнення | — | C6 polish |
| AM-1 | Фаза 2 «вихід 80%» | — | C4/C6 повний |
| AM-2 | — | P3 Planning + P2 Jobs | Confirm model v2 |
| AM-3 | — | P0 Workbench + новий tab | — |
| AM-4 | Фаза 6 editions | Edition matrix | §5 Security |

---

## 11. Історія оновлень

| Дата | Версія | Зміна |
|------|--------|-------|
| 2026-06-11 | 1.0 | Початковий розгорнутий roadmap Agent Mode (AM-0..AM-4) після аудиту зрілості |

---

*Оновлюйте чекбокси при закритті задач. Ops: [`ROADMAP.md`](../ROADMAP.md) · Архітектура tier: [`COMPUTER_USE.md`](COMPUTER_USE.md)*
