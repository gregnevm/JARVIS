# Roadmap execution run — progress log

> Автономний прогон roadmap (Claude Code). Гілка: `feat/platform-p0-p12-and-refactor`.
> Старт: 2026-06-15. НЕ пушити в remote без дозволу; локальні коміти — ок.

## Baseline (на старті прогону)

- Platform P0–P12: **done (100%)** за `docs/PLATFORM_ROADMAP.md`.
- На гілці — незакомічений **SAAS_DEEP_DIVE PR#1** рефактор:
  - новий `jarvis_core/context.py` (RequestContext, synthetic_context, redis_key)
  - новий `jarvis_core/http_helpers.py` (require_text/require_found консолідація)
  - gateway/tools `_helpers.py` ре-експортують з jarvis_core
  - `whoami` розширено org/role/plan/legacy_uid
  - нові тести: `jarvis_core/tests/test_context.py`, `test_http_helpers.py`

## Тести (baseline, per-service)

| Сервіс | Результат |
|--------|-----------|
| jarvis_core | ✅ 40 passed |
| memory | ✅ 46 passed (потрібен `alembic` — доставлено в dev venv) |
| hostagent | ✅ 41 passed |
| twin | ✅ 41 passed |
| edge | ✅ 6 passed |
| gateway | ✅ 264 passed |
| tools | ✅ pass (після фіксу 2 нестійких тестів) |

**mypy strict (CI-matrix):** ✅ jarvis_core / gateway / tools / memory / twin / hostagent — усі green.

**Docker:** стек уже live (9 сервісів, healthy, 19h uptime); `docker compose config` валідний;
rebuild gateway+tools із новим кодом — verified.

## Знайдені й виправлені проблеми

1. **2 нестійкі (environment-fragile) тести в `tools/`** — падали локально, зелені в CI:
   - `test_toolkit.py::test_schemas_default_excludes_code_exec` — не пінив `mcp_servers_json`
     (локальний `.env` має `MCP_SERVERS_JSON`, тож `mcp_call` протікав у дефолтний набір схем).
   - `test_continue_tool.py::test_open_file_calls_hostagent_cli` — не пінив `continue_vscode_cli`
     (локальний `.env` має повний шлях до Cursor `code.cmd`).
   - **Фікс:** додав hermetic-піни в обидва тести. Тепер детерміновані незалежно від `.env`.
2. **Dev venv бракувало `alembic` + `Pillow`** (декларовані в `memory/`+`tools/` requirements,
   але не в спільному dev-venv) → memory-тести й `mypy tools` падали локально. Доставлено.

## Стан roadmap (підсумок інвентаризації)

- **Platform P0–P12:** done (100%).
- **SAAS_DEEP_DIVE PR-послідовність:** PR#0 (IDOR) ✅ · **PR#1 (RequestContext + http_helpers) ✅
  завершено цим прогоном** · PR#2–#7 — попереду (multi-tenant migration; архітектурна зміна +
  потребує Stripe/JWT секретів на PR#6).
- **Решта (Stowp A/B/C треки, Agent Mode AM-1…AM-4):** ~65 actionable, ~10 blocked (RunPod/GPU/
  cloud-secrets), ~50 deferred/YAGNI.

## Зроблено (коміти цього прогону)

1. `77052d7` test(tools): hermetic-фікс 2 нестійких тестів.
2. `a9b25b2` feat(jarvis_core): **SAAS PR#1** — RequestContext + http_helpers consolidation.
3. `1fe91e6` feat(tools): **CA-1.4/2.1/2.2** — repo_tree/repo_grep/code_read (read-only,
   `ENABLE_CODING_TOOLS`, owner+computer gate, 18 тестів, mypy strict, real-`rg` verified).
4. `7145306` feat(coding-agent): **CA-1.1/1.2/1.3/1.5** — `code_edit` (search_replace+unified diff)
   через host-agent `POST /fs/edit`; мутуючий T1 → confirm-flow з diff-preview; git-safety
   `.jarvis_backup/<name>.<ts>.bak`; CRLF-safe; FS_ROOTS-scoped. 13 hostagent + 10 tools тестів.

