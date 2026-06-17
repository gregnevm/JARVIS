# JARVIS Platform — Roadmap

> **Версія:** 1.1 (2026-06-05)
> **Статус:** Living document — оновлюється після кожного milestone.
> **Scope:** sovereign self-hosted personal AI — Telegram, RAG, voice, computer use,
> LoRA fine-tuning, Edge USB, web console `/platform`.

> **Місце в ієрархії:** цей файл — **трек** (web-консоль) під парасолькою [`docs/PRODUCT_ROADMAP.md`](PRODUCT_ROADMAP.md).
> Принципи й цілі — у [`AGENTS.md`](../AGENTS.md). Консоль `/platform` — дім для UI стовпів A (keys/usage/playground) і B (coding tab).

**Пов'язані документи**

| Документ | Роль |
|----------|------|
| [`AGENTS.md`](../AGENTS.md) | Статут: місія, принципи, 3 цілі-стовпи |
| [`docs/PRODUCT_ROADMAP.md`](PRODUCT_ROADMAP.md) | **Парасолька** повного продукту (фундамент + стовпи) |
| [`docs/API_PLATFORM_ROADMAP.md`](API_PLATFORM_ROADMAP.md) | Стовп A — developer-console таби тут |
| [`docs/CODING_AGENT_ROADMAP.md`](CODING_AGENT_ROADMAP.md) | Стовп B — coding tab тут (CA-6.5) |
| [`docs/CLIENTS_ROADMAP.md`](CLIENTS_ROADMAP.md) | Стовп C — `/platform` → SPA/PWA (CL-2) |
| [`ROADMAP.md`](../ROADMAP.md) | Короткий ops-backlog (M/N/E/S мітки) |
| [`docs/DESIGN.md`](DESIGN.md) | Архітектура PortableAI (Edge + Twin + LoRA) |
| [`docs/GAP_ANALYSIS.md`](GAP_ANALYSIS.md) | Що є vs що будувати |
| [`docs/COMPUTER_USE.md`](COMPUTER_USE.md) | Computer Use C0–C6 |
| [`docs/AGENT_MODE_ROADMAP.md`](AGENT_MODE_ROADMAP.md) | Agent Mode AM-0…AM-4 (Computer tab, planning) |

---

## Baseline (підтверджено 2026-06-05)

| Компонент | Стан | Деталь |
|-----------|------|--------|
| Ollama (хост) | ✅ **GPU** | усі layers qwen2.5:7b у VRAM |
| nomic-embed-text | ✅ GPU | усі layers у VRAM |
| VRAM | ✅ вистачає | qwen ~4.6 GiB + embed ~0.5 GiB вміщаються |
| Мікросервіси | ✅ Live + CI green | gateway, tools, memory, whisper, tts, twin |
| Computer Use C0–C6 | ✅ Tested | hostagent, confirm, audit, Playwright |
| jarvis_core | ✅ Wired | bootstrap.py → production path |
| ModelRegistry | ✅ Tested | candidate / active / archived / rollback |
| dataset_export | ✅ Live | JSONL → ShareGPT, train/holdout split |

> **Примітка:** рядок `Library:cpu` у `app.log` (2026-06-01 22:57) — початковий запуск
> після першого встановлення. З 2026-06-03 12:43 Vulkan використовується стабільно.

---

## Критичний борг (відкрито)

| Пріоритет | Борг | Локація | Вплив |
|-----------|------|---------|-------|
| 🟡 важливо | ~~Alembic migrations (версіонування embed dim)~~ | `memory/migrations/` | ✅ 3.3 |
| 🟢 nice | C3 live TG smoke | ручне QA | Completeness |
| 🟢 nice | Edge: покласти koboldcpp + GGUF на USB | `edge/models/`, `edge/engines/` | Manual |

---

## Фаза 0 — Операційна стабільність · **зараз**

**Мета:** security debt закритий, autostart доведений після cold boot.

