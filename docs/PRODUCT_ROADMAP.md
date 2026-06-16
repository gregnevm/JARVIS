# JARVIS — Product Roadmap (повноцінна платформа)

> **Версія:** 2.1 (2026-06-16) — *перевизначено зі «self-hosted personal AGI» на повноцінний продукт.*
> **Статус:** Living document — парасолька над усіма трек-roadmap-ами.
> **Скоуп:** суверенна AI-платформа = **API-платформа розробника** + **агент кодування рівня Claude Code** + **мультиплатформа** (web · Telegram · mobile).

**Цей файл — стратегічна парасолька.** Принципи й цілі — у [`AGENTS.md`](../AGENTS.md). Task-level
чекбокси — у трек-roadmap-ах (нижче). Тут — **фазовий** статус і послідовність.

| Документ | Роль |
|----------|------|
| [`AGENTS.md`](../AGENTS.md) | **Конституція**: місія, принципи, 3 цілі-стовпи |
| [`docs/CODING_AGENT_ROADMAP.md`](CODING_AGENT_ROADMAP.md) | Стовп B — агент кодування (CA-0…CA-6) |
| [`docs/API_PLATFORM_ROADMAP.md`](API_PLATFORM_ROADMAP.md) | Стовп A — API-платформа (AP-0…AP-6) |
| [`docs/CLIENTS_ROADMAP.md`](CLIENTS_ROADMAP.md) | Стовп C — клієнти web/TG/mobile (CL-0…CL-5) |
| [`docs/PLATFORM_ROADMAP.md`](PLATFORM_ROADMAP.md) | Web-консоль `/platform` P0–P12 + Phase 7 |
| [`docs/AGENT_MODE_ROADMAP.md`](AGENT_MODE_ROADMAP.md) | Computer Use / desktop AM-0…AM-4 |
| [`docs/SAAS_DEEP_DIVE.md`](SAAS_DEEP_DIVE.md) | Мультитенант enabler (PR#0…#7) |
| [`ROADMAP.md`](../ROADMAP.md) · [`docs/DESIGN.md`](DESIGN.md) · [`docs/GAP_ANALYSIS.md`](GAP_ANALYSIS.md) | Ops · архітектура · gap |

---

## 1. Позиціонування

### 1.1 Обіцянка (оновлена)

**JARVIS** — суверенна платформа, яку можна споживати трьома способами одночасно:
- 🅰 **як API** (`Bearer sk-jarvis-…`) — розробник підключає свій код/агентів, як до OpenAI/Anthropic;
- 🅱 **як агент кодування** — repo-aware, diff-edit, тест-луп, рев'ю; рівень Claude Code, але локально;
- 🅲 **як асистент** — Telegram-чат, web-штаб `/platform`, мобільний застосунок.

Inference локальний (Ollama/Vulkan, Edge/Kobold). Зовнішні AI-API — лише явний opt-in.

### 1.2 Диференціатори

- **Sovereignty:** $0 inference, дані не виходять із машини, повний контроль (vs cloud-only платформи).
- **Один бекенд — три способи споживання** (API / coding-agent / асистент) під спільною auth.
- **Computer Use з аудитом** — агент реально керує Windows-хостом (PS/CLI/browser/UIA), tier-ladder.
- **PortableAI:** Twin (домашній стек) → Edge (USB) → персональна LoRA з твоїх діалогів.

### 1.3 Чесні обмеження

| Теза | Реальність |
|------|------------|
| «Якість як frontier (GPT-4/Claude)» | Ні на локальній 7B — компенсація: privacy, $0, контроль, fine-tune під себе |
| «Privacy абсолютна» | Inference — так; **training** — ephemeral RunPod (ADR-007), датасет тимчасово залишає машину |
| «Claude Code з коробки» | Ціль, не поточний стан — Стовп B на старті (мости cursor/continue → рідний агент) |
| QLoRA локально на RX 5700 XT | Ні — cloud-burst або окрема NVIDIA |

### 1.4 North Star (12 місяців)

> Розробник додає `base_url=https://my-jarvis/v1` і ганяє агентів на своєму залізі за $0/токен.
> З телефона пише: «полагодь падіння тестів у репо X» — JARVIS-агент читає репо, править диффом,
> ганяє pytest, шле PR, звітує. Усе на власній машині; раз на місяць підтягує свіжу LoRA з Twin.

---

## 2. Архітектура продукту (фундамент + 3 стовпи)

```
        🅰 API Platform        🅱 Coding Agent         🅲 Clients (web·TG·mobile)
        (OpenAI-style)         (Claude Code-style)     (один бекенд, багато каналів)
              └───────────────────────┼───────────────────────┘
                                       ▼
              ФУНДАМЕНТ (готовий ~90%): мікросервіси · Ollama/Vulkan · агент-луп ·
              RAG · STT/TTS · Computer Use C0–C6 · Platform P0–P12 · Twin/LoRA · Edge
```

Стовпи **не починаються з нуля** — вони добудовуються над зрілим фундаментом (фази 0–7 нижче).

---

## 3. Фундамент — фази 0–7 (статус)

Деталі задач — у трек-roadmap-ах; тут лише фазовий підсумок.

| Фаза | Зміст | Статус | Детальний трек |
|------|-------|--------|----------------|
| **0** | Daily-driver ops: autostart, security, backup, smoke | ✅ done | [`ROADMAP.md`](../ROADMAP.md) |
| **1** | UX: профіль, summarization, voice E2E, streaming, Mini App | ✅ done | [`PLATFORM_ROADMAP.md`](PLATFORM_ROADMAP.md) |
| **2** | Computer Use C0–C6 (PS/CLI/browser/UIA/vision) | ✅ інфра / ⏳ автономність | [`AGENT_MODE_ROADMAP.md`](AGENT_MODE_ROADMAP.md) |
| **3** | Twin + перша LoRA (registry, dataset, eval, RunPod) | 🟡 ~82% | [`PLATFORM_ROADMAP.md`](PLATFORM_ROADMAP.md) §Фаза 3 |
| **4** | Edge USB (KoboldCPP, SQLite-vec, sync) | 🟡 ~70% | [`PLATFORM_ROADMAP.md`](PLATFORM_ROADMAP.md) §Фаза 4 |
| **5** | Якість + observability (contract/golden tests, метрики, Alembic) | ✅ ~90% | [`PLATFORM_ROADMAP.md`](PLATFORM_ROADMAP.md) §Фаза 5 |
| **6** | Web-консоль `/platform` P0–P12 (13 можливостей) | ✅ 100% | [`PLATFORM_ROADMAP.md`](PLATFORM_ROADMAP.md) §Фаза 6 |
| **7** | Advanced: Orchestrator, Self-improve, MoE LoRA | 🟡 ~40% | [`PLATFORM_ROADMAP.md`](PLATFORM_ROADMAP.md) §Фаза 7 |

**Фундамент дає стовпам:** агент-луп (`tools/app/agent.py`), `jarvis_core` (facade/pipeline/routing),
OpenAI-сумісний `/v1` (зародок API), Platform-консоль (зародок web-app), host-agent (Computer Use),
multi-user/whitelist (зародок auth), bg jobs / subagents / teams (паралелізм агента).

---

## 4. 🅰 Трек A — API-платформа розробника

**Мета:** з «один глобальний ключ» → повноцінний developer platform як OpenAI/Anthropic.
**Деталі:** [`docs/API_PLATFORM_ROADMAP.md`](API_PLATFORM_ROADMAP.md) · enabler: [`SAAS_DEEP_DIVE.md`](SAAS_DEEP_DIVE.md).

| Фаза | Зміст | Старт-умова | Статус |
|------|-------|-------------|--------|
| AP-0 | `/v1` baseline: chat+models, bearer, SSE | — | ✅ done |
| AP-1 | API-ключі: per-org keys, scopes, prefix-hash, revoke | PR#0 IDOR + tenant context | ⏳ |
| AP-2 | `/v1` повнота: `embeddings`, `responses`, tool-use, `usage` | AP-1 | ⏳ |
| AP-3 | Developer console: keys UI, usage charts, **playground**, logs | AP-1 + Platform | ⏳ |
| AP-4 | Ліміти й метеринг: rate-limit/key, plan limits, usage_events | AP-2 | ⏳ |
| AP-5 | SDK + docs: Python/JS клієнти, OpenAPI, quickstart | AP-2 | ⏳ |
| AP-6 | Білінг (cloud-only): Stripe, plans, overage | SaaS PR#5 | ⏳ |

**Вихід треку A:** сторонній розробник реєструє ключ у консолі, бачить usage, ганяє свій застосунок
проти `/v1` — без знання внутрішньої кухні.

---

## 5. 🅱 Трек B — Агент кодування (Claude Code analog)

**Мета:** з «мости cursor_task/continue_dev» → рідний repo-aware coding-агент.
**Деталі:** [`docs/CODING_AGENT_ROADMAP.md`](CODING_AGENT_ROADMAP.md) · desktop: [`AGENT_MODE_ROADMAP.md`](AGENT_MODE_ROADMAP.md).

| Фаза | Зміст | Старт-умова | Статус |
|------|-------|-------------|--------|
| CA-0 | Bridges baseline: `cursor_task`, `continue_dev`, computer PS/CLI | — | ✅ done |
| CA-1 | Рідний file-edit: read/diff/apply, workspace-скоуп, git-aware | Computer Use FS | ✅ done |
| CA-2 | Repo-context: дерево файлів, symbol-граф, scoped RAG по проєкту | P1 Projects | ✅ done (+ `repo_refs` крос-файл) |
| CA-3 | Test/build loop: запусти→прочитай fail→виправ→повтори | CA-1 | ✅ майже (3.5 live-eval — попереду) |
| CA-4 | Plan→approve→execute для коду; multi-file рефактор | P3 Planning + CA-2 | ✅ done (батч + rename_symbol) |
| CA-5 | Self-review + субагенти (Coder/Reviewer/Tester pipeline) | P8/P9 Teams | 🔄 5.2/5.4 ✅; 5.1/5.3 частково |
| CA-6 | CLI (`jarvis code …`) + IDE-режим (LSP/extension) | CA-3 | 🔄 CLI ✅ (6.1/6.2); IDE/Platform tab — попереду |

**Вихід треку B:** «полагодь тести в репо» з Telegram/CLI → агент сам редагує файли диффами,
ганяє pytest у лупі, рев'ювить, звітує. Tier-ladder і audit — як у Computer Use.

---

## 6. 🅲 Трек C — Мультиплатформа (клієнти)

**Мета:** один бекенд, багато каналів; Telegram primary, web-штаб, mobile APK.
**Деталі:** [`docs/CLIENTS_ROADMAP.md`](CLIENTS_ROADMAP.md).

| Фаза | Зміст | Старт-умова | Статус |
|------|-------|-------------|--------|
| CL-0 | Baseline: Telegram bot + Mini App + `/platform` HTML | — | ✅ done |
| CL-1 | Спільний client-API контракт (`/api/v1/*`), єдина auth (JWT+initData) | AP-1 | ⏳ |
| CL-2 | Web-app v2: `/platform` HTML → SPA/PWA (offline shell, push) | CL-1 | ⏳ |
| CL-3 | Mobile APK (Android): чат, voice, workbench, computer-confirm, push | CL-1 | ⏳ |
| CL-4 | Telegram parity з web (єдиний feature-set, deep links) | CL-1 | 🟡 частково |
| CL-5 | Desktop/tray (опційно) + крос-клієнт sync | CL-2/3 | ⏳ |

**Вихід треку C:** з телефона (APK), браузера (PWA) чи Telegram — той самий агент, та сама пам'ять,
той самий computer-confirm.

---

## 7. Послідовність (як стовпи зчіпляються)

```
СПІЛЬНИЙ ENABLER (розблоковує A і C):
  SaaS PR#0 (IDOR fix) → PR#1 jarvis_core/context + tenant headers → AP-1 keys → CL-1 client-API

Паралельні треки після enabler:
  A: AP-2 /v1 повнота → AP-3 console/playground → AP-4 limits → AP-5 SDK → AP-6 billing(cloud)
  B: CA-1 file-edit → CA-2 repo-context → CA-3 test-loop → CA-4 plan/refactor → CA-5 review → CA-6 CLI/IDE
  C: CL-2 web SPA/PWA → CL-3 mobile APK → CL-4 TG parity → CL-5 desktop

Фундамент паралельно: дотиснути Фазу 3 (перша LoRA) і Фазу 4 (Edge) за наявності датасету/USB.
```

**Найближчий критичний шлях:** `SaaS PR#0/PR#1` (tenant-фундамент) — він спільний для A і C,
і його варто зробити **до** будь-якого нового стовпа, бо потім дешевше.

---

## 8. Editions (цільова матриця)

| Edition | Канал | Включено |
|---------|-------|----------|
| **Core** | self-hosted | Chat, RAG, STT/TTS, streaming, Mini App, `/platform` базовий, `/v1` (1 ключ) |
| **Pro** | self-hosted | + Computer Use (standard), coding-агент CA-1..CA-3, image gen, Platform повний |
| **Studio** | self-hosted | + Twin/LoRA, Edge USB, coding CA-4..CA-6, Orchestrator/Teams, eval dashboard |
| **Cloud** | SaaS | Pro/Studio як сервіс: per-org keys, білінг, члени команди, hybrid connector |

Edition gating технічно лягає на plan limits (SAAS §7) + feature-флаги. Self-hosted = `SAAS_MODE=false`.

---

## 9. KPI (щомісячний огляд)

| KPI | Ціль | Стовп |
|-----|------|-------|
| Uptime після ребуту | 100% без ручних кроків | Фундамент |
| P95 chat (warm, GPU) | < 8 с | Фундамент |
| P95 agent + 1 tool | < 25 с | Фундамент |
| Computer task success (whitelist) | > 90% | B |
| Coding task: «полагодь тест» E2E success | > 70% → 90% | B |
| `/v1` сумісність (OpenAI SDK drop-in) | 100% chat/embeddings/models | A |
| Час від signup до першого API-виклику | < 5 хв | A |
| Крос-клієнт parity (фічі web vs mobile vs TG) | > 90% | C |
| Eval після LoRA | ↑ vs baseline | Фундамент/3 |
| Security incidents (auth/IDOR/computer) | 0 | усі |

---

## 10. Свідомо не робимо

Консолідовано в [`AGENTS.md` §6](../AGENTS.md). Ключове: зовнішній AI-API не дефолт; `ENABLE_CODE_EXEC`
без sandbox — ні; SaaS не ламає self-hosted; agent-loop не переписуємо на LangGraph/CrewAI; n8n — legacy.

---

## 11. Історія оновлень

| Дата | Версія | Зміна |
|------|--------|-------|
| 2026-06-04 | 1.0 | Початкова версія: self-hosted personal AGI, фази 0–7 |
| 2026-06-15 | 2.0 | Перевизначення на повноцінний продукт: 3 стовпи (API/Coding/Clients) над фундаментом; синхронізація з [`AGENTS.md`](../AGENTS.md) і трек-roadmap-ами |
| 2026-06-16 | 2.1 | Стовп B (Coding Agent) рвонув: CA-1…CA-4 ✅, CA-5/6 частково (fix-loop, transactional multi-file + rename_symbol, code-plan/review, coding teams, `jarvis code` CLI). Деталі — [`CODING_AGENT_ROADMAP.md`](CODING_AGENT_ROADMAP.md) v1.15 |

---

*Парасолька. Принципи — у [`AGENTS.md`](../AGENTS.md); деталі задач — у трек-roadmap-ах; ops — у [`ROADMAP.md`](../ROADMAP.md).*
