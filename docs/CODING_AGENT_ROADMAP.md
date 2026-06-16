# JARVIS — Coding Agent Roadmap (Стовп B)

> **Версія:** 1.10 (2026-06-16)
> **Статус:** Living document.
> **Мета:** довести JARVIS від «мостів до cursor/continue» до **рідного repo-aware агента кодування
> рівня Claude Code** — diff-edit, тест-луп, multi-file рефактор, self-review — локально й офлайн.

**Пов'язані документи**

| Документ | Роль |
|----------|------|
| [`AGENTS.md`](../AGENTS.md) | Конституція — Стовп B, принципи |
| [`docs/PRODUCT_ROADMAP.md`](PRODUCT_ROADMAP.md) | Парасолька — трек B фазовий статус |
| [`docs/AGENT_MODE_ROADMAP.md`](AGENT_MODE_ROADMAP.md) | Desktop-керування (host-agent FS/PS/UIA) — фундамент під CA-1 |
| [`docs/PLATFORM_ROADMAP.md`](PLATFORM_ROADMAP.md) | Projects (P1), Planning (P3), Teams (P8/P9) — будівельні блоки |
| [`docs/API_PLATFORM_ROADMAP.md`](API_PLATFORM_ROADMAP.md) | `/v1` як транспорт для CLI/IDE-режиму |

---

## 1. Позиціонування

### 1.1 Що означає «рівня Claude Code» для JARVIS

| Здатність Claude Code | JARVIS-еквівалент | Де в коді |
|------------------------|-------------------|-----------|
| Читає й редагує файли диффами | `fs_read` + майбутній `code_edit` (diff/apply) | `hostagent/`, `tools/app/toolkit/` |
| Тримає репо в контексті | scoped RAG по `project_id` + repo-граф | `tools/app/projects.py`, `memory/` |
| Ганяє термінал/тести | `run_cli`/`run_powershell` у computer mode | `tools/app/computer.py`, `hostagent/` |
| План → апрув → виконання | P3 Planning (загальний) → code-specific | `tools/app/plans.py` |
| Субагенти (паралельна робота) | P8 subagents / P9 teams | `tools/app/subagents.py`, `teams.py` |
| MCP-інструменти | P5 MCP gateway | `tools/app/mcp_gateway.py` |
| Hooks (pre/post) | P10 hooks | `tools/app/hooks.py` |
| CLI (`claude …`) | майбутній `jarvis code …` | новий |

**Ключова теза:** ~70% будівельних блоків Claude Code вже є у фундаменті (агент-луп, projects,
planning, teams, MCP, hooks, computer mode). Бракує **рідного coding-контуру**: diff-edit замість
PS-ехо, repo-граф замість плоского RAG, тест-луп як перша-класна операція, і coding-специфічний UX.

### 1.2 North Star (Стовп B)

> З Telegram/CLI: «у репо O:\proj падає `test_auth.py::test_expiry` — розберись». Агент: відкриває
> репо, читає тест і код, ставить гіпотезу, править файл диффом (показує diff на апрув), ганяє
> `pytest -k test_expiry`, читає вивід, ітерує до green, робить self-review, комітить у гілку, звітує
> з diff + лог тестів. Tier-ladder і `computer.jsonl` audit — як у Computer Use.

### 1.3 Принцип (незмінний)

Агент кодування **редагує файли диффами**, а не «друкує код у термінал». Усі мутації коду —
через `code_edit` із показом diff і (за межами session-trust) confirm. Git — мережа безпеки:
гілка/stash перед мутацією, ніколи не форс-пуш без явного дозволу (S4, AGENTS.md).

---

## 2. Baseline (стан на 2026-06-15)

### 2.1 Реалізовано (фундамент під B)

| Компонент | Звідки | Файл |
|-----------|--------|------|
| Агент-луп (ReAct, tool calling) | Фаза 6 | `tools/app/agent.py` (`AgentRunner`) |
| Cursor bridge | P12 | `tools/app/cursor_tasks.py`, `/cursor`, `cursor:` fast-path |
| Continue.dev bridge | P12 | `tools/app/tools/continue_tool.py`, `continue_dev` tool |
| Computer mode (PS/CLI/FS/browser) | C0–C6 | `tools/app/computer.py`, `hostagent/` |
| FS-операції (read/write, roots) | C0–C1 | `hostagent/` `/fs/*`, `HOSTAGENT_FS_ROOTS` |
| Projects (workspace + scoped RAG) | P1 | `tools/app/projects.py`, `memory/` |
| Planning (plan→approve→execute) | P3 | `tools/app/plans.py` |
| Subagents / Teams | P8/P9 | `tools/app/subagents.py`, `teams.py` |
| MCP gateway / Hooks | P5/P10 | `tools/app/mcp_gateway.py`, `hooks.py` |
| Code exec (sandbox-обмежений) | Фаза 6 | `ENABLE_CODE_EXEC`, `subprocess -I` |

