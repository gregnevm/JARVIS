# JARVIS — Context Module (архітектура підсистеми)

> **Статус:** DRAFT-архітектура (частково реалізовано — див. §7 «поточне vs ціль»).
> **Версія:** 0.1 (2026-06-16)
> **Місце:** наскрізна підсистема культури **P9 Context Passport + P10 Tag Everything**
> ([`AGENTS.md`](../AGENTS.md) C1, [`DESIGN.md`](DESIGN.md) §1.2.1). Живить Стовп C (CL-3) і агент-RAG.
> **Призначення:** єдина дисципліна для перетворення сирих сигналів (нотатки, дзвінки, SMS,
> сповіщення, worklog) у **теговані, засумаризовані, ембеджені паспорти**, що зберігаються раз,
> дістаються за семантикою+тегами+часом і споживаються агентом, daily-summary та proposal-engine.

---

## 1. Одне речення

**Context module** = конвеєр `produce → ingest → redact → passport(summarize+tag) → embed → store`
+ контракт ретриву `retrieve(semantic + tags + time + sensitivity)` + споживачі
`(agent-RAG · daily · proposals)`. Домен — у `jarvis_core` (мозок, не дублюється), зберігання —
у `memory`, I/O — у `gateway` (S3, P8).

---

## 2. Канонічний конвеєр (стадії = шви)

```
PRODUCERS (Adapter)                          CONSUMERS
  host-script · platform · APK · agent          agent-RAG (InputDecorator)
        │                                        daily-summary (bg_job)
        ▼                                        proposal-engine (bg_job)
  ┌───────────────────── INGEST PIPELINE (Pipeline pattern, §3.3) ─────────────────────┐
  │  validate → REDACT(Strategy) → PASSPORT(summarize+normalize-tags) → EMBED → STORE   │
  └──────────────────────────────────────────────┬─────────────────────────────────────┘
                                                  ▼
                              RETRIEVE  (ContextQuery: semantic ⨯ tags ⨯ time ⨯ sensitivity)
```

**Дві швидкості ingest (важливо для вартості LLM):**
- **Fast path** — продюсер уже дав `summary` (ручна нотатка, дешевий device-side summary) →
  redact → embed → store. **Без виклику LLM.** Це поточний шлях `/context/ingest`.
- **Raw path** — прийшов сирий сигнал без summary → ставимо в чергу `bg_job context_summarize`
  (агент-луп зводить пачку) → store. Не блокуємо ingest на Ollama; батчимо (економія).

---

## 3. Розкладання по сервісах (P8 — хто чим володіє)

| Шар | Де | Відповідальність | Не робить |
|-----|----|------------------|-----------|
| **Domain** | `jarvis_core/passport/` (новий, framework-нейтральний) | `Passport`-модель (SSOT), таксономія+`normalize_tags`, `Redactor` (Strategy), summarize-оркестрація, `ContextQuery`-білдер, addressability | без HTTP/DB/FS — Edge-importable (P1) |
| **Storage** | `memory/app/context/` (sub-package) | `ContextRepo` (add/search/recent/purge), `/context/*` routes, таблиця `context_events`, embed summary | **не** редагує/сумаризує бізнес-логіку — лише персист + embed (dumb store) |
| **Ingress/Egress** | `gateway/app/client_api/context.py` | auth(`RequestContext`), org-scope, fast/raw routing, серверна редакція перед store | без доменної логіки паспорта (виклик `jarvis_core.passport`) |
| **Async** | `jarvis_core/bg_jobs.py` + tools | джоби `context_summarize` · `context_daily` · `context_retention` · (далі) `context_proposal` | — |
| **Consume** | `jarvis_core` agent-pipeline (`Handler`) + InputDecorator | ретрив паспортів у промпт агента (payoff!) | — |

> **Чому домен у `jarvis_core`:** статут §5 — «tenant/доменна логіка у `jarvis_core`, не дублюй
> gateway↔tools↔memory». Тоді APK, host-скрипт, платформа й сам агент користуються **однією**
> логікою паспорта/тегів/редакції.

