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

## Kaizen — window 2026-06-19-3 (1 merged PR, main green)

Свіже 5-год вікно (старт ~19:56, ~47 хв активного компуту). Вікно перетнулося з
**паралельним autopilot-писачем** у тому ж робочому дереві.

- **#51** `docs(roadmap)` — D1 doc-code sync: AP-4.4 `[ ]→[~]`. Конкурентний писач змерджив
  *ідентичну* AP-4.4 код-зміну (org-scoped metrics keys через `redis_key`) як **#50**
  (byte-for-byte мій docstring+`_mkey`) — але без roadmap-write-back. Ця ітерація закрила
  саме той D1-дрейф, що #50 лишив: точна нотатка (org_id=None → legacy `jarvis:metrics:*`
  байт-у-байт S2; реальний org → `jarvis:{org}:metrics:*`; `record_*`/`summary` беруть
  keyword-only `org_id`; +2 тести; threading у call-sites чекає tenant-ctx). Merged `16bc444`,
  remote CI 7/7 green.

Контекст: **#50** `feat(tools)` (AP-4.4 org-scoped metrics, +2 тести, 7/7 green) — субстантивна
цеглина pillar-A, змерджена паралельним писачем у це ж вікно; цей прогон закрив її doc-half.

Чесно про контенцію: робота йшла в **ізольованому git-worktree**, бо main-дерево активно
перемикав гілки й ревертив незакомічені правки інший автономний loop (autopilot). Це трактовано
як kill-switch-подібну аномалію (safety-contract §1) → wind-down після 1 ітерації, без піраміди
конфліктних PR.

Стоп: **concurrent-writer contention + backlog_dry** (безпечна offline-жила стоншала; решта
потребує сервісів/секретів/SPA/міграцій або tenant-ctx до tools — той самий gate, що AP-4.3/4.5).
kaizen-score 86 (-2: низький власний throughput через колізію, але якість висока й main зелений
усе вікно; D1-дрейф закрито). Артефакти: `data/artifacts/self-improve/` (паспорти 0043–0046,
`window.json`, `runs/2026-06-19-3/{summary.json,digest.md}`).

## Kaizen iteration 2026-06-20-verify (single-iter, end-to-end verification)

Прогін routine `kaizen-loop` (profile:jarvis) як функціональна перевірка скіла.

- **Task (leverage):** закрити mypy-gap сервісу `tts` — `mypy tts/app` падав на
  `torch` (немає стабів, не в `ignore_missing_imports`), тож сервіс не можна додати
  в CI-матрицю чесно. **Fix:** додано `torch.*` в `pyproject.toml` mypy-override
  (той самий патерн, що `TTS.*`/`playwright.*`).
- **CI-gate (scoped):** `mypy tts/app` 🟢 (4 файли), `pytest tts/tests` 🟢 (3),
  без регресій (`jarvis_core` 45 + `tools/app` 91 mypy 🟢). Local commit, no push.
- **Follow-up (drift):** `tts` ще НЕ в `.github/workflows/ci.yml` матриці — додавання
  тягне важкі deps (TTS/torch) → рішення про CI-час за людиною. mypy-блокер знято.

## Kaizen window 2026-07-04-1203 (ULTRACODE max-utilization, 8 PR змерджено в green `main`)

Свіже 5-годинне вікно (window_start 12:03:48 UTC). Кожен інкремент вироблено й перевірено
мультиагентним **Workflow**-оркеструванням (ultracode): PLAN judge-panel (4 скаути A/B/C/foundation
→ 15 кандидатів → leverage-суддя з evidence spot-check) згенерував ранжовану чергу (збережено в
`plan-queue.json`); кожна ітерація — WRITE → adversarial 2–4-lens REVIEW → незалежний VERIFY кожної
знахідки → LOCAL CI-gate → commit → PR → watch-green → squash-merge. Ізоляція: усі правки в
`O:/JARVIS-kaizen` worktree з `origin/main`; жива гілка користувача не торкнута.

Змерджено (усі після 7/7 remote CI green, 0 reverts, main зелений усе вікно):

1. **#73** `fix(orchestrator)` — `parse_critic_verdict` substring→word-boundary `\bAPPROVED\b`:
   «DISAPPROVED»/«UNAPPROVED» більше не парситься як approved=True (Critic-gate інвертувався на
   S1 prose-path). Review зрефакторив над-широкий reject-regex до мінімальної форми. Merged `f94cbc8`.
2. **#74** `fix(bot)` — tgauth arming лише для server-minted `pending` токена (`bind_tgauth_login`,
   single-use pending→uid): закрито arbitrary-token session-fixation → account-takeover + resurrection +
   clobber. Residual unauth-mint fixation → spawn-task follow-up. Merged `0f01511`.
3. **#75** `fix(memory)` — redaction-backstop на `/context/update` (redact-before-embed): summarize-job
   LLM-summary більше не кладе картки/OTP/секрети cleartext (sibling PR#69). Merged `37a8991`.
4. **#76** `fix(mcp)` — `call_tool` тепер піднімає `CallToolResult.isError` як failure до агент-лупу
   (раніше tool-failure повертався як success observation). Merged `44a03ba`.
5. **#77** `fix(api)` — `GET /v1/models` під `require_scope('models')` (мертвий scope став живим; бек-
   сумісно бо models у `_DEFAULT_SCOPES`); закрито doc/code-drift AP-1.5 + `API_QUICKSTART`. Merged `a122b86`.
6. **#78** `fix(bot)` — `is_addressed` @mention word-boundary: `@jarvis_bot` не матчить у
   `@jarvis_bot_admin`/`@jarvis_bot2` (spurious respond+ambient-ingest чужих повідомлень). Merged `3c15c47`.
7. **#79** `fix(webapp)` — Telegram initData fail-closed на відсутній/невалідний `auth_date`
   (раніше fail-open → необмежене вікно реплею). Merged `f7d472a`.
8. **#80** `fix(saas)` — all-invalid API-key scopes → `[]` (least privilege), не всі defaults (тихе
   розширення привілеїв); перевернуто+перейменовано тест, що кодував баг, +e2e 403. Merged `2371448`.

Покриття: +17 тест-функцій (~45 кейсів). Doc-sync (D1): iter5 **закрив** AP-1.5/QUICKSTART дрейф
(0 нового дрейфу введено). Пиляри: 3× security (auth/redaction), 3× correctness, 2× pillar-A scope —
усі 3 стовпи + foundation.

Стоп: **backlog_dry безпечних високо-цінних задач** (не бюджет — лишалось ~180 хв). Хвіст черги —
ризиковий/пре-емптивний: #9 inline-toolcall (0.55, для JARVIS майже гіпотетичний — усі імена
інструментів `\w+`, моделі емітять name-first; фікс переписує DoS-guarded парсер), #10 mcp-rpc
foreign-request-hang (0.50, concurrency-sensitive, важко верифікувати офлайн), #11 context-events
org-scope reads (0.34, пре-емптивний, без поточного failure, під майбутній SAAS_MODE). Per ULTRACODE
quality-over-quantity — wind-down замість форсування маргінальних ітерацій.

kaizen-score **94** (+5). Артефакти: `data/artifacts/self-improve/` (паспорти 0122–0155,
`window.json` 8 ітерацій, `summary.json`, `plan-queue.json`). Worktree знято; жива гілка чиста.