| # | Задача | DoD | Статус |
|---|--------|-----|--------|
| **M4** | Ротувати Telegram-токен: @BotFather → `/revoke` → `.env` → `docker compose restart gateway` | Новий токен, старий revoked | [x] |
| 0.1 | Reboot smoke: cold boot → бот відповідає < 5 хв без ручних дій | `verify_stack.ps1` green після ребуту | [x] stack ~2.3 хв; autostart hostagent fix |

**Вихід фази 0:** security debt закритий, autostart доведений.

---

## Фаза 1–2 — UX + Computer Use · **завершено (~92%)**

```
✅ UX:           профіль, summarization, voice E2E, streaming editMessageText
✅ Mini App:     статус, runtime flags, computer log, sessions, canvas
✅ Computer Use: C0–C6, trust model, rate limit, audit trail
✅ Browser:      Playwright C3, DOM read/click/fill, confirm
✅ Tools:        notes, reminders (ICS), image gen (SD Forge), OCR, vision
✅ Multi-user:   whitelist, /allow, guest rate limit, per-user isolation

[ ] C3 live TG smoke (API smoke ✅, live Telegram ще не перевірено)
[ ] Named tunnel лише для /app (opt-in Cloudflare, бот лишається на polling)
```

---

## Фаза 3 — Власний мозок: перша LoRA · **активна (~82%)**

### Що зроблено

| Компонент | Статус | Файл |
|-----------|--------|------|
| ModelRegistry | ✅ | `twin/app/registry.py` |
| SessionLogger | ✅ | `tools/app/session_ingest.py` |
| dataset_export (filters + ShareGPT split) | ✅ | `tools/app/dataset_export.py` |
| Eval harness skeleton | ✅ (format-only) | `training/eval/run_eval.py` + `gate.py` |
| train_unsloth.py (Unsloth QLoRA + dry-run + GGUF) | ✅ | `training/runpod/train_unsloth.py` |
| Modelfile.lora.template | ✅ | `training/ollama/` |
| link_active_lora (Blue-Green) | ✅ | `scripts/link_active_lora.ps1` |

### Critical path до першої LoRA

```
① Набір ~500 кураційних прикладів
     scripts/export_dataset.ps1 → ручна курація → sharegpt_train.jsonl

② ~~Доробити train_unsloth.py~~
     FastLanguageModel + SFTTrainer + `--export-gguf` + `--dry-run`
     → model.save_pretrained_gguf("lora_v1", tokenizer, "q4_k_m")

③ RunPod burst (споживчий CUDA-GPU / A100, ~$2–5)
     → lora_v1.gguf → download → data/twin/lora/

④ Зареєструвати та промоутити
     registry.register_lora("v1", path, eval_score)
     registry.promote("v1")
     scripts/link_active_lora.ps1

⑤ Ollama Modelfile → live test у Telegram
     training/ollama/Modelfile.lora.template → ollama create jarvis-v1
```

### Відкритий борг

| # | Задача | Вплив |
|---|--------|-------|
| 3.1 | **LLM-as-judge** в eval gate | ✅ `training/eval/judge.py`, `--with-judge` у gate |
| 3.2 | Promote/rollback → Ollama live (wire end-to-end) | ✅ `tools/app/lora_deploy.py`, auto deploy з Platform |
| 3.3 | Alembic перша міграція | ✅ `memory/migrations/` — schema_meta + projects, `scripts/memory_migrate.ps1` |

**Вихід фази 3:** перша LoRA з eval score, rollback `registry.rollback()` за одну команду.

---

## Фаза 4 — Edge USB · **активна (~70%)**

> **Залежність:** LoRA v1 з фази 3 + KoboldCPP GGUF (модель/бінарник — вручну на USB).

