# JARVIS PortableAI — System Design Document
> **Version:** 1.0
> **Status:** Active
> **Scope:** Edge (USB) + Twin (Home Server) + Fine-Tuning Pipeline

> **Примітка про відношення до поточного коду:** цей документ описує цільову
> архітектуру PortableAI. Аналіз того, як поточний стек (microservices Telegram-бот)
> співвідноситься з нею — у `docs/GAP_ANALYSIS.md`. Коротко: поточний стек ≈ «Twin».

---
## Table of Contents
1. [Vision & Principles](#1-vision--principles)
2. [System Overview](#2-system-overview)
3. [Architecture Patterns](#3-architecture-patterns)
4. [AI-Specific Patterns](#4-ai-specific-patterns)
5. [GoF Patterns — Applied](#5-gof-patterns--applied)
6. [SOLID in Practice](#6-solid-in-practice)
7. [Component Design](#7-component-design)
8. [Data Flow & Protocols](#8-data-flow--protocols)
9. [Fine-Tuning Pipeline](#9-fine-tuning-pipeline)
10. [Deployment & Operations](#10-deployment--operations)
11. [Decision Log (ADR)](#11-decision-log-adr)
12. [Roadmap](#12-roadmap)
---
## 1. Vision & Principles
### 1.1 Core Concept
```
Standard portable AI  = static model in a pocket
JARVIS PortableAI     = sovereign cognitive model that belongs to you
```
PortableAI є не продуктом — це **персоналізована когнітивна інфраструктура**.
Три фундаментальні властивості системи:

**Ownership over Alignment**
Публічні моделі alignовані під "середнього користувача" + корпоративні safety filters.
Fine-tune переписує цей alignment під конкретний профіль, домен, стиль мислення.

**Knowledge Locality**
Дані — на флешці. Жодного cloud inference, жодного logging.
Privacy не як фіча — як архітектурна властивість системи.

**Compression of Expertise**
500–2000 прикладів дозволяють "заморозити" домен-специфічну логіку в ваги моделі.
Замість повторного введення контексту — модель вже знає.

---
### 1.2 Design Principles
| # | Принцип | Наслідок |
|---|---|---|
| P1 | **Offline-first** | Edge працює без мережі як primary scenario |
| P2 | **Fail Fast** | Валідація на вході, не в середині виконання |
| P3 | **Explicit over Implicit** | Ніякої магії, стан явний, залежності явні |
| P4 | **Composition over Inheritance** | Поведінка збирається з частин, не наслідується |
| P5 | **Open/Closed** | Новий транспорт/стратегія — новий клас, не зміна існуючого |
| P6 | **YAGNI** | Реалізуємо те що потрібно зараз, не "на майбутнє" |
| P7 | **Single Source of Truth** | Model Registry — єдиний авторитет про версії |
| P8 | **Separation of Concerns** | Training ≠ Inference ≠ Sync ≠ UI |
---
### 1.3 Quality Attributes (трейдофи)
```
Attribute          Edge Priority    Twin Priority
─────────────────────────────────────────────────
Privacy            CRITICAL         HIGH
Latency            HIGH             MEDIUM
Accuracy           MEDIUM           HIGH
Availability       MEDIUM           HIGH
Scalability        LOW              MEDIUM
Maintainability    HIGH             HIGH
```
Свідомий трейдоф: **якість відповідей < frontier models** (GPT-4, Claude).
Компенсація: **privacy абсолютна, cost після налаштування → $0, контроль повний**.

> **Уточнення (gap-аналіз):** «privacy абсолютна» стосується *inference*. Етап *training*
> на цьому залізі (AMD, без CUDA) виноситься в cloud (RunPod) — це ephemeral cloud-burst,
> не постійний logging, але датасет тимчасово залишає машину. Див. ADR-007.

---
## 2. System Overview
### 2.1 Conceptual Model
```
┌─────────────────────────────────────────────────────────────────────┐
│                        JARVIS SYSTEM                                │
│                                                                     │
│  ┌───────────────────────┐         ┌───────────────────────────┐   │
│  │   EDGE (USB Flash)    │◄───────►│   TWIN (Home PC/Server)   │   │
│  │                       │  sync   │                           │   │
│  │  • Offline inference  │         │  • Online inference       │   │
│  │  • Local context log  │         │  • Fine-tune training     │   │
│  │  • LoRA adapter       │         │  • Model registry         │   │
│  │  • Lightweight UI     │         │  • Backup & versioning    │   │
│  │  • Sidecar sync agent │         │  • VPN gateway            │   │
│  │                       │         │  • Web dashboard          │   │
│  │  "soldier in field"   │         │  "headquarters"           │   │
│  └───────────────────────┘         └───────────────────────────┘   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```
### 2.2 Operational Modes
```
┌──────────┬───────────────────────────────────────────────────────────┐
│ Mode     │ Behavior                                                  │
├──────────┼───────────────────────────────────────────────────────────┤
│ OFFLINE  │ Edge inference локально. Лог пишеться в JSONL.            │
│          │ Sync pending. Twin недоступний або відсутній.             │
├──────────┼───────────────────────────────────────────────────────────┤
│ LAN      │ Edge проксує складні запити на Twin (більша модель).      │
│          │ Sync авто при підключенні. Twin = primary inference.      │
├──────────┼───────────────────────────────────────────────────────────┤
│ VPN      │ Те саме що LAN але через WireGuard з будь-якої точки.    │
├──────────┼───────────────────────────────────────────────────────────┤
│ TRAINING │ Twin mode. Unsloth retrain → нова LoRA → версія → sync.  │
└──────────┴───────────────────────────────────────────────────────────┘
```
### 2.3 Component Map
```
EDGE
├── InferenceEngine       (KoboldCPP wrapper)
├── LoRAManager           (load / swap / version)
├── MemoryManager         (context + summarization)
├── RAGEngine             (SQLite-vec local)
├── InputDecorator        (deterministic code layer)
├── SessionLogger         (JSONL append-only)
└── SyncAgent             (sidecar, mode-aware)

TWIN
├── InferenceServer       (KoboldCPP / vLLM GPU)
├── SyncServer            (FastAPI, ingest + serve)
├── TrainingService       (Unsloth QLoRA pipeline)
├── ModelRegistry         (SQLite, versions + eval)
├── BackupService         (rclone → NAS / B2)
├── Scheduler             (APScheduler, cron jobs)
├── VPNGateway            (WireGuard)
└── Dashboard             (React, status + controls)
```
---
## 3. Architecture Patterns
### 3.1 System-Level: Modular Monolith
**Edge:** чистий Monolith — один процес, один бінарник, нульова мережева latency між компонентами.
**Twin:** Modular Monolith — один FastAPI процес, але з чіткими internal boundaries.
Кожен модуль — окремий Python package з явним інтерфейсом.
При необхідності масштабування — модуль виноситься в окремий сервіс без рефакторингу логіки.
```
Причина не Microservices:
  • один розробник
  • distributed debugging — дорого
  • network overhead між сервісами не виправданий на цьому масштабі
  • YAGNI — мікросервіси коли команда або навантаження вимагають
```
---
### 3.2 Communication: Async + SSE
```
Simple queries:   Sync Request-Response
Long generation:  Server-Sent Events (streaming tokens)
Background jobs:  Async + Job Queue + Polling
System events:    Internal Event Bus (Pub/Sub)
```
**SSE для inference** — критично для UX. Користувач бачить токени в реальному часі замість очікування повної відповіді.
```python
@app.get("/stream/{job_id}")
async def stream(job_id: str):
    async def generator():
        async for token in model.stream(job_id):
            yield f"data: {token}\n\n"
        yield "data: [DONE]\n\n"
    return EventSourceResponse(generator())
```
---
### 3.3 Data Flow: Pipeline + DAG
**Pipeline** для лінійних задач (audiobook, document processing):
```
Input → [validate] → [preprocess] → [inference] → [format] → [log] → Output
```
**DAG** для паралельних задач (multi-source analysis):
```
[fetch_supplier_a] ──┐
                     ├──► [merge] ──► [analyze] ──► [report]
[fetch_supplier_b] ──┘
        │
        └──────────────────────────► [check_certifications]
```
---
### 3.4 Reliability
**Circuit Breaker** — Twin недоступний → автоматичний fallback на Edge:
```
CLOSED → (N failures) → OPEN → (timeout) → HALF-OPEN → CLOSED
                                              ↓ fail
                                            OPEN
```
**Bulkhead** — Training і Inference ізольовані в пулах ресурсів.
Training не може вбити Inference через RAM exhaustion.

**Retry з Exponential Backoff** — для sync операцій:
```
attempt 1: immediate
attempt 2: 1s delay
attempt 3: 2s delay
attempt 4: 4s delay → give up, buffer locally
```
---
### 3.5 Deployment: Blue-Green + Shadow
```
Active:  [Blue]  — LoRA v3, eval_score: 0.84
Staging: [Green] — LoRA v4, eval_score: pending

Shadow validation:
  User request ──► [Blue]  → відповідь користувачу
                └─► [Green] → відповідь в лог (user не бачить)

Comparison window: 48 hours, 500+ queries
  Green стабільно краще → promote
  Green гірше → discard, no user impact
```
---
## 4. AI-Specific Patterns
### 4.1 LoRA (Low-Rank Adaptation)
**Що відбувається:**
```
Base model weights:  W₀  (frozen, 4–7B parameters)
LoRA delta:          ΔW = A × B  (trainable, ~7M parameters, 0.1%)
Active model:        W₀ + ΔW
```
LoRA — не нові знання. Це зміщення розподілу відповідей:
"з усього що ти знаєш — відповідай ось так, у цьому стилі, з цим пріоритетом."

**Параметри:**
```python
r           = 16     # rank: баланс якість/розмір
lora_alpha  = 16     # scaling: зазвичай = r
lora_dropout = 0.05  # регуляризація для малих датасетів
learning_rate = 2e-4 # sweet spot для QLoRA
num_epochs  = 3      # менше → underfitting, більше → overfitting
```
**Модульні адаптери:**
```
base.gguf (frozen, 4.3 GB)
├── jarvis_persona.gguf      (80 MB) — стиль, tone, поведінка
├── erp_domain.gguf          (120 MB) — ERP термінологія, процеси
├── supply_chain.gguf        (95 MB) — supply chain аналіз
└── drone_ops.gguf           (88 MB) — FPV, RF, UAV домен
```
Swap LoRA між сесіями = **модульна особистість**.
---
### 4.2 RAG (Retrieval-Augmented Generation)
```
User query
    ↓
[Embed query] → vector similarity search
    ↓
[Retrieve] top-K relevant chunks
    ↓
[Inject] у context: "Використовуй ці факти: {chunks}"
    ↓
Base model генерує з актуальними даними
```
**LoRA vs RAG — чіткий поділ відповідальностей:**
```
LoRA = "як відповідати" (стиль, поведінка, tone) — статично
RAG  = "що говорити"   (факти, документи, ціни) — динамічно
Hybrid: LoRA для глибини + RAG для актуальності = найсильніша позиція
```
**Edge RAG — SQLite-vec (офлайн):**
```python
# Легка векторна БД, нульові залежності
conn = sqlite3.connect("./rag.db")
conn.enable_load_extension(True)
conn.load_extension("./vec0")
# Індексація документів
conn.execute("""
    CREATE VIRTUAL TABLE docs USING vec0(
        embedding float[384]
    )
""")
# Retrieval
results = conn.execute("""
    SELECT content, distance
    FROM docs
    WHERE embedding MATCH ?
    ORDER BY distance LIMIT 3
""", [query_embedding]).fetchall()
```
---
### 4.3 Decorator Pattern (AI шар)
```
User input
    ↓
[Input Decorator]   ← детермінований код, нульова latency
    ↓ inject: system context, domain hints, format rules
[Base Model + LoRA] ← один inference
    ↓
[Output Validator]  ← тільки на Twin, якщо score < threshold
    ↓
Response
```
**Input Decorator** — не модель, а код:
```python
class InputDecorator:
    def __init__(self, context_store: ContextStore, rag: RAGEngine):
        self.context = context_store
        self.rag = rag
    def decorate(self, user_input: str, mode: str) -> str:
        system = self.context.get_system_prompt(mode)
        history_summary = self.context.get_summary()
        relevant_docs = self.rag.retrieve(user_input, k=3)
        return f"""{system}
Context from previous sessions:
{history_summary}
Relevant knowledge:
{self._format_docs(relevant_docs)}
User: {user_input}"""
```
**Чому не Output Decorator на Edge:**
```
Проблема когерентності:
  Base model генерує draft A
  Output decorator переписує → user бачить B
  Наступний turn: base має в контексті A, user посилається на B
  → розрив контексту
Фікс: зберігати decorator output як контекст → context window × 2
Висновок: Output Decorator тільки на Twin де є compute
```
---
### 4.4 Chain-of-Thought (CoT)
```
Без CoT:
  Q: "Який постачальник кращий?"
  A: "Supplier A"  ← чорна скринька, не перевіряється
З CoT:
  Q: "Який постачальник кращий? Think step by step."
  A: "Крок 1: порівнюю ціну (A: $12, B: $15) → A дешевше
      Крок 2: надійність (A: 3 скарги/рік, B: 0) → B краще
      Крок 3: терміни (A: 3 дні, B: 7 днів) → A швидше
      Зважена оцінка: A виграє по ціні+швидкість, B по надійності
      Висновок: A для прототипів, B для критичних компонентів"
```
CoT — промпт-техніка, не архітектурний компонент.
Але фундаментально змінює якість на складних reasoning задачах.

**Варіації:**
```
Zero-shot CoT:    "Think step by step" — безкоштовно
Few-shot CoT:     2-3 приклади з reasoning — +30% якість на домені
Tree-of-Thought:  кілька паралельних chains → вибір кращого (Twin only)
```
---
### 4.5 ReAct (Reason + Act)
```
Loop:
  [Thought]:      що мені потрібно для відповіді?
  [Action]:       виклик інструменту
  [Observation]:  результат інструменту
  [Thought]:      що це означає?
  [Action]:       наступний крок або Final Answer
```
**Інструменти для JARVIS:**
```python
TOOLS = {
    "search_suppliers":  search_supplier_db,
    "calculate_roi":     calculate_roi,
    "get_exchange_rate": fetch_nbu_rate,
    "read_document":     read_from_rag,
    "web_search":        brave_search_api,  # Twin only
}
```
---
### 4.6 Cascade Routing
```
Query → [Classifier (fast, deterministic or small model)]
           ├── simple     → Edge inference (Phi-3.5 mini, <1s)
           ├── domain     → Edge inference + LoRA + RAG
           └── complex    → Twin inference + CoT + tools
```
80% запитів — прості. Cascade економить ~70% compute.
```python
def classify_query(query: str) -> str:
    q = query.lower()
    if len(query.split()) < 10 and "?" not in query:
        return "simple"
    if any(kw in q for kw in DOMAIN_KEYWORDS):
        return "domain"
    return "complex"
```
---
### 4.7 Multi-Agent (Twin only)
```
[Orchestrator]
    │ assigns tasks
    ├── [ResearcherAgent]  — збирає факти, не генерує висновки
    ├── [WriterAgent]      — пише, не досліджує
    ├── [CriticAgent]      — знаходить помилки, не виправляє
    └── [FormatterAgent]   — форматує, не додає змісту

Агенти комунікують через Mediator (Blackboard state)
Кожен має ізольований system prompt + tool subset
```
**Коли активувати:**
- Критичні рішення (постачальник, архітектура)
- Документи які підуть клієнту
- Задачі де один прогін дає помилки

**Коли НЕ активувати (Edge):** завжди. Немає compute для multi-agent.
---
### 4.8 Memory Architecture
```
┌─────────────────────────────────────────────────────┐
│  Tier 1: In-Context (working memory)                │
│  • поточна сесія, автоматично                       │
│  • 4K–8K токенів                                    │
│  • зникає після сесії                               │
├─────────────────────────────────────────────────────┤
│  Tier 2: External (long-term)                       │
│  • SQLite: структурований стан                      │
│  • SQLite-vec: семантичний пошук (RAG)              │
│  • JSONL logs: сирі сесії для training              │
│  • персистентно, searchable                         │
├─────────────────────────────────────────────────────┤
│  Tier 3: Parametric (в вагах)                       │
│  • LoRA адаптери                                    │
│  • стиль, поведінка, domain knowledge               │
│  • постійно, нульова latency                        │
│  • не оновлюється в runtime                         │
└─────────────────────────────────────────────────────┘
```
**Summarization Memory** — при переповненні контексту:
```python
def manage_context(messages: list, model, max_tokens: int = 4096):
    if count_tokens(messages) > max_tokens * 0.8:
        old = messages[:-10]  # все крім останніх 10
        summary = model.generate(
            f"Стисни розмову в 3 речення, зберігши ключові факти:\n{old}"
        )
        return [
            {"role": "system", "content": f"[HISTORY]\n{summary}"},
            *messages[-10:]
        ]
    return messages
```
---
## 5. GoF Patterns — Applied
### 5.1 Creational
#### Abstract Factory — Edge vs Twin Infrastructure
```python
class AIInfraFactory(ABC):
    @abstractmethod
    def create_model(self) -> Generatable: ...
    @abstractmethod
    def create_storage(self) -> Storage: ...
    @abstractmethod
    def create_transport(self) -> Transport: ...
    @abstractmethod
    def create_logger(self) -> Logger: ...

class EdgeFactory(AIInfraFactory):
    """Сімейство для офлайн USB — легке, без мережі"""
    def create_model(self):     return KoboldModel(threads=4, ctx=2048)
    def create_storage(self):   return SQLiteStorage("./local.db")
    def create_transport(self): return NoopTransport()
    def create_logger(self):    return FileLogger("./edge.log")

class TwinFactory(AIInfraFactory):
    """Сімейство для домашнього сервера — повне, з GPU"""
    def create_model(self):     return VLLMModel(gpu_layers=-1, ctx=8192)
    def create_storage(self):   return PostgresStorage(DSN)
    def create_transport(self): return HTTPTransport(TWIN_URL)
    def create_logger(self):    return StructuredLogger()

# Composition Root — єдине місце вибору
factory = EdgeFactory() if detect_mode() == "OFFLINE" else TwinFactory()
model     = factory.create_model()
storage   = factory.create_storage()
transport = factory.create_transport()
```
Ключова властивість: **неможливо випадково змішати** Edge компоненти з Twin.
---
#### Builder — InferenceEngine конфігурація
```python
engine = (
    InferenceEngineBuilder()
    .with_model("./models/qwen2.5-7b-q4_k_m.gguf")
    .with_lora("./lora/jarvis_v3.gguf")
    .with_context(4096)
    .with_threads(8)
    .with_gpu_layers(0)   # Edge: CPU only
    .build()
)
```
---
#### Prototype — PromptTemplate клонування
```python
# Базовий шаблон будується один раз (завантаження прикладів з БД)
base = PromptTemplate(system=JARVIS_SYSTEM, examples=db.load_all())
# Варіації для контекстів — миттєво, без повторного DB запиту
erp_template   = base.clone(system_override=ERP_SYSTEM)
drone_template = base.clone(system_override=DRONE_SYSTEM)
```
---
### 5.2 Structural
#### Adapter — уніфікований LLM інтерфейс
```python
class LLMInterface(ABC):
    @abstractmethod
    def generate(self, prompt: str, max_tokens: int) -> str: ...
    @abstractmethod
    def stream(self, prompt: str) -> Iterator[str]: ...

class KoboldAdapter(LLMInterface):
    def generate(self, prompt, max_tokens):
        return self._kobold.generate_text(prompt, max_length=max_tokens)
    def stream(self, prompt):
        return self._kobold.stream_tokens(prompt)

class OllamaAdapter(LLMInterface):
    def generate(self, prompt, max_tokens):
        r = self._ollama.chat(
            messages=[{"role": "user", "content": prompt}],
            options={"num_predict": max_tokens}
        )
        return r["message"]["content"]
    def stream(self, prompt):
        for chunk in self._ollama.chat(stream=True, ...):
            yield chunk["message"]["content"]
```
Весь downstream код працює з `LLMInterface`. Бекенд замінюється без рефакторингу.
> **Gap-аналіз:** саме цей Adapter дозволяє лишити Ollama (доведено на Vulkan) як Twin-інференс,
> а KoboldCPP взяти лише на Edge (USB-портативність).
---
#### Decorator — поведінковий стек
```
BaseLLM
    └── LoggingDecorator       (append to JSONL)
            └── CachingDecorator   (SQLite cache, TTL=1h)
                    └── RetryDecorator     (3 attempts, exponential backoff)
                            └── StyleDecorator     (inject JARVIS persona)
```
```python
llm = StyleDecorator(
          RetryDecorator(
              CachingDecorator(
                  LoggingDecorator(BaseLLM()),
                  cache=SQLiteCache()
              )
          )
      )
# Єдиний інтерфейс — декоратори прозорі
result = llm.generate("Проаналізуй постачальника")
```
---
#### Facade — JARVIS single entry point
```python
class JARVIS:
    """Один клас замість знання про всі підсистеми"""
    def __init__(self, config_path: str):
        cfg = Config.from_yaml(config_path)
        factory = resolve_factory(cfg)
        self._model   = build_engine(factory, cfg)
        self._memory  = MemoryManager(factory.create_storage(), cfg)
        self._rag     = RAGEngine(cfg.vector_db_path)
        self._sync    = SyncService(cfg)
    def chat(self, message: str) -> str:
        context = self._memory.get_context()
        docs    = self._rag.retrieve(message, k=3)
        prompt  = build_prompt(message, context, docs)
        response = self._model.generate(prompt)
        self._memory.add(message, response)
        return response
    def sync(self):
        self._sync.push(self._memory.get_delta())
        if lora := self._sync.pull_latest_lora():
            self._model.apply_lora(lora)
# Caller — один рядок
jarvis = JARVIS("./config.yaml")
print(jarvis.chat("Проаналізуй постачальника X"))
```
---
#### Proxy — Virtual + Remote + Protection
```python
class ModelProxy(LLMInterface):
    """
    Virtual:    lazy load — модель не в RAM до першого запиту
    Remote:     Twin inference через мережу якщо LAN/VPN
    Protection: rate limiting, auth check
    """
    def __init__(self, config: Config):
        self._model = None          # Virtual: ще не завантажено
        self._config = config
        self._requests = []
    def _ensure_loaded(self):
        if self._model is None:
            self._model = load_model(self._config.model_path)
    def _check_rate_limit(self):
        now = time()
        self._requests = [t for t in self._requests if now - t < 60]
        if len(self._requests) >= 60:
            raise RateLimitError("60 req/min exceeded")
        self._requests.append(now)
    def generate(self, prompt: str, max_tokens: int) -> str:
        self._check_rate_limit()
        self._ensure_loaded()
        return self._model.generate(prompt, max_tokens)
```
---
### 5.3 Behavioral
#### Chain of Responsibility — request pipeline
```
Cache → Safety → RateLimit → ModeRouter → Inference
```
```python
cache_h.set_next(safety_h).set_next(ratelimit_h) \
       .set_next(router_h).set_next(inference_h)
result = cache_h.handle(request)
```
Кожен handler незалежний. Додаєш новий — вставляєш в ланцюг без зміни інших.
---
#### Command — операції з undo
```python
class CommandHistory:
    def execute(self, cmd: Command):
        cmd.execute()
        self._history.append(cmd)
    def undo_last(self):
        if self._history:
            self._history.pop().undo()
# Сценарій: нова LoRA виявилась гіршою
history.execute(ApplyLoRACommand(engine, "./lora/v4.gguf"))
# ... тестування ... погіршення eval score ...
history.undo_last()   # відкат до v3 — миттєво
```
---
#### Observer — event-driven coordination
```python
sync_service = SyncService()
# Підписники не знають один про одного
sync_service.on("logs_received",
    lambda e: backup.snapshot(e.data))
sync_service.on("retrain_threshold_reached",
    lambda e: trainer.queue(e.data["examples"]))
sync_service.on("lora_updated",
    lambda e: notifier.push(f"New LoRA v{e.data['version']} ready"))
# При отриманні логів — всі реакції відбуваються автоматично
sync_service.receive_logs(incoming_logs)
```
---
#### State — mode-aware behavior
```python
class SyncManager:
    def __init__(self):
        self._state: SyncState = OfflineState()
    def transition(self, new_state: SyncState):
        self._state = new_state
        self._state.on_enter(self)
    def push(self, data):   self._state.push(self, data)
    def pull(self):          return self._state.pull(self)
# Offline → буферизує. LAN → флашить буфер + синхронізує.
# Поведінка змінюється — код caller не змінюється.
```
---
#### Strategy — pluggable algorithms
```python
class RAGEngine:
    def __init__(self, strategy: RetrievalStrategy):
        self.strategy = strategy
    def set_strategy(self, s: RetrievalStrategy):
        self.strategy = s   # swap в runtime
# Edge: швидкий keyword (немає GPU для embeddings)
rag = RAGEngine(KeywordBM25Strategy())
# Twin: семантичний hybrid
rag.set_strategy(HybridStrategy(
    vector=VectorSimilarityStrategy(),
    keyword=KeywordBM25Strategy(),
    alpha=0.7
))
```
---
#### Mediator — multi-agent coordination
```python
class AgentOrchestrator:
    """Агенти не знають один про одного — тільки через Orchestrator"""
    def run(self, task: str) -> str:
        research = self.agents["researcher"].run(task)
        draft    = self.agents["writer"].run(task, context=research)
        critique = self.agents["critic"].review(draft)
        if critique["approved"]:
            return self.agents["formatter"].format(draft)
        else:
            revised = self.agents["writer"].revise(draft, critique)
            return self.agents["formatter"].format(revised)
```
---
#### Template Method — training pipeline skeleton
```python
class TrainingPipeline(ABC):
    """Порядок кроків незмінний. Реалізація — в підкласах."""
    def run(self):  # не перевизначається
        data  = self.load_data()
        data  = self.preprocess(data)
        self.validate(data)          # hook з default реалізацією
        model = self.train(data)
        score = self.evaluate(model)
        if score >= self.threshold:
            self.deploy(model)
        return {"score": score, "deployed": score >= self.threshold}
    # Hooks
    def validate(self, data):
        assert len(data) >= 100, f"Dataset too small: {len(data)}"
    threshold = 0.75
    # Abstract steps
    @abstractmethod
    def load_data(self) -> list: ...
    @abstractmethod
    def preprocess(self, data: list) -> list: ...
    @abstractmethod
    def train(self, data: list): ...
    @abstractmethod
    def evaluate(self, model) -> float: ...
```
---
#### Memento — state snapshot / rollback
```python
# Перед кожним оновленням LoRA — зберігаємо стан
caretaker.save()  # → EngineMemento(lora=v3, prompt=..., context=...)
# Застосовуємо нову LoRA v4
history.execute(ApplyLoRACommand(engine, "lora_v4.gguf"))
# Shadow validation 48h → eval score dropped
caretaker.restore()  # → повертаємо v3, нульовий downtime для user
```
---
## 6. SOLID in Practice
### 6.1 Single Responsibility
```
Клас / Модуль            Одна відповідальність
────────────────────────────────────────────────────────────
InferenceEngine          генерація токенів
SessionLogger            запис сесій в JSONL
MemoryManager            управління контекстом
RAGEngine                retrieval з векторної БД
SyncAgent                передача delta між Edge і Twin
ModelRegistry            версіонування моделей і LoRA
TrainingService          запуск і моніторинг Unsloth
BackupService            копіювання і ротація версій
```
**Тест:** якщо змінився формат логу — міняємо тільки `SessionLogger`. Нічого більше.
---
### 6.2 Open/Closed
```python
# Новий sync транспорт — новий клас. SyncManager не чіпаємо.
class BluetoothTransport(SyncTransport):
    def push(self, data: bytes) -> bool: ...
    def pull(self) -> bytes: ...
# Нова retrieval стратегія — новий клас. RAGEngine не чіпаємо.
class GraphRAGStrategy(RetrievalStrategy):
    def retrieve(self, query: str, k: int) -> list[str]: ...
```
---
### 6.3 Liskov Substitution
**Контракт Edge ↔ Twin моделі:**
- `generate(prompt, max_tokens)` завжди повертає `str`, ніколи `None`
- `stream(prompt)` завжди є ітератором рядків
- Exception types задокументовані в base class

Якщо Twin модель недоступна — Circuit Breaker переключає на Edge модель.
Caller не знає яка модель відповідає.
---
### 6.4 Interface Segregation
```python
class Generatable(ABC):
    @abstractmethod
    def generate(self, prompt: str, max_tokens: int) -> str: ...
class Streamable(ABC):
    @abstractmethod
    def stream(self, prompt: str) -> Iterator[str]: ...
class Trainable(ABC):
    @abstractmethod
    def train(self, dataset: list, config: TrainConfig): ...
class Observable(ABC):
    @abstractmethod
    def get_metrics(self) -> dict: ...
# Edge: тільки що реально потрібно
class EdgeModel(Generatable, Streamable, Observable): ...
# Twin: повний набір
class TwinModel(Generatable, Streamable, Trainable, Observable): ...
```
Edge модель не реалізує `Trainable` — і не повинна. Немає `NotImplementedError`.
---
### 6.5 Dependency Inversion
```python
class Container:
    """Composition Root — єдине місце де все збирається"""
    def __init__(self, config: Config):
        mode = detect_mode()
        # Infrastructure (конкретні реалізації)
        storage   = SQLiteStorage(config.db_path)
        transport = LANTransport(config.twin_ip) if mode != "OFFLINE" \
                    else NoopTransport()
        logger    = FileLogger(config.log_path)
        # Domain (залежать від абстракцій, не від конкретних)
        self.sync      = SyncService(storage, transport, logger)
        self.inference = InferenceService(storage, logger,
                             model=build_engine(config))
        self.training  = TrainingService(storage, logger)
# main.py
container = Container(Config.from_yaml("config.yaml"))
```
`SyncService` не знає що це `SQLiteStorage`. Він знає тільки `Storage`.
В тесті — `MockStorage()`. Нульова зміна коду.
---
## 7. Component Design
### 7.1 InferenceEngine
```
Interfaces:   Generatable, Streamable, Observable
Dependencies: model file (GGUF), optional LoRA file
State:        loaded model, active LoRA version, metrics counter
Public API:
  generate(prompt, max_tokens, temperature) → str
  stream(prompt, max_tokens) → Iterator[str]
  apply_lora(path) → void
  get_metrics() → {tokens_generated, avg_latency_ms, errors}
Internal:
  _load_model(path) — завантаження в RAM
  _build_prompt(raw) — додавання chat template
  _validate_output(text) — базова перевірка
```
---
### 7.2 MemoryManager
```
Interfaces:   none (domain service)
Dependencies: Storage, Summarizer (= InferenceEngine subset)
State:        current session messages, summary cache
Public API:
  add(user_msg, assistant_msg) → void
  get_context() → list[Message]
  get_summary() → str
  get_delta() → list[Message]   (нові з останнього sync)
  clear_session() → void
Invariants:
  • context завжди ≤ max_tokens (auto-summarize при overflow)
  • delta монотонно зростає між sync точками
```
---
### 7.3 SyncAgent (Edge sidecar)
```
Mode detection:
  1. ping LAN twin → success → LAN mode
  2. ping VPN twin → success → VPN mode
  3. both failed   → OFFLINE, buffer locally
Push (Edge → Twin):
  • context_log delta (нові сесії)
  • feedback_flags (відмічені погані відповіді)
  • metadata (session count, token stats)
Pull (Twin → Edge):
  • active_lora.gguf (якщо нова версія)
  • system_prompt.txt (якщо оновлений)
  • config.yaml patch (якщо змінений)
Scheduling:
  • при підключенні до мережі (network change event)
  • кожні 30 хвилин якщо мережа є
  • при shutdown Edge (flush buffer)
```
---
### 7.4 ModelRegistry (Twin)
```sql
CREATE TABLE lora_versions (
    id          INTEGER PRIMARY KEY,
    version     TEXT NOT NULL,          -- "v1", "v2", ...
    path        TEXT NOT NULL,
    eval_score  REAL,
    status      TEXT DEFAULT 'candidate', -- candidate|active|archived
    dataset_size INTEGER,
    train_epochs INTEGER,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    notes       TEXT
);
CREATE TABLE system_prompts (
    id          INTEGER PRIMARY KEY,
    version     TEXT NOT NULL,
    content     TEXT NOT NULL,
    active      BOOLEAN DEFAULT FALSE,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);
```
Operations:
```
register_lora(version, path, eval)  → candidate
promote(version)                    → active (previous → archived)
rollback(n=1)                       → restore n-th previous active
get_active()                        → current active lora + prompt
```
---
### 7.5 TrainingService (Twin)
```
Trigger conditions (OR):
  • pending_examples >= 200
  • scheduled cron (03:00 daily)
  • manual trigger via dashboard
Pipeline:
  1. load pending examples from storage
  2. convert to ShareGPT format
  3. filter flagged bad responses
  4. merge with existing dataset
  5. split train/holdout (90/10)
  6. run Unsloth QLoRA (r=16, epochs=3)
  7. eval on holdout
  8. if eval_score >= threshold → register in ModelRegistry
  9. notify via Observer ("lora_updated")
Resource constraints (Bulkhead):
  max_ram:   8 GB (isolated from inference pool)
  max_vram:  all available (training mode = inference paused)
  timeout:   6 hours hard limit
```
> **Gap-аналіз:** на AMD/Windows Unsloth не запускається (CUDA-only). Ця служба
> виконується на cloud-інстансі (RunPod) або окремій NVIDIA-машині. Див. ADR-007.
---
## 8. Data Flow & Protocols
### 8.1 Sync Protocol
```
Edge → Twin (push):
POST /ingest/logs
{
  "edge_id": "usb_01",
  "delta_start_idx": 142,
  "logs": [
    {
      "session_id": "s_20250426_143201",
      "messages": [...],
      "flagged": false,
      "tokens": 847,
      "timestamp": "2025-04-26T14:32:01Z"
    }
  ]
}
Response: {"accepted": 7, "last_idx": 149}
```
```
Twin → Edge (pull):
GET /latest/lora
Response: {
  "version": "v4",
  "eval_score": 0.87,
  "size_mb": 94,
  "download_url": "/download/lora/v4",
  "checksum": "sha256:abc..."
}
GET /latest/config
Response: { "system_prompt_version": "v3", ... }
```
---
### 8.2 Training Data Format (ShareGPT)
```json
{
  "conversations": [
    {
      "from": "system",
      "value": "Ти — JARVIS. Відповідай структуровано, dense, без води. Markdown headers де доречно."
    },
    {
      "from": "human",
      "value": "Зроби порівняльний аналіз двох постачальників FPV компонентів"
    },
    {
      "from": "gpt",
      "value": "## Порівняння постачальників\n\n| Критерій | Supplier A | Supplier B |\n|---|---|---|\n| Ціна | $12/unit | $15/unit |\n| Надійність | 94% | 99% |\n| Термін | 3 дні | 7 днів |\n\n**Висновок:** A для прототипів та масових замовлень. B для критичних компонентів де надійність важливіша за ціну."
    }
  ]
}
```
---
### 8.3 Event Schema
```python
@dataclass
class SystemEvent:
    name: str        # "logs_received" | "retrain_triggered" | "lora_updated" | ...
    source: str      # компонент що emitнув
    data: dict       # payload специфічний для події
    timestamp: datetime
# Каталог подій системи:
EVENTS = {
    "logs_received":           {"count", "edge_id", "total_pending"},
    "retrain_triggered":       {"trigger", "dataset_size"},
    "retrain_completed":       {"version", "eval_score", "duration_min"},
    "lora_updated":            {"version", "eval_score"},
    "lora_deployed_to_edge":   {"version", "edge_id"},
    "sync_failed":             {"edge_id", "error", "retry_at"},
    "backup_completed":        {"files_count", "destination"},
}
```
---
## 9. Fine-Tuning Pipeline
### 9.1 Dataset Strategy
```
Джерела для JARVIS датасету:
  • Кращі Claude conversations (export → ShareGPT convert)
  • ERP документи → Q&A пари
  • Supply chain аналізи → structured format
  • Drone specs → технічні описи
  • Власні рішення з reasoning → CoT приклади
Якість > Кількість:
  50 ідеальних прикладів > 500 середніх
Ідеальний приклад:
  ✓ відповідь саме така, яку хочеш бачити ЗАВЖДИ
  ✓ правильний tone, структура, довжина
  ✓ нуль "слів-паразитів" (Звичайно!, Чудово!, Я розумію...)
  ✓ покриває реальний сценарій використання
  ✓ різноманітний контекст
Цільовий розмір:
  MVP launch:    500 прикладів  (базова адаптація)
  Stable v1:    2000 прикладів  (стабільна поведінка)
  Deep domain:  5000 прикладів  (глибока доменна адаптація)
```
---
### 9.2 Training Code (Unsloth)
```python
from unsloth import FastLanguageModel
from trl import SFTTrainer
from transformers import TrainingArguments
# 1. Base model
model, tokenizer = FastLanguageModel.from_pretrained(
    model_name="unsloth/Qwen2.5-7B-Instruct-bnb-4bit",
    max_seq_length=4096,
    load_in_4bit=True,
)
# 2. LoRA configuration
model = FastLanguageModel.get_peft_model(
    model,
    r=16,
    target_modules=[
        "q_proj", "k_proj", "v_proj", "o_proj",
        "gate_proj", "up_proj", "down_proj"
    ],
    lora_alpha=16,
    lora_dropout=0.05,
    use_gradient_checkpointing="unsloth",
)
# 3. Training
trainer = SFTTrainer(
    model=model,
    tokenizer=tokenizer,
    train_dataset=load_dataset("json", data_files="dataset.jsonl")["train"],
    max_seq_length=4096,
    args=TrainingArguments(
        per_device_train_batch_size=2,
        gradient_accumulation_steps=4,   # effective batch = 8
        num_train_epochs=3,
        learning_rate=2e-4,
        warmup_ratio=0.03,
        lr_scheduler_type="cosine",
        fp16=True,
        output_dir="./output",
    ),
)
trainer.train()
# 4. Export for koboldcpp
model.save_pretrained_gguf(
    "jarvis_lora_v1",
    tokenizer,
    quantization_method="q4_k_m"
)
```
---
### 9.3 Evaluation
```python
EVAL_CASES = [
    {
        "prompt": "Порівняй двох постачальників...",
        "must_contain": ["##", "|", "Висновок"],
        "must_not_contain": ["Звичайно!", "Я радий", "Безумовно"],
        "max_tokens": 600,
    },
    # ... 50 таких кейсів
]
def evaluate_lora(model, cases) -> float:
    scores = []
    for case in cases:
        response = model.generate(case["prompt"], max_tokens=800)
        structure = sum(1 for kw in case["must_contain"]
                        if kw in response) / len(case["must_contain"])
        clean = sum(1 for ph in case["must_not_contain"]
                    if ph not in response) / len(case["must_not_contain"])
        length_ok = 1.0 if len(response.split()) <= case["max_tokens"] else 0.5
        scores.append((structure + clean + length_ok) / 3)
    return sum(scores) / len(scores)
```
**Пороги:**
```
score >= 0.85 → promote to active
score >= 0.75 → candidate (manual review)
score <  0.75 → reject, keep previous
```
> **Gap-аналіз:** цей eval міряє формат/стиль (keywords), НЕ фактичну коректність.
> Потрібен окремий correctness-gate (LLM-as-judge на holdout з еталонними фактами),
> інакше self-improving loop ризикує дрейфом фактів попри «зелений» eval.
---
### 9.4 Iteration Cycle
```
Day 1:    100 прикладів → перший retrain (40 хв, RTX 3060)
          Результат: базова адаптація tone
Day 3:    30 поганих відповідей → виправити → додати до датасету
          Retrain → помітно стабільніше
Week 2:   300 прикладів, v3
          Відповідає "своїм голосом" в 80% випадків
Month 1:  500+ прикладів, v6
          Не потребує корекції в основних сценаріях
Month 2:  Auto-pipeline активний
          Щотижневий retrain на накопичених логах
          Модель самовдосконалюється без ручного втручання
```
---
## 10. Deployment & Operations
### 10.1 File System Layout
```
USB Flash (32 GB):
/PortableAI/
├── models/
│   └── qwen2.5-7b-instruct-q4_k_m.gguf     (4.3 GB, read-only)
├── lora/
│   ├── active/
│   │   └── jarvis.gguf                       (symlink → versioned)
│   └── versioned/
│       ├── jarvis_v1.gguf
│       ├── jarvis_v2.gguf
│       └── jarvis_v3.gguf
├── engines/
│   ├── win/    koboldcpp.exe
│   ├── linux/  koboldcpp
│   └── mac/    koboldcpp-mac
├── data/
│   ├── context_log.jsonl                     (append-only)
│   ├── feedback_flags.jsonl
│   ├── rag.db                                (SQLite-vec)
│   └── memory.db                             (SQLite)
├── personas/
│   ├── jarvis_system_v3.txt
│   └── active_system.txt                     (symlink)
├── config.yaml
├── edge_sync.py
├── run_win.bat
├── run_linux.sh
└── run_mac.sh

Twin Home Server:
/ai_twin/
├── inference/                                (koboldcpp GPU)
├── training/                                 (Unsloth workspace)
│   └── datasets/
│       ├── base_dataset.jsonl
│       └── incremental/
│           └── YYYY-MM-DD.jsonl
├── registry/                                 (ModelRegistry SQLite)
├── lora_versions/
│   ├── v1.gguf ... v4.gguf
│   └── active → v4.gguf                      (symlink)
├── backup/                                   (rclone staging)
├── server/                                   (FastAPI app)
└── dashboard/                                (React build)
```
---
### 10.2 Run Scripts
**run_win.bat:**
```bat
@echo off
cd /d %~dp0
engines\win\koboldcpp.exe ^
  --model models\qwen2.5-7b-instruct-q4_k_m.gguf ^
  --lora lora\active\jarvis.gguf ^
  --contextsize 4096 ^
  --threads 8 ^
  --port 5001 ^
  --launch
start python edge_sync.py
```
**run_linux.sh:**
```bash
#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
./engines/linux/koboldcpp \
  --model ./models/qwen2.5-7b-instruct-q4_k_m.gguf \
  --lora ./lora/active/jarvis.gguf \
  --contextsize 4096 \
  --threads $(nproc) \
  --port 5001 &
python3 edge_sync.py &
wait
```
---
### 10.3 Twin Server Stack
```
Caddy (reverse proxy, SSL)
    └── FastAPI :8765 (SyncServer + API)
         ├── /ingest/logs    POST
         ├── /latest/lora    GET
         ├── /download/lora  GET
         ├── /status         GET
         └── /trigger/retrain POST (manual)
APScheduler jobs:
    • 03:00 daily:   check retrain threshold
    • 04:00 daily:   rclone backup → NAS / B2
    • */30 min:      eval pending candidates
WireGuard VPN:
    • server: Twin (home PC)
    • clients: laptop, phone
    • Edge auto-detects VPN IP
```
---
### 10.4 Backup Strategy
```
Rclone sync → Backblaze B2 (або локальний NAS)
  • datasets/:      кожні 24h, retention 30 днів
  • lora_versions/: при кожному promote, retention 10 версій
  • registry.db:    кожні 6h
  • context_logs/:  при кожному sync з Edge
Rollback procedure:
  1. rollback(n=1) в ModelRegistry → повертає symlink
  2. notify Edge при наступному pull → Edge отримує попередню LoRA
  3. Zero downtime — інференс не переривається
```
---
## 11. Decision Log (ADR)
### ADR-001: KoboldCPP як Edge runtime
**Context:** потрібен крос-платформений офлайн inference
**Decision:** KoboldCPP — один бінарник, GGUF формат, вбудований Web UI
**Alternatives:** Ollama (daemon, складніше для USB), llama.cpp (без UI)
**Consequences:** +нульова інсталяція, +SSE streaming; -обмежений GPU offload на деяких платформах
---
### ADR-002: LoRA замість Full Fine-Tuning
**Context:** адаптація моделі під персональний профіль
**Decision:** QLoRA (r=16) через Unsloth
**Alternatives:** Full FT (потребує 80+ GB VRAM), Prefix Tuning (нижча якість)
**Consequences:** +RTX 3060 справляється, +адаптер 80-200 MB, +модульність; -не змінює глибинні знання
---
### ADR-003: SQLite-vec для Edge RAG
**Context:** семантичний пошук офлайн без залежностей
**Decision:** SQLite-vec — розширення SQLite, нульовий overhead
**Alternatives:** Chroma (потребує Python env), FAISS (складніша інтеграція)
**Consequences:** +нульові залежності, +один файл БД; -менша продуктивність на великих корпусах
---
### ADR-004: Modular Monolith для Twin
**Context:** вибір між Microservices і Monolith для домашнього сервера
**Decision:** Modular Monolith (один FastAPI процес, чіткі internal boundaries)
**Alternatives:** Microservices (overkill для одного розробника)
**Consequences:** +простий deployment, +нульовий network overhead; -вертикальне масштабування
---
### ADR-005: Event Bus для внутрішньої координації
**Context:** компоненти Twin мають реагувати на події без tight coupling
**Decision:** Internal Event Bus (dict of callbacks, asyncio.create_task)
**Alternatives:** Redis Pub/Sub (external dependency), direct method calls (tight coupling)
**Consequences:** +додавання підписника без зміни publisher; -складніше trace event flow
---
### ADR-006: Blue-Green для LoRA deployment
**Context:** оновлення LoRA без ризику для активних сесій
**Decision:** Blue-Green через symlinks + Shadow validation 48h
**Alternatives:** Rolling update (немає сенсу для single instance), Feature flags
**Consequences:** +instant rollback, +zero downtime; +shadow validation знижує ризик деградації
---
### ADR-007: Training — cloud-burst (RunPod), не локально
**Context:** Unsloth/QLoRA потребує CUDA; цільова машина — AMD RX 5700 XT (ROCm не підтримується Unsloth)
**Decision:** training виконується на ephemeral RunPod-інстансі; результат (LoRA .gguf) тягнеться назад і реєструється у ModelRegistry
**Alternatives:** окрема NVIDIA-машина (капітальні витрати), AMD ROCm + кастомний стек (нестабільно)
**Consequences:** +inference лишається суверенним і локальним; -датасет тимчасово залишає машину під час training (звузити тезу «privacy абсолютна» до inference); -потрібен RunPod-акаунт і трансфер даних
---
## 12. Roadmap
### Phase 1 — Edge MVP (Week 1-2)
```
[ ] KoboldCPP запускається з USB на Win/Linux
[ ] Qwen 2.5 7B Q4 завантажується і генерує
[ ] JARVIS system prompt активний
[ ] SSE streaming в браузері
[ ] SessionLogger пише JSONL
[ ] run_win.bat / run_linux.sh / run_mac.sh
```
### Phase 2 — Twin Foundation (Week 3-4)
```
[ ] FastAPI SyncServer підіймається
[ ] /ingest/logs приймає delta від Edge
[ ] /latest/lora відповідає поточну версію
[ ] edge_sync.py push/pull базовий
[ ] WireGuard VPN — доступ з будь-де
[ ] Caddy reverse proxy + SSL
```
### Phase 3 — Memory & RAG (Month 2)
```
[ ] SQLite-vec на Edge для локальної бази знань
[ ] MemoryManager з auto-summarization
[ ] InputDecorator інжектує context + docs
[ ] Context delta sync Edge → Twin
```
### Phase 4 — Training Pipeline (Month 2-3)
```
[ ] Перший датасет 500 прикладів (з Claude exports)
[ ] Unsloth QLoRA на RunPod → перша LoRA
[ ] ModelRegistry з eval scoring
[ ] Blue-Green deployment через symlinks
[ ] Auto-retrain scheduler (threshold 200 прикладів)
```
### Phase 5 — Quality & Observability (Month 3)
```
[ ] Eval pipeline (50 holdout cases)
[ ] Shadow validation перед promote
[ ] Dashboard: версії, eval scores, sync status
[ ] LLM-as-Judge на Twin для якості відповідей
[ ] Rollback через CommandHistory
```
### Phase 6 — Advanced (Month 4+)
```
[ ] Multi-agent для критичних задач (Orchestrator + Critic)
[ ] Cascade routing (classify → edge/twin)
[ ] MoE через domain-specific LoRA swap
[ ] Self-improving loop (повністю автоматичний)
[ ] Phi-3.5 mini як router/classifier на Edge
```
---
## Appendix A — Model Selection Matrix
| Model | Q4 Size | RAM | Quality | CPU Speed | Recommended |
|---|---|---|---|---|---|
| Phi-3.5 mini | 2.2 GB | 4 GB | ★★★☆ | ★★★★★ | RAM < 8 GB |
| Qwen 2.5 7B | 4.3 GB | 8 GB | ★★★★★ | ★★★☆ | **Default** |
| Mistral 7B | 4.1 GB | 8 GB | ★★★★☆ | ★★★☆ | Alternative |
| Llama 3.1 8B | 4.7 GB | 10 GB | ★★★★☆ | ★★★☆ | High RAM |
---
## Appendix B — GoF Quick Reference
| Pattern | Category | Problem Solved | Applied In |
|---|---|---|---|
| Abstract Factory | Creational | Сімейства сумісних об'єктів | Edge vs Twin infra |
| Builder | Creational | Складна конфігурація | InferenceEngine |
| Prototype | Creational | Клонування дорогих об'єктів | PromptTemplate |
| Singleton | Creational | Один екземпляр | Config, Logger |
| Adapter | Structural | Несумісні інтерфейси | Kobold vs Ollama |
| Decorator | Structural | Стек поведінок | LLM pipeline |
| Facade | Structural | Спрощений API | JARVIS class |
| Proxy | Structural | Lazy / Remote / Protection | ModelProxy |
| Composite | Structural | Дерево задач | TaskGraph |
| Chain of Resp. | Behavioral | Ланцюг обробників | Request pipeline |
| Command | Behavioral | Undo / queue | LoRA swap |
| Observer | Behavioral | Event-driven координація | SyncService |
| State | Behavioral | Mode-aware поведінка | SyncManager |
| Strategy | Behavioral | Взаємозамінні алгоритми | RAG retrieval |
| Template Method | Behavioral | Скелет алгоритму | TrainingPipeline |
| Mediator | Behavioral | Агенти не знають один про одного | Orchestrator |
| Memento | Behavioral | Snapshot / rollback | Engine state |
| Iterator | Behavioral | Стрім токенів | TokenStream |
---
## Appendix C — SOLID Quick Reference
| Principle | Rule | Violation Signal |
|---|---|---|
| SRP | Одна причина змінюватись | Клас залежить від 2+ акторів |
| OCP | Розширення без модифікації | `if isinstance(...)` або `if type == ...` |
| LSP | Підклас замінює base | `NotImplementedError`, звужений контракт |
| ISP | Маленькі фокусні інтерфейси | Реалізація порожніх методів |
| DIP | Залежи від абстракцій | `new ConcreteClass()` всередині класу |
---
*JARVIS PortableAI Design Document — Living document, оновлюється з системою*