### 2.2 Оцінка зрілості (чесно)

| Критерій | Оцінка | Коментар |
|----------|--------|----------|
| Виконання команд/тестів | **9/10** | `run_tests`/`run_lint` структуровані (CA-3.1/3.3); виділена fix-orchestration `fix_tests` (CA-3.2) + no-progress stop (CA-3.4); лишається live-fix eval (CA-3.5) |
| Редагування файлів | **8/10** | `code_edit` diff/apply + git-safety `.jarvis_backup` + транзакційний multi-file `code_edit_batch` (усе-або-нічого, dry-run) (CA-4.3/4.4); лишається rename/move з оновленням імпортів (CA-4.5) |
| Repo-контекст | **7/10** | дерево (repo_tree), grep, symbol-outline (repo_symbols), scoped-RAG індекс project-файлів + token-бюджет; бракує крос-файлового symbol-графа (CA-4.5) |
| Планування коду | **5/10** | P3 Planning є, не інтегрований у coding-контур |
| Self-review | **4/10** | P9 teams (Reviewer) є як bg job, не в coding-лупі |
| UX (coding-специфічний) | **3/10** | Workbench загальний; немає diff-viewer, repo-tree, test-panel |
| CLI / IDE | **1/10** | немає `jarvis code`; Continue лише як міст |
| Модель | **4/10** | qwen2.5:7b слабка для складного multi-file; потрібна 14b+/cloud opt-in |

### 2.3 Розриви (gap list)

| # | Gap | Вплив |
|---|-----|-------|
| ~~CB1~~ ✅ | ~~Немає `code_edit` (diff/apply)~~ → `code_edit` (search_replace+diff, confirm, diff-preview) | Закрито (CA-1.1/1.2) |
| ~~CB2~~ ✅ | ~~Немає git-safety~~ → `.jarvis_backup/<name>.<ts>.bak` перед кожним записом | Закрито (CA-1.3) |
| CB3↓ | Repo-контекст: дерево/grep/symbol-outline + scoped-RAG індекс project-файлів є; лишається крос-файловий symbol-граф (CA-4.5) | Структура файлу видима; крос-файлові залежності — ще ні |
| CB4 | Тест-луп не первинна операція (через generic PS) | Немає структурованого fail→fix циклу |
| CB5 | Planning не coding-специфічний (немає file-targets у кроках) | План не прив'язаний до файлів |
| CB6 | Немає diff-viewer / repo-tree / test-panel у Platform | Огляд правок лише через текст |
| CB7 | Немає `jarvis code` CLI та IDE-режиму | Не drop-in для розробника за клавіатурою |
| CB8 | Модель 7B слабка для multi-file | Потрібна 14b+/cloud planner opt-in (як AM-2.4) |

---

## 3. Фази розвитку (CA-0…CA-6)

```
CA-0 (bridges ✅) ─► CA-1 (diff-edit) ─► CA-2 (repo-context) ─► CA-3 (test-loop)
                                                 │                      │
                                                 ▼                      ▼
                                       CA-4 (plan/refactor) ─► CA-5 (review/agents) ─► CA-6 (CLI/IDE)
```

---

## CA-0 — Bridges baseline · ✅ **done**

| # | Задача | Статус |
|---|--------|--------|
| CA-0.1 | `cursor_task` (host CLI + cloud fallback) + `/cursor` + `cursor:` fast-path | [x] |
| CA-0.2 | `continue_dev` tool (`ENABLE_CONTINUE_DEV` + `cn serve`) | [x] |
| CA-0.3 | Computer mode PS/CLI/FS для ручних coding-дій | [x] |

**Вихід:** із Telegram можна запустити cursor/continue-задачу. Це **міст**, не рідний агент.

---

## CA-1 — Рідний file-edit · **наступний спринт (2–3 тижні)**

**Мета:** агент редагує код диффами з git-safety, не повним перезаписом.

