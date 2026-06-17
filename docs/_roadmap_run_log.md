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
