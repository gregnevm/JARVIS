# Auto-Code Coroutine — OKR-керований автономний цикл розробки

> Статус: **MVP вертикальний зріз** (default OFF). Гілка: `claude/auto-code-coroutine-okr-f595n4`.
> Корутина пише код, рев'ює, рефакторить, аналізує, тестує й **еволюціонує власний
> roadmap** — без підтверджень, але строго в межах OKR/goals та контексту адміна.

## 1. Навіщо

JARVIS уже має нативний coding-агент (`tools` — `code_edit`/`run_tests`/orchestrator),
self-improve scan (human-gate) і per-service CI. Бракувало **замкненої петлі**, яка б
сама обирала «що робити далі» з roadmap, виконувала повний цикл якості й оновлювала
цілі. Ця корутина — той замок.

Принцип — як у `context_scheduler` (ADR-008): **чиста логіка тестується ізольовано,
IO-цикл тонкий і default-off**, вмикається свідомо й під наглядом.

## 2. Цикл (6 фаз)

Кожен тік веде **одну** ціль OKR (вибір — `select_objective`) крізь:

| # | Фаза | Виконавець (прод-dispatch) | Слід |
|---|------|----------------------------|------|
| 1 | `code` | `spawn_orchestrator` — реалізує наступний пункт із `roadmap` цілі | job/run_id |
| 2 | `review` | `improve_scan` — self-improve пропозиції по діфу | N пропозицій |
| 3 | `refactor` | `spawn_orchestrator` — застосовує зауваження review | job/run_id |
| 4 | `analyze` | `repo_tree` — знімок архітектури + cleanup-нотатки | artifact |
| 5 | `test` | `create_coding_job(pytest)` — headless run & fix (`/agent/code/fix`) | job_id |
| 6 | `evolve` | `mutate_okr` — прогрес KR + пере-пріоритезація за адмін-контекстом | новий OKR |

Фаза падає → warning у лог, цикл їде далі (один збій не валить прогон). Кожен цикл
лишає `data/autopilot/run_log.md` + перегенерований `dashboard.md`.

## 3. OKR / goals + контекст адміна

`data/okr/okr.json` (схема — `jarvis_core/okr.py`):

- **Objective**: `id`, `title`, `roadmap` (джерело задач), `priority` (1..5), `status`, `key_results`.
- **KeyResult**: `progress`/`target` → нормований `ratio`; `done` коли досягнуто.
- **OKR.admin_context**: вільний текст адміна (фокус/обмеження).

**Вибір цілі** (`select_objective`): `active` + не досягнута → найменший `priority` →
найменший прогрес → `id`. **Мутація** (`mutate_okr`): дельти KR із результатів фаз +
адмін-контекст **однією фразою піднімає пріоритет** цілей, чий `id`/`title` згаданий
(напр. «зосередься на AP» → P2→P1). Так адмін перенацілює корутину без ручного JSON.

## 4. Поверхні керування

- **Platform tab** (`gateway/app/platform/autopilot.py`, `/platform/api/autopilot/*`):
  - `GET status` — прапор + інтервал + OKR;
  - `GET dashboard` — markdown-дашборд;
  - `POST okr` — мутація (admin_context / kr_deltas);
  - `POST tick` — один цикл вручну (тим самим прод-dispatch).
- **Skill** `data/skills/auto-coder/SKILL.md` — поведінка агента в циклі + правила безпеки.
- **Фоновий loop** (`auto_coroutine_loop` у lifespan `main.py`) — default OFF.

## 5. Безпека (default-off, ADR-008)

- `AUTO_COROUTINE_ENABLED=false` за замовчуванням — мутує код без підтверджень, тож
  вмикати лише свідомо.
- Застосування правок **додатково** гейтиться tools-політикою `CODING_HEADLESS_APPLY`
  (`no_confirm=True` лише запитує, реальний запис вирішує tools-бік).
- Секрети — deny-glob (`.env`/`*.pem`/`*.key`/`id_rsa`), як у `repo_grep`/`code_edit`.
- Не пушити в remote без дозволу; кожен цикл — у append-only run-log.

## 6. Конфіг (`.env`)

```
AUTO_COROUTINE_ENABLED=false              # головний рубильник
AUTO_COROUTINE_USER_ID=0                  # 0 → перший ADMIN_USER_IDS
AUTO_COROUTINE_REPO_PATH=                 # корінь репо для test/fix (порожньо → '.')
AUTO_COROUTINE_INTERVAL=3600              # сек між циклами
AUTO_COROUTINE_BYPASS_PERMISSIONS=false   # 🔓 auto-apply без підтверджень (індикатор+намір)
```

### Автономний режим (Bypass permissions)

Дзеркало режиму **«Bypass permissions»** у Claude Code — повний цикл «ось так
автоматично», без жодних підтверджень. **Один майстер-вимикач** у спільному `.env`:

| Прапор (один `.env`) | Роль |
|--------|------|
| **`BYPASS_CONFIRMATIONS=true`** | 🔓 глобально знімає ВСІ ✅/❌: мутуючі дії (fs/CLI/PS/code_edit) + headless code-apply + авто-апрув планів |
| `AUTO_COROUTINE_ENABLED=true` | запускає фоновий autopilot-loop |
| `AUTO_COROUTINE_BYPASS_PERMISSIONS=true` | індикатор+намір loop'а; `status` → `mode=bypass`, дашборд → 🔓 |

`BYPASS_CONFIRMATIONS` гейтить три точки в `tools`: `computer_confirm.wrap_execute`
(мутуючі дії), `headless.authorize_headless_apply` (CLI apply), `agent.code_plan`
(авто-апрув). Гранулярна альтернатива (без майстра): `COMPUTER_REQUIRE_CONFIRM=false`
+ `CODING_HEADLESS_APPLY=true`.

> ⚠️ Знімає підтвердження **і в інтерактиві** (не лише для autopilot). Якщо треба без
> confirm лише для autopilot — лиши майстер off і видай власнику full session-trust
> (`COMPUTER_SESSION_TRUST_MINUTES` / «Full trust» у Mini App): дії в trust-вікні без ✅.
> **Виняток:** друге admin-confirm для elevated PowerShell лишається за `COMPUTER_ALLOW_ADMIN`.

Status (`GET /platform/api/autopilot/status`) повертає `mode: bypass|supervised`;
дашборд має рядок **Режим:** 🔓/🔒. Локально перевірити: `python scripts/autopilot_run.py --bypass`.

## 7. Зроблено в цьому зрізі

- `jarvis_core/okr.py` + 15 тестів — модель, вибір, мутація, (де)серіалізація.
- `gateway/app/auto_coroutine.py` + 14 тестів — планувальник, run_cycle, dispatch,
  loop, дашборд, сховище.
- Platform tab `autopilot.py` (wired у router) + lifespan-loop + 4 settings-прапори.
- Skill `auto-coder`, seed `data/okr/okr.json`, згенерований `data/autopilot/dashboard.md`.
- mypy strict green (gateway/app 101 файл + jarvis_core 31); усі нові тести зелені.

## 8. Далі (backlog)

- `AP-loop`: реальний прохід усіх 6 фаз у проді на стек із redis/tools (зараз — unit + e2e-stub).
- `review→refactor`: передавати конкретні REAL-знахідки scan у задачу рефактора (зараз — summary).
- `analyze`: артефакт-канвас `[[app:markdown|...]]` для дашборда в Mini App.
- `evolve`: підтягувати фактичні маркери прогресу з roadmap-доків (парсер `done/⬜`).
- no-progress детектор для `test`-фази (CA-3.4) → стоп-умова циклу.