| # | Задача | DoD | Пріоритет | Статус |
|---|--------|-----|-----------|--------|
| CA-1.1 | host-agent `POST /fs/edit` — apply unified-diff / search-replace block | Атомарний запис, повертає новий diff | P0 | [x] `hostagent` `/fs/edit` (search_replace + diff, .jarvis_backup) |
| CA-1.2 | Toolkit `code_edit` (схема: path, diff/old→new) + dispatch + confirm tier | Diff показується перед apply | P0 | [x] `computer.code_edit` (T1, mutating → confirm, diff у describe) |
| CA-1.3 | Git-safety: auto-branch або stash перед першою мутацією в repo | `.jarvis_backup/` або `git stash` | P0 | [x] `.jarvis_backup/<name>.<ts>.bak` перед кожним записом |
| CA-1.4 | `code_read` з line-ranges + контекст навколо матчу | Економія токенів vs повний файл | P1 | [x] `tools/app/tools/coding_tools.py` (`ENABLE_CODING_TOOLS`) |
| CA-1.5 | Workspace-скоуп: правки лише в `HOSTAGENT_FS_ROOTS`/project root | Deny поза скоупом | P0 | [x] `/fs/edit` через `_resolve_path` (FS_ROOTS scoping) |
| CA-1.6 | Golden trace: «додай docstring у функцію X» — diff apply + revert | `tools/tests/golden/` | P1 | [x] `hostagent/tests/golden/code_edit.json` + apply/revert round-trip |

**Вихід CA-1:** «додай тест до `agent.py`» → агент показує diff → апрув → apply, з можливістю revert.

---

## CA-2 — Repo-context · **3–4 тижні**

**Мета:** агент «бачить» структуру репо, не лише плоский RAG.

| # | Задача | DoD | Статус |
|---|--------|-----|--------|
| CA-2.1 | `repo_tree` tool — дерево файлів (gitignore-aware, ліміт глибини/entries) | JSON для моделі | [x] `coding_tools.repo_tree` (`rg --files`, depth/entries cap) |
| CA-2.2 | `repo_grep` / `repo_find` — ripgrep-обгортка по workspace | Read-only, ліміт результатів | [x] `coding_tools.repo_grep` (rg, `-g` glob, result cap) |
| CA-2.3 | Symbol-граф (ctags/tree-sitter) — функції/класи/імпорти | Опційно per-language | [x] `repo_symbols` — Python `ast` (точно), regex-фолбек для решти |
| CA-2.4 | Scoped RAG по project root (індексація файлів проєкту, не лише чату) | Reuse `project_id` embed | [x] embed project-файлів на add + `POST /projects/{id}/reindex` |
| CA-2.5 | Context-budget: вибірка релевантних файлів під ліміт токенів | Як P1.7 (12k budget) для коду | [x] `memory/app/budget.py` token-бюджет; релевантність — RAG (CA-2.4) |

**Вихід CA-2:** агент відповідає «де визначено `AgentRunner`?» і підтягує правильні файли в контекст.

---

## CA-3 — Test/build loop · **3–4 тижні**

**Мета:** запусти→прочитай fail→виправ→повтори як перша-класна операція.

| # | Задача | DoD | Статус |
|---|--------|-----|--------|
| CA-3.1 | `run_tests` tool — обгортка (pytest/npm/…) з парсингом fail-summary | Структурований `{passed, failed[], output_tail}` | [x] `check_tools.run_tests` (runner-allowlist, pytest-парсер) |
| CA-3.2 | Fix-loop у `AgentRunner`: fail → локалізація файлу → `code_edit` → re-run | Max N ітерацій (config) | [x] `AgentRunner.fix_tests` — виділена петля «тест→правка→тест», `coding_fix_max_rounds`, авторитетний re-run як гейт, стоп green/max/no-progress |
| CA-3.3 | Build/lint tool (mypy/ruff/tsc) з тим самим патерном | Структурований вивід | [x] `check_tools.run_lint` (mypy/ruff/generic парсер) |
| CA-3.4 | Stop-conditions: green / max-iters / no-progress (однаковий fail двічі) | Graceful звіт | [x] `fix_loop.note_test_result` — per-user fail-сигнатура (Redis, TTL); повтор → підказка «зміни підхід / зупинись»; max-iters в агент-лупі |
| CA-3.5 | Golden trace: навмисно зламаний тест → агент полагодив до green | `tools/tests/golden/` | [~] детермінований golden парсингу (`check_output.json`); live-fix eval — попереду |