| # | Задача | Статус |
|---|--------|--------|
| 4.1 | KoboldCPP + qwen2.5-7b-q4_k_m.gguf на USB layout (`edge/`) | [x] layout + `run_win.bat` / `run_linux.sh` |
| 4.2 | `KoboldAdapter(LLMInterface)` — той самий agent loop | [x] `jarvis_core` + `LLM_BACKEND=kobold` у tools |
| 4.3 | SQLite RAG (Edge offline) | [x] `edge/rag.py` |
| 4.4 | SyncAgent: OFFLINE/LAN/VPN → push/pull delta | [x] `edge/edge_sync.py` + `GET /registry/lora/active/download` |
| 4.5 | `run_win.bat` / `run_linux.sh` one-click | [x] |

**Вихід фази 4:** флешка офлайн → LAN → проксі на Twin; LoRA sync автоматичний.

---

## Фаза 5 — Якість і observability · **~85%**

| Статус | Задача |
|--------|--------|
| ✅ | Contract tests host-agent ↔ tools |
| ✅ | Golden traces (`tools/tests/golden/`) |
| ✅ | X-Request-ID middleware (gateway → tools) |
| ✅ | Threat model + computer rollback runbook |
| ✅ | **tok/s** у dashboard — ключова метрика GPU швидкості |
| ✅ | Alembic migrations (`memory/migrations/`, schema_meta.embed_dim) |
| [ ] | S1 Redis queue + workers (YAGNI — лише при реальному навантаженні) |

---

## Фаза 6 — Platform Web Console · **P0–P12 done (100%)**

**Мета:** єдиний `/platform` — бачиш стан системи, тестуєш агента, керуєш памʼяттю
та проєктами, відстежуєш довгі задачі. Telegram — канал споживання; Platform — штаб.

**Наступна фаза:** Phase 7 Advanced (eval pipeline, LoRA MoE) або ops backlog.

### P0 — Shell + Core tabs (1–2 тижні)

| # | Задача | DoD | Статус |
|---|--------|-----|--------|
| P0.1 | `gateway/app/platform/` router + `static/platform.html` | `/platform` відкривається, auth | [x] |
| P0.2 | **Overview** — merge admin + dashboard metrics | Health, Ollama, models, p50/p95 | [x] |
| P0.3 | **Workbench** — SSE `/agent/stream`, mode picker, tool trace | Prompt → streaming відповідь | [x] |
| P0.4 | **Memory browser** — search pgvector, notes, profile, `project_id` filter | GET `/platform/api/memory/*` | [x] |
| P0.5 | **Logs** — tail `data/logs/sessions/*.jsonl` | Фільтр user_id, mode, limit | [x] |
| P0.6 | **Settings** — runtime flags + read-only .env | POST flags як `/app/flags` | [x] |
| P0.7 | **Users** — перенести access з `/admin` | approve / deny / revoke | [x] |
| P0.8 | **Models** — Ollama tags, CHAT/AGENT, LoRA status | Promote/rollback для admin | [x] |
| P0.9 | Тести `gateway/tests/test_platform.py` | Auth, overview, workbench mock | [x] |
| P0.10 | `/admin` → «legacy» banner на `/platform` | Backward compat | [x] |

**Baseline для reuse:**

| Компонент | Файл | Для Platform |
|-----------|------|--------------|
| Admin API | `gateway/app/admin_panel.py` | Overview, Users, Settings |
| Mini App API | `gateway/app/webapp.py` | Flags, mode, sessions |
| Metrics | `tools/app/metrics.py` | Overview charts |
| Session logs | `tools/app/session_ingest.py` | Logs tab |
| Auth | `gateway/app/telegram_webapp_auth.py` | Platform auth |
| Dashboard payload | `tools/app/bootstrap.py` | Status API |

### P1 — Projects (2 тижні)

**Мета:** ізольовані workspace (як Claude Projects / Cursor folders).

| # | Задача | Статус |
|---|--------|--------|
| P1.1 | Schema: `projects`, `project_files`, `messages.project_id` (idempotent SQL) | [x] |
| P1.2 | CRUD projects API | [x] |
| P1.3 | Scoped RAG — embed/search з `project_id` filter | [x] |
| P1.4 | System prompt per project | [x] |
| P1.5 | Platform UI: project switcher, files attach | [x] |
| P1.6 | Telegram: `/project` list/switch/create | [x] |
| P1.7 | **Project files → agent context** (`include_content`, budget 12k) | [x] |

