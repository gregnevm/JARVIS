# JARVIS Platform — Roadmap

> **Версія:** 1.1 (2026-06-05)
> **Статус:** Living document — оновлюється після кожного milestone.
> **Scope:** sovereign self-hosted personal AI — Telegram, RAG, voice, computer use,
> LoRA fine-tuning, Edge USB, web console `/platform`.

**Пов'язані документи**

| Документ | Роль |
|----------|------|
| [`ROADMAP.md`](../ROADMAP.md) | Короткий ops-backlog (M/N/E/S мітки) |
| [`docs/DESIGN.md`](DESIGN.md) | Архітектура PortableAI (Edge + Twin + LoRA) |
| [`docs/GAP_ANALYSIS.md`](GAP_ANALYSIS.md) | Що є vs що будувати |
| [`docs/PRODUCT_ROADMAP.md`](PRODUCT_ROADMAP.md) | Деталізовані фази 0–7 з чекбоксами |
| [`docs/COMPUTER_USE.md`](COMPUTER_USE.md) | Computer Use C0–C6 |

---

## Baseline (підтверджено 2026-06-05)

| Компонент | Стан | Деталь |
|-----------|------|--------|
| Ollama (хост) | ✅ **Vulkan GPU** | 29/29 layers qwen2.5:7b у VRAM, 8 GiB |
| nomic-embed-text | ✅ Vulkan GPU | 13/13 layers у VRAM |
| VRAM загалом | ✅ 8.0 GiB | qwen ~4.6 GiB + embed ~0.5 GiB ≈ 2.9 GiB вільно |
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
| 🔴 **критично** | **M4 — Telegram-токен не ротований** (інцидент 2026-06-03) | `.env` | Security |
| 🟡 важливо | LLM-as-judge у eval gate (зараз format-only) | `training/eval/gate.py` | Якість LoRA |
| 🟡 важливо | Promote/rollback LoRA → Ollama live | `scripts/link_active_lora.ps1` | LoRA pipeline |
| 🟡 важливо | Alembic migrations (версіонування embed dim) | `memory/app/db.py` | DB safety |
| 🟢 nice | tok/s метрика → dashboard | `tools/app/metrics.py` | Observability |
| 🟢 nice | C3 live TG smoke | ручне QA | Completeness |

---

## Фаза 0 — Операційна стабільність · **зараз**

**Мета:** security debt закритий, autostart доведений після cold boot.

| # | Задача | DoD | Статус |
|---|--------|-----|--------|
| **M4** | Ротувати Telegram-токен: @BotFather → `/revoke` → `.env` → `docker compose restart gateway` | Новий токен, старий revoked | **[ ] ВІДКРИТО** |
| 0.1 | Reboot smoke: cold boot → бот відповідає < 5 хв без ручних дій | `verify_stack.ps1` green після ребуту | [ ] |

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

## Фаза 3 — Власний мозок: перша LoRA · **активна (~60%)**

### Що зроблено

| Компонент | Статус | Файл |
|-----------|--------|------|
| ModelRegistry | ✅ | `twin/app/registry.py` |
| SessionLogger | ✅ | `tools/app/session_ingest.py` |
| dataset_export (filters + ShareGPT split) | ✅ | `tools/app/dataset_export.py` |
| Eval harness skeleton | ✅ (format-only) | `training/eval/run_eval.py` + `gate.py` |
| train_unsloth.py skeleton | ✅ (TODO SFTTrainer) | `training/runpod/train_unsloth.py` |
| Modelfile.lora.template | ✅ | `training/ollama/` |
| link_active_lora (Blue-Green) | ✅ | `scripts/link_active_lora.ps1` |

### Critical path до першої LoRA

