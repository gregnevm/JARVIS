# ai_tester — порти рушія (статус заповненості)

> Контракт портів живе тут і в docstring [`server.py`](server.py); JARVIS-конкретика — лише в
> [`adapters/jarvis/manifest.json`](../adapters/jarvis/manifest.json) (Ports & Adapters, DR1).
> «Всі модулі — MCP»: кожен порт експонований 1:1 MCP-тулом; жодного CLI-only входу.

| Порт | Що | Реалізація | MCP-тули | Статус |
|---|---|---|---|---|
| `endpoint`/`auth` | куди й ким ходити (S1: локальний дефолт, fail-fast без creds) | `TesterConfig.from_env` (AI_TESTER_* → JARVIS_* → PLATFORM_PASSWORD → ADMIN_PANEL_PASSWORD → репо-`.env`) | `ready` | ✅ P0 |
| `source` | джерело даних відповідей — **ланцюжок декораторів** над живим gateway | `HttpSource` + `ReplaySource` (підміна фікстурою) / `FaultSource` (інʼєкція збою) / `RecordingSource` (запис фікстур) | `run(mode)`, `simulate` | ✅ P0 |
| `scenario` | реєстр фіч (ендпоінт+запит+oracle+ремедіація) | `Adapter.load` ← manifest адаптера | `features` | ✅ P0 (10 фіч jarvis) |
| `oracle` | pure-оцінка результату (status/поля/латентність; gated ≠ fail) | `evaluate_feature` | у складі `run`/`simulate` | ✅ P0 |
| `dispatch` | ремедіація через ті самі важелі, що `mcp__jarvis__code`/`computer` | `POST /api/v1/code/task`, `/api/v1/driver/exec|screenshot` | `dispatch_fix`, `verify_ui`, `screenshot` | ✅ P0 |
| `loop` | bounded test→fix→retest; зупинка на awaiting_confirm (S4) | `Engine.loop_run` | `loop_run` | ✅ P0 |
| `report` | артефакти прогонів (лише метадані, anti-leak; виняток — recordings-* із зредагованими тілами, під .gitignore) | `data/artifacts/ai_tester/run-*.json` + `last_run.json` | `report` | ✅ P0 |
| `confirm_gate` | S4: апрув завжди людський, рушій ніколи не авто-апрувить | міст до gateway `/api/v1/confirm/*` | `confirm_pending/approve/cancel` | ✅ P0 |
| `audit` | jsonl-слід (SSOT `jarvis_core/llm/jsonl_log.py`, лише метадані) | `make_audit` → `data/logs/ai_tester.jsonl` | — | ✅ P0 |

## Env (порт `endpoint`/`auth`)

| Змінна | Дефолт | Що |
|---|---|---|
| `AI_TESTER_BASE_URL` | `http://localhost:8000` (або `JARVIS_BASE_URL`) | gateway client-API |
| `AI_TESTER_BASIC_USER` | `admin` (або `JARVIS_BASIC_USER`) | користувач Basic-auth |
| `AI_TESTER_API_KEY` / `AI_TESTER_BASIC_PASSWORD` | фолбек `JARVIS_*` → `PLATFORM_PASSWORD` → `ADMIN_PANEL_PASSWORD` → репо-`.env` | Bearer або Basic |
| `AI_TESTER_TIMEOUT` | `120` | сек на запит (chat/coder бувають довгі) |
| `AI_TESTER_MAX_ROUNDS` | `3` (мінімум 1, fail-fast) | стеля раундів `loop_run` |
| `AI_TESTER_ARTIFACTS` | `data/artifacts/ai_tester` | куди класти звіти/записи |
| `AI_TESTER_AUDIT` | `data/logs/ai_tester.jsonl` | audit-слід |
| `AI_TESTER_REDACT` | `1` (або `JARVIS_REDACT`) | скраб секретів перед виходом у хост-AI |
| `AI_TESTER_MCP_TRANSPORT` | `stdio` | stdio \| http \| sse |

> Це env **скіла** (задається в `.mcp.json`), не Settings бекенд-сервісів — тому НЕ входить у
> `gen_env_docs`/`.env.example` (S2: нуль diff у бекенді).
