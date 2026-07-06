# JARVIS — Synergy Roadmap (паспортна шина + 10 синергій)

> **Версія:** 1.0 (2026-07-06)
> **Статус:** Living document — **крос-стовповий трек** (фундамент під 🅰🅱🅲).
> **Мета:** замкнути п'ять уже наявних практик — **MCP-модулі · EventBus (Observer) · Decorator ·
> ContextPassport (P9) · Tags everywhere (P10)** — в одну «нервову систему» (паспортна шина,
> трек SY-B) і зняти з неї десять продуктових синергій (SY-1…SY-10).

**Пов'язані документи**

| Документ | Роль |
|----------|------|
| [`AGENTS.md`](../AGENTS.md) | Конституція — P4/P5/P9/P10, C1, S1–S5; guardrails §6 |
| [`docs/CONTEXT_MODULE.md`](CONTEXT_MODULE.md) | Субстрат: паспортний конвеєр, `ContextQuery`, §8 (Observer позначено «далі») |
| [`docs/PRODUCT_ROADMAP.md`](PRODUCT_ROADMAP.md) | Парасолька — фазовий статус треку |
| [`docs/FEATURE_AUDIT.md`](FEATURE_AUDIT.md) | P2-3 — борг тег-адресації (закривається SY-B3) |
| [`docs/API_PLATFORM_ROADMAP.md`](API_PLATFORM_ROADMAP.md) · [`CODING_AGENT_ROADMAP.md`](CODING_AGENT_ROADMAP.md) · [`CLIENTS_ROADMAP.md`](CLIENTS_ROADMAP.md) · [`AGENT_MODE_ROADMAP.md`](AGENT_MODE_ROADMAP.md) | Треки-споживачі синергій (AP/CA/CL/AM) |
| [`docs/DESIGN.md`](DESIGN.md) | Патерн-мова (§1.2.1 паспорт/теги, §3.3 pipeline, §4.3 decorator) |

> **Правило статусів (D1):** task-чекбокси `SY-*` живуть **тут**. Парасолька тримає лише фазовий
> статус. Зміна коду за задачею → `[x]` тут у тому ж PR.

---

## 1. Формула синергії (шасі)

> **Паспорт — це подія. Тег — це адреса. Шина — це транспорт. Декоратор — це обробка. MCP — це роз'єм.**

Кожен із п'яти елементів займає рівно одну роль у життєвому циклі сигналу:

| Елемент | Роль | Стан (2026-07-06) |
|---------|------|-------------------|
| **ContextPassport** (P9/C1) | універсальний конверт: `kind + summary + tags + embedding` | ✅ `jarvis_core/passport/`, стор `context_events` |
| **Tags** (P10) | мова **індексації** (GIN-containment) і **адресації** (хендли) | ✅ індексація · ❌ адресація (резолвера нема) |
| **EventBus** (Observer) | транспорт: підписка = tag-containment | ✅ in-proc (SY-B1) · ❌ крос-сервіс (SY-B2) |
| **Decorator** | закон розширення на обох кінцях шини | ✅ прецеденти: `jarvis_core/llm/decorators.py`, InputDecorator, kaizen DR5 |
| **MCP-модулі** | двобічні органи: продюсери **і** підписники | ✅ конектори `jarvis`/`erp_sa` · ❌ реєстр модулів як паспорти |

```
MCP-модуль (орган: erp_sa, kaizen, APK, host-script, agent)
   │  продукує / споживає
   ▼
Passport (єдиний конверт: kind + summary + tags + embedding)     ← P9/C1, є
   │  emit ПІСЛЯ store (context_events = durable log шини)
   ▼
PassportBus (Observer: підписка = tag-containment)               ← SY-B1/B2
   │  маршрутизація за тегами — та сама семантика, що GIN-ретрив ← P10
   ▼
Підписник = ланцюг декораторів (OrgScope(Redact(Dedup(handler))))← закон DR5
```

### 1.1 П'ять уніфікацій (чому це синергія, а не купа патернів)