> **Наймінг:** пакет — `passport/` (не `context/`), бо `jarvis_core/context.py` уже зайнятий
> `RequestContext`. `Passport` = носій культури P9/P10; підсистема в цілому = «context module».

---

## 4. Дані: один паспорт — три представлення (P7 SSOT)

```python
# jarvis_core/passport/models.py  — домен (авторитет)
@dataclass(frozen=True)
class Passport:
    kind: str                 # note|call|sms|notification|usage|worklog|daily|...
    summary: str              # P9: dense, 1–3 речення
    tags: list[str]           # P10: namespaced ns:value, гарантований kind:<kind>
    sensitivity: str          # public|personal|health|finance → redaction/retention
    source: str | None
    ref: str | None           # стабільний хендл для адресації
    event_id: str | None      # ідемпотентність
    event_ts: str | None
    payload: dict             # сире (редаговане); для health/finance — порожнє
    owner_uid: int            # партиція/anti-IDOR
    org_id: str
```
- **Wire (ingest JSON):** `ContextEvent` у gateway — підмножина без owner/org (їх дає `RequestContext`).
- **DB row:** `context_events` (міграція 003) — + `id`, `embedding vector(768)`, `created_at`.
- Три форми тримати синхронними; розбіжність = баг (D1).

---

## 5. Контракт ретриву + адресація (P10)

```python
@dataclass
class ContextQuery:
    user_id: int
    text: str | None = None         # семантика (embed → cosine); None = чисто тегами
    tags: list[str] | None = None   # containment: tags @> query (GIN)
    since: str | None = None        # часове вікно
    max_sensitivity: str = "personal"  # стеля чутливості для цього споживача
    top_k: int = 8
```
**Дві ролі тегів** (як у §1.2.1 DESIGN):
1. **Індексація** — фільтр ретриву (`person:mom AND topic:rent`).
2. **Адресація** — тег як хендл виклику: `resolve("module:scam-shield")`, `context_of("person:mom", days=7)`.
   Резолвер живе в `passport/addressing.py` — мапить tag-запит → `ContextQuery`.

---

## 6. Cross-cutting (наскрізне)

| Концерн | Рішення | Патерн |
|---------|---------|--------|
| **Ідемпотентність** | client `event_id`, unique `(user_id, event_id)` | (готово) |
| **Org-scope / anti-IDOR** | кожен запит фільтрує `user_id`/`org_id`; ingest бере з `RequestContext` | — |
| **Редакція** | дворівнева: device pre-redact + серверний `Redactor` перед store; правила за `sensitivity` | Strategy |
| **Рівні чутливості** | `sensitivity:` керує глибиною редакції, retention і **чи зберігати raw** (health/finance → summary-only) | — |
| **Retention** | per-kind TTL; джоб `context_retention` чистить прострочений raw, summary живе довше | scheduled bg_job |
| **Privacy ledger** | `/context/ledger` = read-model над `context_events` (що зібрано/відправлено) | — |
| **Observability** | лічильники: ingest/source, embed-success-rate, passports/kind → metrics | — |
| **Offline-first** | embed best-effort (store без вектора, доембедити пізніше); черга на продюсері | (готово) |

---

## 7. Поточне vs ціль (чесний refactor-шлях)

**Зараз (реалізовано, CL-3.9):** ingest+ретрив працюють, але доменна логіка «розмазана» —
`normalize_tags`/summary-fallback живуть у `memory/app/main.py`, методи в `db.py`, редакції нема.

**Цільовий рефактор (інкрементально, без big-bang) — ✅ виконано:**
1. ✅ Винесено `jarvis_core/passport/`: `models.py` + `tags.py`(`normalize_tags`) + `redaction.py`
   (`Redactor` Strategy) + `jobs.py` + `retrieval.py` — чисто, з тестами.
2. ✅ `memory`: `/context/*` і моделі → `memory/app/context/` sub-package; спільний `normalize_tags`
   із `jarvis_core` (дубль прибрано, P7). memory-образ отримав `jarvis_core` (pure-import, нуль нових pip-deps).
3. ✅ `gateway` ingest: серверна редакція через `Redactor` + raw-path (`pending:summary`, raw у payload,
   health/finance → drop-raw).