```
① Набір ~500 кураційних прикладів
     scripts/export_dataset.ps1 → ручна курація → sharegpt_train.jsonl

② Доробити train_unsloth.py
     # TODO: FastLanguageModel.from_pretrained + SFTTrainer block
     → model.save_pretrained_gguf("lora_v1", tokenizer, "q4_k_m")

③ RunPod burst (RTX 3060+ / A100, ~$2–5)
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
| 3.1 | **LLM-as-judge** в eval gate | Факти не дрейфують при self-improving loop |
| 3.2 | Promote/rollback → Ollama live (wire end-to-end) | LoRA не активується автоматично |
| 3.3 | Alembic перша міграція | Безпечна зміна embed dim |

**Вихід фази 3:** перша LoRA з eval score, rollback `registry.rollback()` за одну команду.

---

## Фаза 4 — Edge USB · **не почата**

> **Залежність:** LoRA v1 з фази 3 + KoboldCPP GGUF.

| # | Задача | Статус |
|---|--------|--------|
| 4.1 | KoboldCPP + qwen2.5-7b-q4_k_m.gguf на USB layout (`/PortableAI/`) | [ ] |
| 4.2 | `KoboldAdapter(LLMInterface)` — той самий agent loop | [ ] |
| 4.3 | SQLite-vec RAG (Edge offline, нульові залежності) | [ ] |
| 4.4 | SyncAgent: mode-detect OFFLINE / LAN / VPN → push/pull delta | [ ] |
| 4.5 | `run_win.bat` / `run_linux.sh` one-click | [ ] |

**Вихід фази 4:** флешка офлайн → LAN → проксі на Twin; LoRA sync автоматичний.

---

## Фаза 5 — Якість і observability · **~70%**

| Статус | Задача |
|--------|--------|
| ✅ | Contract tests host-agent ↔ tools |
| ✅ | Golden traces (`tools/tests/golden/`) |
| ✅ | X-Request-ID middleware (gateway → tools) |
| ✅ | Threat model + computer rollback runbook |
| [ ] | **tok/s** у dashboard — ключова метрика GPU швидкості |
| [ ] | Alembic migrations (версіонування embed dim) |
| [ ] | S1 Redis queue + workers (YAGNI — лише при реальному навантаженні) |

---

## Фаза 6 — Platform Web Console · **~15%**

**Мета:** єдиний `/platform` — бачиш стан системи, тестуєш агента, керуєш памʼяттю
та проєктами, відстежуєш довгі задачі. Telegram — канал споживання; Platform — штаб.

### P0 — Shell + Core tabs (1–2 тижні)

| # | Задача | DoD | Статус |
|---|--------|-----|--------|
| P0.1 | `gateway/app/platform/` router + `static/platform.html` | `/platform` відкривається, auth | [x] |
| P0.2 | **Overview** — merge admin + dashboard metrics | Health, Ollama, models, p50/p95 | [x] |
| P0.3 | **Workbench** — SSE `/agent/stream`, mode picker, tool trace | Prompt → streaming відповідь | [x] |
| P0.4 | **Memory browser** — search pgvector, list notes, view profile | GET `/platform/api/memory/search` | [x] |
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

### P2 — Background Jobs (1–2 тижні)

| # | Задача | Статус |
|---|--------|--------|
| P2.1 | Redis job schema `jarvis:job:{id}` (status, progress, result) | [ ] |
| P2.2 | Worker loop → notify Telegram при завершенні | [ ] |
| P2.3 | API `POST /jobs`, `GET /jobs/{id}`, cancel | [ ] |
| P2.4 | Platform Jobs tab — live progress + history 7d | [ ] |

### P3 — Planning Mode (2 тижні)

**Мета:** plan → approve → execute.

| # | Задача | Статус |
|---|--------|--------|
| P3.1 | `POST /agent/plan` → structured plan JSON (steps[], risks[]) | [ ] |
| P3.2 | Plan storage Redis/DB + TTL | [ ] |
| P3.3 | `POST /agent/plan/{id}/execute` — step-by-step з progress | [ ] |
| P3.4 | Platform plan viewer + approve/deny | [ ] |
| P3.5 | Telegram inline ✅/❌ на plan | [ ] |

### P4+ — Майбутні можливості

| Фаза | Можливість | Умова старту |
|------|------------|--------------|
| P4 | Deep Research (multi-hop + citations) | P2 Jobs |
| P5 | MCP Gateway (stdio + SSE transport) | Threat model update |
| P6 | Connectors (Calendar, Notion, Slack) | P5 MCP |
| P7 | Skills library (`data/skills/`) | P1 Projects |
| P8 | Subagents (spawn + budget) | P3 Planning |
| P9 | Agent Teams (Researcher + Coder + Reviewer) | P8 |
| P10 | Hooks (pre_turn / post_tool / on_error) | P1 Projects |
| P11 | OpenAI-compatible API (opt-in) | Personal use confirmed |

---

## Фаза 7 — Advanced · **6+ місяців**

| # | Фіча | Умова старту |
|---|------|--------------|
| 7.1 | Multi-agent (Orchestrator + Critic) | Eval pipeline стабільний |
| 7.2 | Self-improving loop (авто-датасет + human gate) | LLM-as-judge готовий |
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
  ① M4: ротувати Telegram-токен (15 хв, критично)
  ② Reboot smoke end-to-end

Тиждень 2 — перший LoRA датасет
  ③ 200–300 кураційних прикладів (export_dataset.ps1 + курація)
  ④ Доробити train_unsloth.py → SFTTrainer + save_pretrained_gguf

Тиждень 3 — перший training run
  ⑤ RunPod burst → QLoRA → lora_v1.gguf
  ⑥ Eval gate: LLM-as-judge для holdout

Тиждень 4 — promote + metrics
  ⑦ register → promote → Ollama Modelfile → live test у Telegram
  ⑧ tok/s метрика → dashboard
```