1. **Подія = паспорт.** Шині не потрібна власна схема повідомлень — конверт уже канонізований
   конституцією (C1: «голий» артефакт = баг). Emit відбувається *після* store → шина отримує
   durable log безкоштовно; replay пропущеного = звичайний `ContextQuery` (event sourcing lite
   без нової таблиці).
2. **Підписка = tag-запит.** Жодних topics/channels: `subscribe(tags=["kind:invoice",
   "sensitivity:finance"])` — той самий containment-предикат, що в GIN-ретриві. «Що сталося» і
   «що я знаю» — один механізм.
3. **Адресація тегом закриває P10-борг.** Модуль при реєстрації інжестить паспорт `kind:module`
   з тегами `module:<name>` + `capability:*` → реєстр модулів стає звичайним контекстом; агент
   знаходить виконавця тим самим ретривом, яким згадує людей. Одна адресна книга на
   `person:mom`, `module:erp-sa`, `routine:kaizen`.
4. **Декоратор — єдиний закон розширення.** Produce-бік: ingest-стадії (Redact → Passport →
   Embed → Ledger → Store) як шари над `ContextStore`. Consume-бік: підписник = handler у
   cross-cutting шарах (org-scope, dedup, rate-limit, metrics). Той самий закон, що в
   `build_llm_stack` і kaizen DR5 («профіль = декоратор, не форк») — новий концерн = новий шар (P5).
5. **MCP-модуль — двобічний орган.** Модулі емітять паспорти (erp_sa → `kind:erp_import`;
   kaizen уже пише фазові паспорти) і підписуються на теги. `mcp__jarvis__context_ingest/search`
   означає: зовнішній Claude Code *вже* продюсер/консюмер шини.

### 1.2 Попарні виграші

| Пара | Синергія |
|------|----------|
| Passport × Bus | шина отримує схему і durable log задарма; паспорти — реактивних споживачів замість полінгу |
| Tags × Bus | підписка і ретрив говорять однією мовою (containment) |
| Tags × MCP | discovery модулів = tag-запит; `module:*` закриває P10-борг механічно |
| Decorator × Bus | redact/ledger/org-scope/metrics — шарами, не розмазкою по стадіях |
| Decorator × MCP | DR5 (профіль декорує engine) поширюється з kaizen на всі рантайм-модулі |
| Passport × MCP | «скіл без рядка в індексі = баг» стає механікою: модуль без паспорта не резолвиться |

### 1.3 Емерджентні можливості (payoff)

1. **Самоспостережність:** паспорти kaizen/autopilot у `context_events` → «що kaizen зробив
   учора» = ретрив; дайджест — підписка на `routine:kaizen AND kind:loop`.
2. **Жива проактивність у межах S4:** proposal-engine реагує на події, а не добовий cron;
   емітить лише пропозиції.
3. **Offline-first без компромісів (P1):** `PassportBus` — порт із двома адаптерами
   (`InProcBus` для Edge, `RedisBus` для compose; Redis уже в стеку — нуль нових залежностей).
4. **Розширення = підписник:** нова фіча — новий модуль з тегами, а не правка ядра (P5 на
   рівні системи).

---

## 2. Baseline (стан на 2026-07-06)

### 2.1 Реалізовано (фундамент SY-B0 ✅)