### P2 — Background Jobs (1–2 тижні) · **done**

| # | Задача | Статус |
|---|--------|--------|
| P2.1 | Redis `jarvis:bgjob:{id}` + queue `jarvis:bgjob:queue` (окремо від macro ZSET) | [x] |
| P2.2 | Worker loop (`bg_job_runner`) → notify Telegram | [x] |
| P2.3 | API `POST/GET/DELETE /bgjobs` (+ `/platform/api/jobs`) | [x] |
| P2.4 | Platform Jobs tab — create, list, cancel, auto-refresh | [x] |

### Workbench extras (P0.3+)

| # | Задача | Статус |
|---|--------|--------|
| WB.1 | Computer confirm flow (approve/deny/resume SSE) | [x] |

### P3 — Planning Mode (2 тижні)

**Мета:** plan → approve → execute.

| # | Задача | Статус |
|---|--------|--------|
| P3.1 | `POST /agent/plan` → structured plan JSON (steps[], risks[]) | [x] |
| P3.2 | Plan storage Redis/DB + TTL | [x] |
| P3.3 | `POST /agent/plan/{id}/execute` — step-by-step з progress | [x] |
| P3.4 | Platform plan viewer + approve/deny | [x] |
| P3.5 | Telegram inline ✅/❌ на plan | [x] |

### P4 — Deep Research · **done**

| # | Задача | Статус |
|---|--------|--------|
| P4.1 | Multi-hop orchestrator (`research.py`) + citations | [x] |
| P4.2 | bg job type `deep_research` + worker dispatch | [x] |
| P4.3 | Platform Research tab + Jobs type selector | [x] |

### P5 — MCP Gateway MVP · **done**

| # | Задача | Статус |
|---|--------|--------|
| P5.1 | `mcp_gateway.py` stdio + allowlist (`MCP_SERVERS_JSON`) | [x] |
| P5.2 | Agent tool `mcp_call` + `/mcp/*` API | [x] |
| P5.3 | Platform MCP status tab + THREAT_MODEL update | [x] |

### P6 — Connectors MVP · **done**

| # | Задача | Статус |
|---|--------|--------|
| P6.1 | Notion search/read (`NOTION_TOKEN`) | [x] |
| P6.2 | Slack post/list channels (`SLACK_BOT_TOKEN`) | [x] |
| P6.3 | Calendar ICS + reminders (`CALENDAR_ICS_URL`) | [x] |
| P6.4 | Platform Connectors status tab | [x] |

### P7 — Skills library · **done**

| # | Задача | Статус |
|---|--------|--------|
| P7.1 | `data/skills/*/SKILL.md` loader + budget | [x] |
| P7.2 | Active skill Redis + agent inject | [x] |
| P7.3 | Platform Skills tab | [x] |

### P8 — Subagents · **done**

| # | Задача | Статус |
|---|--------|--------|
| P8.1 | spawn + budget_iters + Redis runs | [x] |
| P8.2 | bg job type `subagent` + worker | [x] |
| P8.3 | Agent tool `spawn_subagent` + Platform tab | [x] |

### P10 — Hooks · **done**

| # | Задача | Статус |
|---|--------|--------|
| P10.1 | `data/hooks/` pre_turn / post_tool / on_error | [x] |
| P10.2 | Wire у AgentRunner run + tool loop | [x] |
| P10.3 | Platform Hooks status tab | [x] |

### P9 — Agent Teams · **done**

| # | Задача | Статус |
|---|--------|--------|
| P9.1 | Researcher → Coder → Reviewer pipeline (`teams.py`) | [x] |
| P9.2 | bg job `agent_team` + worker | [x] |
| P9.3 | Platform Teams tab | [x] |