4. ✅ Context-jobs `summarize_pending`/`build_daily`/`run_retention` у `jarvis_core/passport/jobs.py`
   (scheduled sweeps — **окремо** від interactive `JOB_TYPES`, прецедент ADR-008) + memory `/context/{pending,update}`.
5. ✅ **Agent payoff:** context-retrieval у `_memory_context` (InputDecorator-точка) за прапором
   `ENABLE_CONTEXT_RETRIEVAL` — зібраний контекст тече у промпт агента. Культуру замкнено.

6. ✅ **Виконавець context-jobs у tools:** [`tools/app/context_jobs.py`](../tools/app/context_jobs.py)
   (адаптер `MemoryClient`→`ContextStore` + Ollama-summarizer на chat-моделі) + ручний роут
   `POST /context/jobs/{name}` ([`routes/context.py`](../tools/app/routes/context.py)) — тригер
   із нагляду, **без auto-cron** (ADR-008).

7. ✅ **Зовнішній тригер:** gateway-проксі `POST /api/v1/context/jobs/{name}` (auth, org-scoped,
   flag `ENABLE_CONTEXT_API`) → tools. Колектор `scripts/jarvis_context.py --job daily|summarize|retention`.
   Рекурентність — через **власний планувальник** користувача (Task Scheduler/cron б'є ендпоінт),
   що в дусі ADR-008 (запуск із нагляду, не прихований auto-cron).

```bash
# Щоденний контекст о 06:00 — рядок у cron (або Task Scheduler на Windows):
0 6 * * *  python /opt/jarvis/scripts/jarvis_context.py --job daily --password "$JARVIS_PW"
```

8. ✅ **In-app scheduler:** [`gateway/app/context_scheduler.py`](../gateway/app/context_scheduler.py)
   — gateway-loop б'є tools `/context/jobs/*` (summarize кожен тік; daily+retention раз/добу від
   `CONTEXT_DAILY_HOUR`, guard у Redis). Flag `CONTEXT_SCHEDULER_ENABLED` (дефолт off, ADR-008).

> **Лишилось (не блокує):** Platform-UI тригера/перегляду контексту; device-колектори
> (APK ambient: дзвінки/SMS/сповіщення, CL-3).

---

## 8. Патерни (мапа на DESIGN.md)

| Патерн | Застосування в context |
|--------|-------------------------|
| Pipeline (§3.3) | стадії ingest |
| Strategy | `Redactor` правила; retrieval (semantic / tag-only / hybrid) |
| Adapter | продюсери (host/APK/platform/agent) → уніфікований `Passport`/`RawSignal` |
| Repository | `ContextRepo` над `context_events` |
| Chain of Responsibility | context-retrieval `Handler` в агент-пайплайні |
| Decorator | InputDecorator інжектить контекст у промпт |
| Observer | ingest emit → daily/proposal підписники (далі) |

---

## 9. Відкриті рішення

| # | Питання | Варіанти | Рекомендація |
|---|---------|----------|--------------|
| CX-1 | Де summarize raw-сигналів | синхронно в ingest · async `bg_job` батчем | **async batch** (не блокувати ingest на Ollama, дешевше) |
| CX-2 | Чи робити memory повністю «dumb» | так (паспорт будується upstream) · лишити light-логіку в memory | **так** — redact/summarize/tag в `jarvis_core`, memory лише store+embed |
| CX-3 | Окрема таблиця raw vs passport | одна `context_events` (raw у `payload`) · дві таблиці | **одна** поки (YAGNI); рознести при потребі retention-tiering |
| CX-4 | Context-retrieval у кожен agent turn | завжди · лише коли релевантно (класифікатор) | **завжди top-k, дешево** (вже є embed-кеш); поріг score відсікає шум |

---

*Принципи — [`AGENTS.md`](../AGENTS.md) (P9/P10/C1). Схема паспорта/тегів — [`DESIGN.md`](DESIGN.md) §1.2.1.
Продуктовий контекст (ambient APK) — [`proposals/CL-3_mobile_context_companion.md`](proposals/CL-3_mobile_context_companion.md).*