**Вихід CA-3:** «полагодь падіння в `tests/`» → агент ітерує до green або чесно звітує, що застряг.

---

## CA-4 — Plan / multi-file рефактор · **4–6 тижнів**

**Мета:** план із file-targets, один апрув, multi-file зміни консистентно.

| # | Задача | DoD | Статус |
|---|--------|-----|--------|
| CA-4.1 | `POST /agent/code/plan` — кроки з `{file, action, rationale, risk}` | JSON schema (розширення P3) | [x] `AgentRunner.code_plan` + route; `_normalize_steps` зберігає code-поля (file/action/rationale/risk) |
| CA-4.2 | Один ✅ на план (не на кожен файл); session-trust як computer | Redis TTL як P3 plans | [~] один апрув на план через P3 approve-flow + маркер (Redis TTL); session-trust auto-approve — попереду |
| CA-4.3 | Multi-file apply транзакційно (усе або відкат) | Rollback при fail у середині | [x] host-agent `/fs/edit_batch` (план-усіх→запис-усіх, відкат із пам'яті, дедуп, `edit_batch_max`) + tool `code_edit_batch` (T1, mutating→confirm, owner-gated) |
| CA-4.4 | Dry-run: показати всі diff-и без apply | `/code plan --dry` | [x] `code_edit_batch(dry_run=true)` — усі diff-и без запису, read-only (без confirm) |
| CA-4.5 | Rename/move рефактор з оновленням імпортів (symbol-граф із CA-2.3) | Golden trace | [ ] |

**Вихід CA-4:** «винеси `_helpers` у `jarvis_core`» → план на 5 файлів → один апрув → консистентний apply.

---

## CA-5 — Self-review + субагенти · **5–8 тижнів**

**Мета:** агент рев'ювить власні зміни; Coder/Reviewer/Tester як pipeline.

| # | Задача | DoD | Статус |
|---|--------|-----|--------|
| CA-5.1 | `code_review` self-pass: diff → зауваження → fix перед звітом | Інтеграція з P9 Reviewer | [ ] |
| CA-5.2 | Coder→Reviewer→Tester team-pipeline для coding-задач | Reuse `teams.py` | [ ] |
| CA-5.3 | bg job type `coding_task` — довгі задачі з progress/cancel | Reuse `bg_jobs.py` + AM-2.2 | [ ] |
| CA-5.4 | Subagent на під-задачу (напр. окремий файл) з budget_iters | Reuse `subagents.py` | [ ] |
| CA-5.5 | Hooks: pre-commit lint/test gate (P10 hooks) | `data/hooks/` post_tool | [ ] |

**Вихід CA-5:** велика задача йде як фоновий job; Reviewer ловить баги до звіту; видно progress.

---

## CA-6 — CLI + IDE-режим · **6–10 тижнів**

**Мета:** drop-in для розробника за клавіатурою, не лише з Telegram.

| # | Задача | DoD | Статус |
|---|--------|-----|--------|
| CA-6.1 | `jarvis code "<task>"` CLI — локальний агент проти cwd-репо | Streaming у термінал | [ ] |
| CA-6.2 | CLI auth через `/v1` ключ (Стовп A) | `JARVIS_API_KEY` + `base_url` | [ ] |
| CA-6.3 | IDE-міст: LSP-обгортка або VS Code extension (поверх `/v1`) | Inline diff в IDE | [ ] |
| CA-6.4 | Headless-режим (CI): `jarvis code --apply --no-confirm` за політикою | Policy gate (AM-4) | [ ] |
| CA-6.5 | Platform Coding tab: repo-tree, diff-viewer, test-panel (закриває CB6) | SSE як Workbench | [ ] |

**Вихід CA-6:** `jarvis code "fix lint"` у терміналі = той самий агент, що з Telegram; видно diff в IDE/Platform.

---

## 4. KPI

| KPI | Baseline (2026-06) | Ціль CA-3 | Ціль CA-6 | Як міряти |
|-----|--------------------|-----------|-----------|-----------|
| «Полагодь тест» E2E success | ~30% (через PS) | 70% | 90% | golden + ручне QA |
| Diff-edit замість full-write | 0% | 100% | 100% | audit tier |
| Multi-file рефактор success | — | — | >80% | golden traces |
| Confirms на 5-file задачу | 5 | 3 | 1 (plan) | audit |
| Втрата коду (немає git-safety) | можлива | 0 | 0 | git reflog присутній |
| CLI parity з Telegram | 0% | — | >90% | feature-чеклист |

---

## 5. Свідомо не робимо

- **Full-file write для коду** після CA-1 — лише diff (огляд + revert).
- **Форс-пуш / `git reset --hard`** без явного дозволу користувача (S4).
- **Auto-apply без confirm** поза session-trust / policy (CA-6.4 — лише за політикою).
- **Переписати `AgentRunner` на LangGraph/CrewAI** — розширюємо наявний луп (P6).
- **Хмарна модель за дефолт** — локальна 7B/14B; cloud planner лише opt-in (як AM-2.4.2).

---

## 6. Залежності та ризики

| Ризик | Мітигація |
|-------|-----------|
| 7B слабка для multi-file | 14b+ рекомендація, cloud planner opt-in, дрібніші кроки в плані |
| Агент псує код | git-safety (CA-1.3), dry-run (CA-4.4), diff-confirm, golden traces |
| Symbol-граф крихкий per-language | почати з Python (tree-sitter), graceful degrade до grep |
| Великий diff не влазить у контекст | line-ranges (CA-1.4), context-budget (CA-2.5) |

---

## 7. Мапінг на існуючі roadmap-и

| Цей документ | Будівельний блок | Звідки |
|--------------|------------------|--------|
| CA-1 file-edit | host-agent FS, `HOSTAGENT_FS_ROOTS` | AGENT_MODE AM-1.4 |
| CA-2 repo-context | Projects, scoped RAG | PLATFORM P1 |
| CA-3 test-loop | computer mode CLI/PS | AGENT_MODE / Computer Use |
| CA-4 plan | Planning mode | PLATFORM P3 |
| CA-5 review/agents | Teams, Subagents, Hooks, bg jobs | PLATFORM P8/P9/P10/P2 |
| CA-6 CLI/IDE | `/v1` API | API_PLATFORM AP-2/AP-5 |

---

## 8. Історія оновлень

| Дата | Версія | Зміна |
|------|--------|-------|
| 2026-06-16 | 1.10 | CA-4.1 code-plan (`code_plan` + `POST /agent/code/plan`, file-targeted кроки) + CA-4.2 (один апрув на план через P3 flow) |
| 2026-06-16 | 1.9 | CA-4.3/4.4 завершено: tool `code_edit_batch` (T1, confirm на запис, dry-run read-only) поверх `/fs/edit_batch` — повний контур транзакційної multi-file правки |
| 2026-06-16 | 1.8 | CA-4.3/4.4 (host-side) транзакційний `/fs/edit_batch` (усе-або-нічого, dry-run, дедуп, `edit_batch_max`) + рефактор `_plan_edit`/`_write_planned` |
| 2026-06-16 | 1.7 | CA-3.2 виділена fix-orchestration `AgentRunner.fix_tests` (петля тест→правка→тест, `coding_fix_max_rounds`, стоп green/max/no-progress) |
| 2026-06-16 | 1.6 | CA-3.4 no-progress детектор (`fix_loop.py` — per-user fail-сигнатура в Redis, повтор → підказка стоп/зміна підходу) + крос-платформний `_basename` (PureWindowsPath) |
| 2026-06-15 | 1.5 | CA-3.1 `run_tests` + CA-3.3 `run_lint` (структуровані раннери, `check_tools.py`) + golden парсингу |
| 2026-06-15 | 1.4 | CA-2.4 scoped-RAG індекс project-файлів (embed+reindex) + CA-2.5 token-бюджет (`budget.py`) |
| 2026-06-15 | 1.3 | CA-2.3 `repo_symbols` (Python ast + regex-фолбек) + CA-1.6 golden trace (apply/revert) |
| 2026-06-15 | 1.2 | CA-1.1/1.2/1.3/1.5 done — `code_edit` (search_replace+diff) через host-agent `/fs/edit`, confirm-tier T1, git-safety `.jarvis_backup/` |
| 2026-06-15 | 1.1 | CA-1.4/CA-2.1/CA-2.2 done — `coding_tools.py` (repo_tree/repo_grep/code_read), read-only, `ENABLE_CODING_TOOLS` |
| 2026-06-15 | 1.0 | Початковий roadmap Стовпа B (CA-0…CA-6) після аудиту фундаменту |

---

*Оновлюйте чекбокси при закритті задач. Принципи: [`AGENTS.md`](../AGENTS.md) · Парасолька: [`PRODUCT_ROADMAP.md`](PRODUCT_ROADMAP.md)*