| Компонент | Стан | Де |
|-----------|------|----|
| Паспортний конвеєр ingest (fast/raw path, redact, embed) | ✅ | `jarvis_core/passport/`, `gateway/app/client_api/context.py`, `memory/app/context/` |
| Теги: `normalize_tags`, GIN-containment ретрив | ✅ | `jarvis_core/passport/tags.py`, `context_events` |
| Ідемпотентність ingest | ✅ unique `(user_id, event_id)` | migration 003 |
| Context-jobs (summarize/daily/retention/proposal) | ✅ ручний тригер + in-app scheduler за прапором | `tools/app/context_jobs.py`, `gateway/app/context_scheduler.py` |
| Agent payoff (retrieval у промпт) | ✅ `ENABLE_CONTEXT_RETRIEVAL` | InputDecorator-точка `_memory_context` |
| LLM-декоратори | ✅ `CacheLLM`, `StyleLLM`, `build_llm_stack` | `jarvis_core/llm/decorators.py` |
| MCP-конектори | ✅ `jarvis` (chat/code/context/confirm), `erp_sa` (Chrome-міст) | `.claude/skills/` |
| Push | ✅ ntfy (UnifiedPush), дефолт off | `tools/app/push.py` |
| S4 confirm-цикл | ✅ `confirm_pending/approve/cancel` (полінг) | MCP jarvis/erp_sa |
| Kaizen-паспорти фаз | ✅ пишуться, але **поза стором** (мертві JSON) | `data/artifacts/self-improve/passports/` |
| Tier-лог Computer Use | ✅ | `data/logs/computer.jsonl` |

### 2.2 Бракує (що будує цей трек)

| Прогалина | Закриває |
|-----------|----------|
| Живий Observer (споживачі на полінгу/cron) | SY-B1/SY-B2 |
| Тег-адресація: резолвера нема (FEATURE_AUDIT P2-3) | SY-B3 |
| Реєстр модулів як паспорти (`kind:module`) | SY-B3 |
| Kaizen-паспорти недоступні ретриву | SY-B3.4 |
| Зовнішня жива підписка (Platform/APK стрічка) | SY-B4 |
| Продуктові синергії над шасі | SY-1…SY-10 |

---

## 3. Трек SY-B — паспортна шина (шасі)

### SY-B1 — In-proc шина (мінімальний транспорт) — 🟢 done (2026-07-06)

**Мета:** порт + адаптер (~150 LOC з тестами), emit з ingest, один підписник. Нічого не ламає:
полінг-шляхи лишаються, вимкнений прапор = поведінка як сьогодні.

```python
# jarvis_core/bus.py (порт)
class PassportBus(Protocol):
    def subscribe(self, pattern: list[str], handler: Handler) -> Subscription: ...
    async def emit(self, passport: Passport) -> None   # fire-and-forget; помилка підписника не валить emit
```

- [x] **SY-B1.1** `jarvis_core/bus.py`: порт `PassportBus` + `InProcBus`; матчинг = containment
      (та сама семантика, що GIN) — юніт-тести на матчинг/фан-аут/ізоляцію помилок
- [x] **SY-B1.2** `emit()` з ingest-шляху **після** store → стор = durable log шини
      (`gateway/app/client_api/context.py`; дублі store не емітяться — ідемпотентність шини)
- [x] **SY-B1.3** перший підписник: push (ntfy) на `priority:high` (`gateway/app/bus.py`;
      ntfy-хелпер — спільний `jarvis_core/push.py`, конфіг — блок `PushCfg`)
- [x] **SY-B1.4** захист від петель: фільтр «не реагуй на власний `source`» + hop-limit
      (`payload["bus_hop"]`, хелпер `next_hop_payload`)
- [x] **SY-B1.5** прапор `ENABLE_PASSPORT_BUS=false` → `.env.example` + `ENV_CHECKLIST.md` (D1)

**DoD:** e2e-тест «ingest → підписник отримав паспорт»; збій підписника не валить ingest;
прапор off → нуль змін поведінки.

### SY-B2 — RedisBus (крос-сервісний транспорт) — 🔴 todo

**Мета:** gateway↔tools↔memory на одній шині; Edge лишається на `InProcBus` (P1).

- [ ] **SY-B2.1** адаптер `RedisBus` (pub/sub; Redis уже в стеку — нуль нових залежностей);
      ключі з org-префіксом `jarvis:{org_id}:bus:*` (multi-tenant дисципліна, статут §5)
- [ ] **SY-B2.2** daily/proposal переведені на підписки; `context_scheduler` лишається
      fallback-guard (дух ADR-008: реактивність — за прапором, cron — страховка)
