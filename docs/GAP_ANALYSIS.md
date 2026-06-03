# PortableAI vs поточний JARVIS — Gap-аналіз

> Як `DESIGN.md` (PortableAI: Edge+Twin+fine-tuning) співвідноситься з тим,
> що **вже збудовано** (microservices Telegram-бот, PR #1). Що реюзабельне,
> що з нуля, що викинути, у якому порядку будувати.

## TL;DR

**Поточний стек ≈ готовий «Twin».** Те, що в PR #1 (FastAPI-сервіси, агент-луп,
pgvector RAG, Ollama+Vulkan, tools, STT/TTS, docker) — це 80% ролі HQ з дизайну.
Реально новий код: **Edge (USB/KoboldCPP)**, **Sync-протокол**, **ModelRegistry**,
**training pipeline**. Залізне обмеження: **тренування (Unsloth/QLoRA) НЕ йде на AMD** —
тільки cloud (RunPod) або окрема NVIDIA-машина.

---

## Покомпонентна мапа

| PortableAI (DESIGN) | Поточний JARVIS | Вердикт |
|---|---|---|
| **Twin: InferenceServer** (KoboldCPP/vLLM GPU) | Ollama на хості (Vulkan, доведено) | **REUSE** — лишаємо Ollama як Twin-інференс через `LLMInterface`/Adapter |
| **Twin: SyncServer** (/ingest/logs, /latest/lora) | gateway (FastAPI-патерни) | **NEW** — новий модуль, але патерни/каркас з gateway |
| **Twin: ModelRegistry** (SQLite версії+eval) | — | **NEW** (малий, чистий Python/SQLite) |
| **Twin: TrainingService** (Unsloth QLoRA) | — | **NEW + BLOCKED локально** (немає NVIDIA → RunPod) |
| **Twin: BackupService** (rclone) | — | **NEW** (малий) |
| **Twin: Scheduler** (APScheduler) | — | **NEW** (малий) |
| **Twin: Dashboard** (React) | — (n8n UI частково) | **NEW** (можна відкласти; спершу CLI/HTML) |
| **Twin: VPNGateway** (WireGuard) | cloudflared tunnel | **ADAPT** — tunnel уже працює; WireGuard опц. |
| **Edge: InferenceEngine** (KoboldCPP) | Ollama (інша обгортка) | **NEW рантайм** — Adapter (`KoboldAdapter`) міст |
| **Edge: RAGEngine** (SQLite-vec) | memory/pgvector (серверний) | **NEW** — Edge офлайн потребує SQLite-vec; pgvector лишається на Twin |
| **Edge: MemoryManager** (summarization) | tools/agent context + memory | **ADAPT** — логіка є, перенести в Edge-формат |
| **Edge: InputDecorator** | `agent._sys_with_ctx` + prompt-build | **REUSE** — це вже наш код у `tools/app/agent.py` |
| **Edge: SessionLogger** (JSONL) | — (httpx-логи не те) | **NEW** (малий, append-only) |
| **Edge: SyncAgent** (sidecar) | — | **NEW** |
| **Агент-луп** (routing, tool-calling, inline-fix) | `tools/app/agent.py` | **REUSE — це коронна коштовність**, рантайм-агностична |
| **Toolkit** (calc/search/fetch/notes) | `tools/app/toolkit.py` | **REUSE** (Twin повний, Edge — subset) |
| **STT / TTS** | whisper + tts (piper) | **REUSE** на обох |
| **n8n** (orchestrator-proxy) | n8n (тонкий проксі) | **DISCARD** — PortableAI не має оркестратора; агент-луп уже в Python |
| **Telegram I/O** | gateway | **KEEP як канал** — стає одним із UI до Twin (поряд із KoboldCPP web UI на Edge) |

---

## Що ВИКИНУТИ з поточного

- **n8n** — у PortableAI оркестрації-проксі немає, агент-луп живе в Python. Ми ще в
  Фазі 6 зазначили n8n як «seam»; PortableAI цей seam закриває. Мінус один контейнер.
- Нічого більше — решта або reuse, або adapt.

---

## Залізна реальність (визначає план)

| Задача | На AMD RX 5700 XT | Висновок |
|---|---|---|
| **Inference** (Edge+Twin) | ✅ Ollama+Vulkan (доведено ~50-60 tok/s), KoboldCPP на CPU | будуємо локально |
| **Embeddings/RAG** | ✅ nomic на Vulkan / SQLite-vec на CPU | локально |
| **Training (Unsloth QLoRA)** | ❌ потребує CUDA, ROCm не підтримується | **тільки RunPod / NVIDIA-бокс** |

**Наслідок для приватності:** теза «privacy абсолютна» (P-принципи) **не витримує** training-фазу —
датасет їде на RunPod. Чесне формулювання: *inference* суверенний; *training* — ephemeral
cloud-burst (інстанс піднявся, навчив, знищився; дані не лишаються). Це треба вписати в DESIGN.

---

## Рекомендований порядок білду (під наше залізо)

**Етап A — «Twin-ізація» поточного стеку (найдешевше, реюз 90%)**
1. `ModelRegistry` (SQLite: версії LoRA/промптів + eval score + status) — backbone усього.
2. `SyncServer` ендпойнти на gateway/окремому сервісі: `POST /ingest/logs`, `GET /latest/lora`.
3. `SessionLogger` (JSONL append-only) — сире джерело для майбутніх датасетів.
   → Усе чистий Python, тестується зараз, без GPU.

**Етап B — Edge MVP (новий портативний артефакт)**
4. KoboldCPP + GGUF (qwen2.5-7b, у нас уже є в Ollama — треба сирий .gguf) на USB-розкладці.
5. `KoboldAdapter(LLMInterface)` — щоб агент-луп працював і на Kobold, і на Ollama.
6. `SyncAgent` (mode-detect: OFFLINE/LAN/VPN) + Edge `SQLite-vec` RAG.

**Етап C — Дані (справжній critical path, без GPU)**
7. Курація 500 прикладів (експорти Claude → чистка → ShareGPT). 80% успіху fine-tune тут.
8. Eval-харнес (50 holdout) + **correctness-gate** (не лише format keywords — LLM-as-judge).

**Етап D — Training (BLOCKED локально)**
9. RunPod QLoRA pipeline (Unsloth) → LoRA → register у ModelRegistry → Blue-Green deploy.
   → Робимо коли (а) є датасет, (б) є RunPod-доступ або NVIDIA.

**Старт:** Етап A, крок 1 — `ModelRegistry`. Малий, тестований, нічого не блокує, і
від нього залежить весь deploy/training-цикл.

---

## Збіг патернів (приємний бонус)

DESIGN вже передбачає міст до поточного коду:
- **Adapter** (`KoboldAdapter`/`OllamaAdapter`) — рівно те, що дозволяє лишити Ollama на Twin.
- **Circuit Breaker** Edge↔Twin — у нас уже є breaker в `tools/app/ollama.py`.
- **Strategy** для RAG — Edge keyword/SQLite-vec, Twin pgvector hybrid.
- **Memento/Command** для LoRA-rollback — лягає на ModelRegistry.status.

Тобто PR #1 — не глухий кут, а фундамент Twin.