## Adversarial review (workflow wf_d27bb773) + фікси

Прогнав multi-agent review (4 лінзи → verify, 19 raw → 9 REAL). Виправлено 3 справжні баги:

- 🔴 **diff-applier (HIGH)** — був підрядковий (`str.count`/`replace`): сплайсив у середину
  довшого рядка (`-export=80` у `reexport=80`), хибно скаржився «not unique» (`port`/`export`),
  ламав multi-hunk із повтором контексту. **Фікс:** переписав на **line-anchored** із @@-офсетами
  (`_parse_hunks`→list[lines], `_find_block` із перевагою позиції з заголовка, pure-insertion).
- 🔴 **repo_grep secret-leak (HIGH)** — `rg -g '.env'` РЕ-ВКЛЮЧАЄ gitignore-файл (перевірено live).
  **Фікс:** трейлінг deny-глоби (`_SECRET_DENY`: .env/*.pem/*.key/id_rsa/…), які user-glob не
  перебиває (last-wins). Перевірено проти реального rg: leak заблоковано, нормальний пошук працює.
- 🟡 **max_bytes=6KB блокував правку файлів >6KB** — додав `HOSTAGENT_EDIT_MAX_BYTES` (2 MB) для /fs/edit.

Додано 6 regression-тестів (hostagent) + 2 (tools). Не виправляв (поза скоупом, occ-tracking
для окремого PR): rate-limit double-count (pre-existing у всіх мутуючих tools, → spawn_task);
path-vs-FS_ROOTS для repo_grep (refuted — у межах owner-trust `run_cli`).

## CA-2 repo-context + CA-1.6 (коміти cc0265f, 6bf5abe, 9be60cd)

- **CA-2.3 `repo_symbols`** — outline файлу: Python `ast` (точні сигнатури/вкладеність/імпорти,
  без нових залежностей), regex-фолбек для решти мов; pattern-фільтр. +7 тестів.
- **CA-1.6 golden trace** — `hostagent/tests/golden/code_edit.json` (4 кейси) + apply==expected,
  reversibility (new→old), endpoint apply + revert із `.jarvis_backup`. +10 тестів.
- **CA-2.4 scoped-RAG project files** — embed чанків project-файлів (message_id IS NULL) на add;
  `POST /projects/{id}/reindex` (clear+reembed); прапор `index_project_files`. +4 тести.
- **CA-2.5 token-бюджет** — `memory/app/budget.py` (estimate_tokens + fit_token_budget);
  `read_project_files_content` → токен-бюджет (3000/1200) замість char. +5 тестів. Релевантність — RAG.

Стан: усі per-service suites + mypy strict green; docker memory+tools rebuild.
CODING_AGENT_ROADMAP: CA-1.1–1.6, CA-2.1–2.5 закрито; репо-контекст maturity 4→7, edit 3→7.

## CA-3 test/lint runners (коміт b2d2f34)

- **CA-3.1 `run_tests`** + **CA-3.3 `run_lint`** (`tools/app/tools/check_tools.py`) — структурований
  pass/fail/errors + список впалих + хвіст; exe з runner-allowlist (блокує rm/curl); парсери
  pytest/mypy/ruff. Fix-цикл — через наявний ReAct-луп (run_tests→code_edit→run_tests).
- 12 unit + 5 golden (`check_output.json`) тестів; mypy strict green; tools rebuild.
- Чесно partial: CA-3.2 (виділена fix-orchestration), CA-3.4 (no-progress детектор),
  CA-3.5 (live-fix eval) — лишаються. exec maturity 7→8.

**Напрям обрано користувачем:** «Additive Pillar B» (рідні coding-агент інструменти).
SaaS PR#2–#7 НЕ беремо без явного дозволу (архітектура + Stripe/JWT секрети).

## Кроки

## Auto-code coroutine (OKR autopilot) — новий вертикальний зріз

Додано **замкнену OKR-керовану петлю** (`docs/AUTO_CODE_COROUTINE_ROADMAP.md`),
default OFF (ADR-008). 6 фаз: code→review→refactor→analyze→test→evolve.

- `jarvis_core/okr.py` — модель OKR/KR + `select_objective`/`mutate_okr` (адмін-контекст
  однією фразою піднімає пріоритет). +15 тестів, mypy strict green.
- `gateway/app/auto_coroutine.py` — чистий планувальник + `run_cycle` (інжектований
  dispatch) + `auto_coroutine_loop` (lifespan, off) + дашборд/сховище. +14 тестів.
- Platform tab `autopilot.py` (status/tick/OKR/dashboard) wired у router; 4 settings-прапори.
- Skill `data/skills/auto-coder`, seed `data/okr/okr.json`, `data/autopilot/dashboard.md`.
- e2e: platform-ендпоїнти 200 через TestClient; mypy `gateway/app` (101) + `jarvis_core` (31) green.

## Kaizen window 2026-06-18-kaizen-2 (max-utilization, 7 PR змерджено в green `main`)

Автономний прогон скіла `kaizen` (`profile:jarvis`). На відміну від попередніх локальних
прогонів — кожне покращення доставлено як **змерджений PR** (code → local CI-gate → push →
PR → watch CI green → squash-merge). `main` зелений увесь час; жодного revert. Стоп:
`backlog_dry` (безпечні offline-1-ітерація задачі вичерпано; решта потребує
сервісів/секретів/GPU або людського рев'ю — SaaS, vision/UIA, SPA, IDOR). 50.8/300 хв вікна.

- **#30** `feat(safety)` — `jarvis_core/safety/blast_radius.py`: fail-closed allow/deny path-guard
  (safety_guard-порт, deny-wins, basename-deny для секретів), 24 тести.
- **#31** `refactor(jsonl)` — єдиний `JsonlLog` SSOT у `jarvis_core`; `twin/app/session_log.py` →
  тонкий re-export (усунуто дублювання, P8/DRY); `read_from` портовано на core + 7 тестів.
- **#32** `test(parsers)` — `test_parsers.py` (29 кейсів): guard-гілки
  `extract_json_object`/`kobold_token`/`ollama_chunk`/`ollama_chat_chunk`/`ollama_inference_stats`.
- **#33** `feat(redaction)` — маскування AWS access key ID (AKIA/ASIA).
- **#34** `docs(context)` — D1 doc-sync: `redis_key` reframed PR#3→Live + звірений список 7 споживачів.
- **#35** `feat(redaction)` — Google API key (AIza) + standalone JWT (eyJ.x.y).
- **#36** `fix(redaction)` — рекурсивна редакція payload (вкладені dict/list на будь-якій глибині).

Підсумок: jarvis_core-тести 144 → **210** (+66); redactor-бекстоп покриває канонічний набір
секретів + вкладені структури; нова safety-цеглина для автономних правок. kaizen-score 86 (+8).
Артефакти: `data/artifacts/self-improve/` (20 паспортів, `window.json`,
`runs/2026-06-18-kaizen-2/{summary.json,digest.md}`).

## Kaizen window 2026-06-19-1 (max-utilization, 8 PR змерджено в green `main`)

Автономний прогон скіла `kaizen` (`profile:jarvis`) у свіжому 5-год вікні. Кожне покращення —
**змерджений PR** (code → local CI-gate → push → PR → watch CI green → squash-merge). `main`
зелений увесь час; жодного revert. Робота велась у git-worktree `O:/JARVIS-kaizen` з `origin/main`
(основне дерево `claude/platform-context-mobile-buildout` має брудний WIP — не чіпали). Два знайдені
вектори: **plan-limits (Стовп A foundation)** і **повна OpenAI-SDK-сумісність `/v1`** (попереднє
вікно зупинилось на `backlog_dry`, але ці жили лишались незачеплені). ~110/300 хв вікна.

- **#38** `feat(saas)` — `jarvis_core/plan_limits.py`: чиста політика-SSOT план→квоти + `exceeds()`;
  studio/enterprise UNLIMITED (S2: self-hosted ніколи не впирається в 402); 9 тестів (AP-4.3 `[~]`).
- **#39** `docs(roadmap)` — D1: AP-1.0/AP-1.1 `[x]` (PR#0 IDOR owner-gate + PR#1 RequestContext —
  звірено з кодом; track-roadmap = SAAS §4.0).
- **#41** `feat(api)` — `/api/v1/whoami` віддає `limits` плану (UNLIMITED→null); `public_limits()` —
  plan_limits стає живим споживачем, не мертвим кодом.
- **#42** `fix(api)` — `/v1` 422 (Pydantic-валідація) у OpenAI-конверт `{error:{...}}`, не дефолтний
  `{detail}`; інакше офіційний openai SDK не парсить помилку (AP-2.6).
- **#43** `fix(api)` — стрім `/v1` більше не світить сирий exc клієнту (info-leak): лог на сервері +
  узагальнене `[stream error]`; +regression-тест.
- **#44** `fix(api)` — неперехоплені помилки `/v1` → 500 OpenAI-конверт (`api_error`), traceback у лог,
  не клієнту; завершує error-envelope AP-2.6 (HTTPException+422+500).
- **#45** `fix(api)` — обʼєкти `/v1/models` отримали обовʼязкове SDK-поле `created:int` (інакше
  `client.models.list()` падає на валідації); +SDK-shape тест.
- **#46** `docs(roadmap)` — D1: «чесна зрілість» `/v1` 7→9/10 (responses/usage присутні, models
  SDK-shape, повний envelope), закрито застарілі gaps AB2 і AB5 (звірено з кодом).

Підсумок: `/v1` тепер drop-in OpenAI-сумісний по всіх error-шляхах (422/500/stream, без info-leak)
і Model-shape; нова pillar-A цеглина plan-limits + її перший споживач (`/whoami`). +15 тестів
(jarvis_core +11, gateway +4). Стоп: `backlog_dry` — обидві безпечні offline-жили вичерпано
(plan-limits enforcement = YAGNI до multi-tenant; решта roadmap потребує сервісів/секретів/SPA/GPU).
kaizen-score 90 (+4). Артефакти: `data/artifacts/self-improve/` (паспорти, `window.json`,
`runs/2026-06-19-1/{summary.json,digest.md}`).

## Kaizen — window 2026-06-19-2 (1 merged PR, main green)

Свіже 5-год вікно. Реально вікно майже все спожив suspended-session gap (старт ~09:24Z,
фініш ~15:05Z, активного компуту ~36 хв) → `remaining≈-41 хв` → wind-down після 1 ітерації.

- **#48** `feat(plan-limits)` — AP-4.5 політика soft/hard + grace як **чистий SSOT** у
  `jarvis_core/plan_limits.py`: `classify()→LimitStatus{ok|grace|blocked}`, `hard_cap()`
  (ops = soft+grace `DEFAULT_GRACE=10%`, floor; billing = `hard==soft`), `RESOURCE_KIND`
  ops/billing-split + `fail_open()` (кодує «fail-open ops, fail-closed billing»); import-assert
  `RESOURCE_KIND==RESOURCES` (той самий fail-fast, що `PLAN_LIMITS==VALID_PLANS`). +14 тестів
  (24 у `test_plan_limits.py`). jarvis_core mypy strict (45) + повний suite (234) green; remote
  CI run `27833174401` success. AP-4.5 `[ ]→[~]`.

Чесно про YAGNI (P6): попереднє вікно відклало *enforcement-wiring* як YAGNI до multi-tenant
(потрібен key→plan через tenant ctx). Ця ітерація додала лише *чисту політику* — задокументований
SSOT-шар, який модуль сам анонсує («enforcement підключає цю політику окремо»), той самий патерн,
що `exceeds()`/`public_limits()` (останній уже має споживача `/whoami`). Споживача в classify/hard_cap
поки немає — це усвідомлений SSOT-first, не дрейф.

Стоп: **window edge** (вікно вичерпане реальним wall-clock; suspended-gap). Безпечна offline-жила
теж стоншала — лишилось переважно те, що потребує сервісів/секретів/міграцій/SPA. kaizen-score 88 (-2:
менший throughput за вікно, але якість висока й main зелений усе вікно). Артефакти:
`data/artifacts/self-improve/` (паспорти 0038–0042, `window.json`, `runs/2026-06-19-2/{summary.json,digest.md}`).