- [ ] **SY-B2.3** реплей після офлайну споживача: курсор по `context_events` (store-as-log)

**DoD:** подія, заінжещена в gateway, доходить до підписника в tools; вбитий підписник
доганяє пропущене реплеєм зі стору.

### SY-B3 — Тег-резолвер + реєстр модулів — 🔴 todo (закриває FEATURE_AUDIT P2-3)

**Мета:** тег стає хендлом. Одна адресна книга для пам'яті, модулів і рутин.

- [ ] **SY-B3.1** `jarvis_core/passport/addressing.py`: `resolve(tag) -> Handle`
      (`ContextQuery | ModuleRef`); `context_of("person:mom", days=7)`
- [ ] **SY-B3.2** реєстрація модулів: при старті модуль інжестить паспорт `kind:module`
      з тегами `module:<name>`, `capability:*`, `tier:<0..4>`; `mcp_list` = tag-запит
- [ ] **SY-B3.3** `normalize_tags`: нові неймспейси `module:`, `capability:`, `tier:`,
      `priority:` (тегова гігієна — §6)
- [ ] **SY-B3.4** kaizen-паспорти (`data/artifacts/self-improve/passports/`) → ingest у
      `context_events` (дзеркало; файли лишаються артефактами вікна)

**DoD:** `resolve("module:erp-sa")` повертає робочий handle; «хто вміє capability:ocr?» —
звичайний ретрив; FEATURE_AUDIT P2-3 позначено закритим.

### SY-B4 — Зовнішня підписка (SSE) — 🔴 todo

- [ ] **SY-B4.1** `GET /context/stream` (SSE, auth + org-scope, flag `ENABLE_CONTEXT_STREAM`)
- [ ] **SY-B4.2** /platform: жива стрічка подій у штабі (Стовп C)
- [ ] **SY-B4.3** APK: push-міст (ntfy) → пізніше нативна підписка

**DoD:** подія видна в /platform ≤2 с після ingest без рефрешу.

---

## 4. Десять синергій (SY-1…SY-10)

> Формат: формула → суть → задачі → DoD. `Залежність: стор` = працює на наявному
> `context_events` без шини (можна робити **зараз**); `B1/B2/B3` = чекає відповідної фази шасі.
> ICE = Impact × Confidence ÷ Effort (1–5).

### SY-1 — Самозарядний backlog — `runtime-телеметрія × kaizen × стор` — 🟢 done (2026-07-06)

| Стовп | Принципи | Залежність | ICE |
|-------|----------|------------|-----|
| 🅱 + маховик kaizen | C1, P2 | **стор** (шина не потрібна) | **10.0** |

Помилки інструментів, ретраї, виправлення користувача емітяться як паспорти
`kind:friction|error`. Plan-фаза kaizen перед вибором задачі робить tag-запит по них → backlog
поповнюється з реального болю, а не лише з roadmap-ів. Мотивація з даних: паспорт `0076`
зупинив луп із причиною `backlog_dry` — цикл глохне без людського підкидання задач.

- [x] **SY-1.1** продюсер friction: агент-луп/tools емітять `kind:friction` (tool-fail,
      unknown-tool, loop-exhausted) прямим ingest у memory (fast path, без LLM; анти-leak —
      лише тип помилки) — `tools/app/friction.py` + хуки в dispatch/agent, прапор
      `ENABLE_FRICTION_TELEMETRY`. *(user-correction/retry як фідбек-сигнали → SY-4.1)*
- [x] **SY-1.2** kaizen plan (профіль jarvis): query `tags=[kind:friction]` за вікно →
      кандидати задач поруч із roadmap-джерелами (kaizen-loop PLAN + profile roadmap_source)
- [x] **SY-1.3** daily digest: shipped-елемент з `friction_ref` рендериться «from telemetry»
      з ref на friction-паспорт (render_digest BLOCK 4; felt, O1)

**DoD:** у kaizen-вікні ≥1 задача походить з телеметрії; частка stop-reason `backlog_dry` падає.