### P11 — OpenAI-compatible API · **done**

| # | Задача | Статус |
|---|--------|--------|
| P11.1 | `POST /v1/chat/completions` (opt-in `ENABLE_OPENAI_API`) | [x] |
| P11.2 | Bearer auth + stream SSE | [x] |
| P11.3 | `GET /v1/models` | [x] |

### P12 — Cursor tasks (Telegram + Computer Use) · **done**

| # | Задача | Статус |
|---|--------|--------|
| P12.1 | `tools/app/cursor_tasks.py` — host CLI + cloud API fallback | [x] |
| P12.2 | Telegram `/cursor` + reply keyboard 🧠 | [x] |
| P12.3 | Computer Use fast path (`cursor:` prefix) + `cursor_task` tool | [x] |
| P12.4 | bg job type `cursor_task` | [x] |

> Потрібен `CURSOR_API_KEY` у `.env` для live cloud/host-agent path.

### P4+ — Майбутні можливості

| Фаза | Можливість | Умова старту |
|------|------------|--------------|
| P4 | Deep Research (multi-hop + citations) | [x] P2 Jobs |
| P5 | MCP Gateway (stdio + SSE transport) | [x] Threat model updated |
| P6 | Connectors (Calendar, Notion, Slack) | [x] native tools MVP |
| P7 | Skills library (`data/skills/`) | [x] P1 Projects |
| P8 | Subagents (spawn + budget) | [x] P3 Planning |
| P9 | Agent Teams (Researcher + Coder + Reviewer) | [x] P8 |
| P10 | Hooks (pre_turn / post_tool / on_error) | [x] P1 Projects |
| P11 | OpenAI-compatible API (opt-in) | [x] |
| P12 | Cursor tasks (Telegram + Computer Use) | [x] |

---

## Фаза 7 — Advanced · **активна (~40%)**

| # | Фіча | Статус |
|---|------|--------|
| 7.1 | Multi-agent (Orchestrator + Critic) | ✅ `tools/app/orchestrator.py`, bg job + Platform API |
| 7.2 | Self-improving loop (авто-датасет + human gate) | ✅ `tools/app/self_improve.py`, judge → pending → review → export |
| 7.3 | Domain LoRA swap (MoE-стиль) | 2+ LoRA в registry |
| 7.4 | llama.cpp benchmark vs Ollama/Vulkan | Bottleneck підтверджений |
| 7.5 | WireGuard замість cloudflared | Потрібен Edge з будь-якої точки |

---

## Edition matrix (ціль)

| Edition | Включено |
|---------|----------|
| **Core** | Chat, RAG, STT, streaming, Mini App, multi-user, Platform P0 |
| **Pro** | + Computer Use C0–C5, macros, health_watch, image gen, Platform P1–P2 |
| **Studio** | + Twin training sync, LoRA deploy, Edge USB, eval dashboard, Platform P3–P7 |

---

## Пріоритетна черга — наступні 4 тижні

```
Тиждень 1 — security + stability
  ① ~~M4: ротувати Telegram-токен~~ ✅
  ② ~~Reboot smoke end-to-end~~ ✅ (Forge опційно)

Тиждень 2 — перший LoRA датасет
  ③ 200–300 кураційних прикладів (export_dataset.ps1 + курація)
  ④ Доробити train_unsloth.py → SFTTrainer + save_pretrained_gguf

Тиждень 3 — перший training run
  ⑤ RunPod burst → QLoRA → lora_v1.gguf
  ⑥ ~~Eval gate: LLM-as-judge для holdout~~ ✅

Тиждень 4 — promote + metrics
  ⑦ ~~register → promote → Ollama Modelfile → live test у Telegram~~ ✅ deploy wired
  ⑧ ~~tok/s метрика → dashboard~~ ✅
```

---

## KPI (щомісячний огляд)