---

## KPI (щомісячний огляд)

| KPI | Ціль | Стан (2026-06-05) |
|-----|------|-------------------|
| Uptime після ребуту | 100% без ручних кроків | ⚠️ не перевірено після cold boot |
| P95 chat (warm, GPU) | < 8 с | ✅ ~3–5 с (Vulkan, 29/29 layers) |
| P95 agent + 1 tool | < 25 с | ✅ ~10–15 с |
| Computer success (whitelist) | > 90% | ✅ C0–C6 реалізовані |
| Eval після LoRA | ↑ vs baseline | 🔲 перший run попереду |
| Security incidents | 0 | ⚠️ M4 токен відкритий |

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
| ADR-002 | QLoRA r=16 (Unsloth) | RTX 3060 справляється, адаптер 80–200 MB |
| ADR-003 | SQLite-vec для Edge RAG | Нульові залежності, один файл |
| ADR-004 | Modular monolith для Twin | Один розробник, zero network overhead |
| ADR-006 | Blue-Green через symlinks | Instant rollback, zero downtime |
| ADR-007 | Training → RunPod (cloud-burst) | Unsloth CUDA-only; AMD ROCm RDNA1 Windows — НІ |
| E2 | Ollama на ХОСТІ (не Docker) | AMD `/dev/dri`/`/dev/kfd` недоступні у WSL2 |

---

## Історія оновлень

| Дата | Версія | Зміна |
|------|--------|-------|
| 2026-06-05 | 1.0 | Початковий roadmap: 12 можливостей, Platform P0–P11 |
| 2026-06-05 | 1.1 | Оновлено baseline (Vulkan GPU підтверджено), критичний борг, пріоритетна черга |

---

*JARVIS Platform Roadmap — оновлюйте чекбокси при закритті задач.*
*Ops-деталі: [`ROADMAP.md`](../ROADMAP.md) · Загальний продукт: [`PRODUCT_ROADMAP.md`](PRODUCT_ROADMAP.md) · Архітектура: [`DESIGN.md`](DESIGN.md)*