### SY-2 — Механічний tier ladder — `тег-резолвер × capability-реєстр × Computer Use` — 🔴 todo

| Стовп | Принципи | Залежність | ICE |
|-------|----------|------------|-----|
| 🅱 (AM-трек) | S5 | **SY-B3** | 4.0 |

Виконавці зареєстровані паспортами з `capability:*` + `tier:*`. Запит «заповни форму» →
резолвер повертає кандидатів, відсортованих за tier'ом; агент пробує найдешевшого. S5 перестає
бути настановою в промпті й стає політикою маршрутизації.

- [ ] **SY-2.1** capability-паспорти для наявних виконавців (PS/CLI/FS/browser/UIA/erp_sa-міст)
- [ ] **SY-2.2** політика вибору: `resolve(capability) → sort by tier → try-escalate`;
      рішення пишеться в `computer.jsonl` (є) + emit `kind:tier_decision`
- [ ] **SY-2.3** тест-guard: жодного T4, якщо існує кандидат T0–T2 для capability

**DoD:** вибір яруса відтворюваний тестом; ескалація T0→T4 видима в логах і паспортах.

### SY-3 — Teach mode: скіл із демонстрації — `Chrome-міст × паспорти × skill-creator` — 🔴 todo

| Стовп | Принципи | Залежність | ICE |
|-------|----------|------------|-----|
| 🅱/🅲 | DR5, S4 | **стор** | 3.0 |

Розширення записує ручний прогін веб-форми як трейс `kind:web_action`-паспортів; дистилятор
стискає трейс у новий autofill-адаптер (engine erp_sa канал-агностичний — новий домен =
адаптер, не форк). «Покажи один раз — отримай скіл»; заповнення завжди під S4.