| KPI | Ціль | Стан (2026-06-05) |
|-----|------|-------------------|
| Uptime після ребуту | 100% без ручних кроків | ✅ compose ~2.3 хв (2026-06-05) |
| P95 chat (warm, GPU) | < 8 с | ✅ ~3–5 с (Vulkan, 29/29 layers) |
| P95 agent + 1 tool | < 25 с | ✅ ~10–15 с |
| Computer success (whitelist) | > 90% | ✅ C0–C6 реалізовані |
| Eval після LoRA | ↑ vs baseline | 🔲 перший run попереду |
| Security incidents | 0 | ✅ M4 закрито (новий бот) |

---

## Свідомо не робимо

- **Embed dim міграція** без Alembic — зміна `nomic-embed-text` = повний re-embed
- **`ENABLE_CODE_EXEC=true`** без sandbox-ізоляції
- **Ollama в Docker** на AMD Windows — немає `/dev/dri`/`/dev/kfd` у WSL2 (E2: НІ)
- **Переписати на FastStream/Celery** — async FastAPI справляється із запасом 100×
- **n8n як оркестратор** — legacy `profiles: ["legacy"]`
- **React SPA** до P6+ — vanilla JS як `/admin` (Vite опційно пізніше)
- **Computer Use UI** у Platform MVP — окремий контур, лишається в Telegram + `/app`
- **MCP без threat model** — untrusted code execution risk

---

## Архітектурні рішення (ADR)

| ADR | Рішення | Причина |
|-----|---------|---------|
| ADR-001 | KoboldCPP для Edge | USB portable, один бінарник, GGUF |
| ADR-002 | QLoRA r=16 (Unsloth) | споживчий CUDA-GPU справляється, адаптер 80–200 MB |
| ADR-003 | SQLite-vec для Edge RAG | Нульові залежності, один файл |
| ADR-004 | Modular monolith для Twin | Один розробник, zero network overhead |
| ADR-005 | Event Bus для внутрішньої координації Twin | Підписник додається без зміни publisher; уникає tight coupling прямих викликів і зайвої залежності від Redis Pub/Sub |
| ADR-006 | Blue-Green через symlinks | Instant rollback, zero downtime |
| ADR-007 | Training → RunPod (cloud-burst) | Unsloth CUDA-only; AMD ROCm на Windows — НІ |
| ADR-008 | Self-improve scan — навмисно ручний тригер (`POST /improve/scan`) | Human-in-the-loop: judge відбирає кандидатів, але людина мусить review'ити перед export у training set — авто-scan ризикує засмітити датасет неякісними прикладами без нагляду |
| E2 | Ollama на ХОСТІ (не Docker) | AMD `/dev/dri`/`/dev/kfd` недоступні у WSL2 |

---

## Історія оновлень

| Дата | Версія | Зміна |
|------|--------|-------|
| 2026-06-05 | 1.0 | Початковий roadmap: 12 можливостей, Platform P0–P11 |
| 2026-06-07 | 1.6 | P12 Cursor tasks (Telegram + Computer Use) — Фаза 6 закрита (P0–P12, 100%) |
| 2026-06-05 | 1.5 | P9 Agent Teams, P11 OpenAI API |
| 2026-06-05 | 1.4 | P7 Skills, P8 Subagents, P10 Hooks |
| 2026-06-05 | 1.3 | P3 Planning, P4 Research, P5 MCP, P6 Connectors |
| 2026-06-05 | 1.2 | P1.7 files inject, Memory notes/project_id, Workbench confirm, P2 bg jobs |
| 2026-06-05 | 1.1 | Оновлено baseline (Vulkan GPU підтверджено), критичний борг, пріоритетна черга |

---

*JARVIS Platform Roadmap — оновлюйте чекбокси при закритті задач.*
*Ops-деталі: [`ROADMAP.md`](../ROADMAP.md) · Загальний продукт: [`PRODUCT_ROADMAP.md`](PRODUCT_ROADMAP.md) · Архітектура: [`DESIGN.md`](DESIGN.md)*