- [ ] **SY-3.1** recorder у `extension/`: клік/філ/навігація → `kind:web_action` (ingest батчем)
- [ ] **SY-3.2** схема трейсу: selector-стратегія, маскування значень `sensitivity:` (redact до store)
- [ ] **SY-3.3** дистилятор: трейс → adapter-скіл (kaizen-style генерація + рев'ю); реєстрація
      в індексі скілів (`.claude/skills/README.md`) — інакше C1-баг
- [ ] **SY-3.4** e2e: демонстрація → адаптер заповнює ту саму форму під S4-апрув

**DoD:** один ручний прогін породжує робочий адаптер без ручного кодування.

### SY-4 — Kaizen для ваг — `feedback-паспорти × Twin/LoRA × eval-gate` — 🔴 todo

| Стовп | Принципи | Залежність | ICE |
|-------|----------|------------|-----|
| Фундамент (PortableAI) | S1, P7; чесність ADR-007 | **стор** | 2.0 |

Лайки/дизлайки/regenerate/виправлення → `kind:feedback` → нічний LoRA-батч на Twin. Інваріант
kaizen «ніколи не комітимо зламане» переноситься на ваги: адаптер активується лише якщо
eval-скор ≥ поточного; ModelRegistry версіонує (P7); meta-OKR отримує ціль O-model.

- [ ] **SY-4.1** продюсери feedback у всіх каналах (TG-реакції, /platform, APK)
- [ ] **SY-4.2** датасет-джоб: `kind:feedback` → навчальна вибірка (redact за sensitivity)
- [ ] **SY-4.3** eval-suite («CI для ваг»): фіксований набір задач + скоринг
- [ ] **SY-4.4** гейт: активація LoRA тільки при score ≥ активного; запис у ModelRegistry
- [ ] **SY-4.5** meta-OKR: O-model у kaizen-профілі

**DoD:** неможливо активувати LoRA з нижчим eval-score (гейт-тест); кожен тренувальний ран —
паспорт `kind:training_run`.

### SY-5 — Confirm-mesh — `S4 × шина × три канали` — 🔴 todo

| Стовп | Принципи | Залежність | ICE |
|-------|----------|------------|-----|
| 🅲 | S4 | MVP: **стор** · повний mesh: **SY-B2** | 5.3 |

Запит підтвердження = паспорт `kind:confirm_request, priority:high`: Telegram-кнопка, APK-push
(ntfy), toast у /platform. Перший апрув виграє, решта карток гаситься. Approve/deny — теж
паспорти → повний аудит-трейл небезпечних дій; «що я дозволив минулого тижня» — ретрив.

- [ ] **SY-5.1** MVP: `confirm_pending` → push-нотифікація (ntfy) з deep-link на канал апруву
- [ ] **SY-5.2** конверти `kind:confirm_request|confirm_decision` (+ ref на дію)
- [ ] **SY-5.3** mesh (після SY-B2): fan-out на канали, first-responder-wins, гасіння карток
- [ ] **SY-5.4** APK computer-confirm з телефона (CL-роадмап) сідає на цю ж механіку

**DoD:** підтвердження доступне з будь-якого активного каналу; кожне рішення — паспорт;
гонка двох апрувів вирішується детерміновано (тест).

### SY-6 — Лічильник як декоратор — `MeterLLM × usage-паспорти × білінг Стовпа A` — 🟢 done (2026-07-06)

| Стовп | Принципи | Залежність | ICE |
|-------|----------|------------|-----|
| 🅰 | P7 | **стор** | **8.0** |

Ще один шар у `build_llm_stack`: `MeterLLM` емітить `kind:usage` (tokens, model, org, latency).
Один потік метрики — три споживачі: `/v1` usage + білінг per-org ключів (AP-трек), self-score
O3 ECO у kaizen, cost-дашборд у /platform. Інакше ці троє приречені на три окремі лічильники.

- [x] **SY-6.1** `MeterLLM` у `jarvis_core/llm/decorators.py` (шар під Cache — кеш-хіт не
      коштує токенів; токени репортить адаптер) + `jarvis_core/llm/usage.py` `UsageMeter`
      (ОДИН агрегат-паспорт на батч); агентський шлях — той самий meter через
      `on_inference_stats`; прапор `ENABLE_USAGE_METERING`, синтетичний UID `-770002`
- [x] **SY-6.2** `/v1/usage` віддає `tokens`-блок зі стору (`saas/token_usage.py` — SSOT;
      requests-лічильник Redis лишається окремим виміром поруч)
- [x] **SY-6.3** kaizen O3 ECO: local-спенд вікна читається tag-запитом `kind:usage`
      (eco-policy «Measured, not estimated» + біндинг у профілі jarvis; фолбек — ledger)
- [x] **SY-6.4** /platform: `GET /platform/api/usage` = той самий агрегатор (цифра
      збігається з `/v1` за побудовою — один стор, DoD)

**DoD:** цифра usage у `/v1` і в ECO-скорі збігається (один стор — розбіжність = баг, D1).

### SY-7 — Edge-органела — `офлайн-черга × ідемпотентний ingest × Twin-канал` — 🔴 todo

| Стовп | Принципи | Залежність | ICE |
|-------|----------|------------|-----|
| Фундамент | P1 | **стор** (ідемпотентність уже є) | 4.0 |

Edge накопичує паспорти в SQLite офлайн; при появі LAN/VPN черга реплеїться в
`/context/ingest` — унікальність `(user_id, event_id)` робить реплей безпечним, дублі
неможливі. Канал синхронізації Twin, який возить LoRA, везе й контекст.

- [ ] **SY-7.1** Edge: локальна черга паспортів (SQLite, append-only)
- [ ] **SY-7.2** replay-клієнт: батч-ingest з backoff; курсор останнього підтвердженого
- [ ] **SY-7.3** інтеграція в Twin-sync (один канал: LoRA + контекст)

**DoD:** офлайн-сесія Edge → 0 дублів після двох реплеїв поспіль (тест на ідемпотентність).

### SY-8 — Репо-граф — це теж контекст — `coding agent × паспорти × теги` — 🔴 todo

| Стовп | Принципи | Залежність | ICE |
|-------|----------|------------|-----|
| 🅱 (CA-трек) | C1, P7 | **стор** | 3.0 |

Файли, символи, тест-рани отримують паспорти (`kind:symbol|file|test_run|code_change`, теги
`module:gateway`, `symbol:PassportBus`) — repo-aware ретрив агента кодування стає тим самим
`ContextQuery`, що й побутова пам'ять. Мерджі емітять `kind:code_change`, на які підписані
kaizen-рев'ю і дайджест. «Чому ми це міняли в травні» — ретрив, а не git-археологія.

- [ ] **SY-8.1** індексатор репо → паспорти символів/файлів (батч, локальний embed)
- [ ] **SY-8.2** агент-луп: merge/test-run емітить `kind:code_change|test_run` з ref на PR
- [ ] **SY-8.3** coding-агент: repo-RAG через `ContextQuery` (замість окремого стору;
      узгодити з CA-роадмапом — один SSOT пам'яті)

**DoD:** запит «чому змінили X» повертає паспорт із ref на PR; kaizen-дайджест містить
code_change-и вікна без читання git-логу.

### SY-9 — Пропозиція → рутина — `proposal-engine × scheduled tasks × S4` — 🔴 todo

| Стовп | Принципи | Залежність | ICE |
|-------|----------|------------|-----|
| 🅲 (продуктова wow-фіча) | S4, ADR-008 | **стор** | **8.0** |

До кожної пропозиції — дія «зробити регулярною»: один апрув → scheduled task, що б'є ендпоінт
джоба/скіла (патерн `scripts/jarvis_context.py --job` — уже благословенний ADR-008 спосіб:
рекурентність із нагляду користувача, не прихований auto-cron). Кожен запуск — run-паспорт.

- [ ] **SY-9.1** проєкція: proposal-паспорт → команда/ендпоінт (мапа «пропозиція → job/skill»)
- [ ] **SY-9.2** матеріалізація: апрув (S4) → рядок Task Scheduler/cron (Windows: schtasks/COM)
- [ ] **SY-9.3** кожен запуск емітить `kind:routine_run` (аудит рутин ретривом)
- [ ] **SY-9.4** /platform + TG: список активних рутин + «вимкнути» одним кліком

**DoD:** пропозиція стає рутиною в ≤2 кліки; run-и і вимкнення видно ретривом.

### SY-10 — Self-healing з аудитом — `health_watch × шина × host-agent playbooks` — 🔴 todo

| Стовп | Принципи | Залежність | ICE |
|-------|----------|------------|-----|
| Ops/фундамент | S4, S5 | **SY-B2** | 3.0 |

Події `health_watch` → паспорти `kind:health, priority:high` → підписники-playbook'и:
безпечний ярус (рестарт контейнера, чистка черги) виконується сам через host-agent `:8400`,
ризиковий — іде в confirm-mesh (SY-5). Кожне «лікування» — паспорт: «чому вночі
перезапускався gateway» видно ретривом.

- [ ] **SY-10.1** `health_watch` емітить `kind:health` (замість/поруч із прямим алертом)
- [ ] **SY-10.2** playbook-реєстр: health-патерн → дія + ярус (safe/risky)
- [ ] **SY-10.3** safe-ярус: авто-виконання через host-agent apply-шлях (той самий, що в autopilot)
- [ ] **SY-10.4** risky-ярус: маршрут у confirm-mesh (SY-5); без апруву не виконується (тест)
- [ ] **SY-10.5** кожне лікування → `kind:healing_run` з ref на health-паспорт

**DoD:** керований збій сервісу лікується без людини; risky-плейбук блокується без апруву.

---

## 5. Хвилі впровадження

Ключовий факт для черговості: **7 із 10 синергій їдуть на сторі, який уже існує** — їм не
потрібна шина. Шина додає реактивність (live-поведінку), резолвер — адресацію.

| Хвиля | Склад | Логіка | Передумова |
|-------|-------|--------|------------|
| **0 — «стор уже вміє»** | SY-1 · SY-6 · SY-9 · SY-5 (MVP) | store-only, найвищий ICE, felt одразу: маховик kaizen + білінг 🅰 + рутини + push-конфірми | нема |
| **1 — «шасі»** | SY-B1 → SY-B2 | транспорт для реактивності; малі PR-и, все за прапорами | нема |
| **2 — «реактивність + адресація»** | SY-5 (mesh) · SY-10 · SY-B3 → SY-2 · SY-7 | live-конфірми, self-healing, закриття P10-боргу, механічний S5 | B2, B3 |
| **3 — «амбітні»** | SY-8 · SY-3 · SY-4 · SY-B4 | найбільший ефект і найбільший скоуп; кожній — окремий spec перед стартом (`docs/*.spec.md`) | хвилі 0–2 |

```
SY-B1 ──► SY-B2 ──► SY-5(mesh) · SY-10 · SY-B4
              └────► SY-B3 ──► SY-2
стор (є) ──► SY-1 · SY-6 · SY-9 · SY-5(MVP) · SY-7 · SY-8 · SY-3 · SY-4
```

---

## 6. Guardrails треку (щоб синергія не з'їла принципи)

- ❌ **Kafka/Celery/FastStream/LangGraph** — guardrail статуту §6 чинний: Redis pub/sub +
  in-proc покривають потребу (P6).
- **Шина ≠ прихований auto-cron (ADR-008):** реактивні підписники за прапорами
  (`ENABLE_*=false` дефолт), мутуючі дії — тільки через S4/confirm-mesh.
- **Петлі на шині:** «не реагуй на власний `source`» + hop-limit — обов'язкові з SY-B1, не «потім».
- **Тегова гігієна:** нові неймспейси лише через `normalize_tags` (SY-B3.3); тег поза
  таксономією = C1-баг. Інакше адресний простір деградує в смітник.
- **Scope C1 незмінний:** шина возить лише паспортовані артефакти; raw-RAG (`/store`) —
  субстрат під нею; LLM-сумаризація кожного повідомлення — порушення P6.
- **D1:** кожен новий прапор → `.env.example` + `ENV_CHECKLIST.md`; кожна закрита задача →
  `[x]` тут у тому ж PR.

---

## 7. KPI треку (Definition of Felt)

| Метрика | Зараз | Ціль | Джерело |
|---------|-------|------|---------|
| Частка kaizen-вікон зі stop `backlog_dry` | трапляється (0076) | ↓ ~0 | meta-OKR паспорти (SY-1) |
| Латентність «подія → пропозиція/пуш» | доба (cron) | хвилини | шина (B1/B2) |
| Мутуючі дії з confirm-паспортом (аудит-повнота) | часткова | 100% | SY-5 |
| Розбіжність usage `/v1` vs O3 ECO | два лічильники | 0 (один стор) | SY-6 |
| P10-адресація | резолвера нема | `resolve()` покриває `module:/routine:/person:` | SY-B3 |
| Дублі контексту після Edge-офлайну | n/a | 0 (тест ідемпотентності) | SY-7 |

---

## 8. Backlog (поза десяткою, кандидати наступної хвилі)

- **Голос як продюсер:** Whisper → готовий raw path (`kind:voice_note`) — дешеве розширення SY-7/CL-3.
- **Privacy-ledger як фіча довіри:** read-model `/context/ledger` → видима сторінка на /platform
  (S1 як продукт, не лише принцип).
- **OKR-дашборд як tag-запит:** `data/okr` + autopilot dashboard рендеряться з ретриву замість
  ручних md-файлів (один SSOT прогресу).

---

*Принципи — [`AGENTS.md`](../AGENTS.md) (P9/P10/C1, S1–S5). Субстрат — [`CONTEXT_MODULE.md`](CONTEXT_MODULE.md).
Хвиля 3 стартує тільки через окремі spec-доки (`docs/*.spec.md`, прецедент `JARVIS_CONNECTOR_P1.spec.md`).*
