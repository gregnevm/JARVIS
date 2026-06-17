# JARVIS → Team Ecosystem: архітектурний трек (Стовп D)

> **Версія:** 0.1 (2026-06-17) — пропозиція до обговорення (ще не прийнято в `AGENTS.md`).
> **Статус:** DRAFT-архітектура / трек-roadmap. Потребує рішення власника про підняття до «Стовпа D».
> **Скоуп:** перетворення JARVIS із персонального асистента 1-користувача на **командну SaaS-екосистему**:
> менеджери + їхні AI-асистенти (делегати), спільні Telegram-групи, граф зв'язків між людьми,
> проактивна автоматизація, оркестрація бізнес-процесів по ієрархії команди.
> **База:** [`AGENTS.md`](../AGENTS.md) (принципи), [`SAAS_DEEP_DIVE.md`](SAAS_DEEP_DIVE.md) (tenant/identity enabler),
> [`CONTEXT_MODULE.md`](CONTEXT_MODULE.md) (паспорти P9/P10), [`PRODUCT_ROADMAP.md`](PRODUCT_ROADMAP.md) (3 стовпи).

---

## 0. Одне речення

**Стовп D** додає над зрілим фундаментом четвертий вимір споживання — **команду**: кожен учасник
організації має проактивного AI-**делегата**, делегати й люди взаємодіють у спільних Telegram-групах,
JARVIS будує **граф зв'язків** (хто кому підпорядкований, хто з ким працює), збирає контекст із усіх
каналів із урахуванням цих зв'язків і **оркеструє бізнес-процеси** по ієрархії — усе під єдиною
org-auth, за прапором, не ламаючи self-hosted сценарій одного користувача.

---

## 1. Навіщо новий трек (а не розширення існуючих)

Запит — це **командна взаємодія**, і він не лягає на жоден існуючий примітив без концептуального зсуву:

| Існуюче в репо | Що це насправді | Чому не покриває запит |
|----------------|-----------------|------------------------|
| `tools/app/teams.py` (`jarvis:team:*`) | **Agent Teams** — AI-pipeline (researcher→coder→reviewer) для **однієї** задачі одного користувача | Це AI-субагенти, а не люди-учасники з ролями/ієрархією |
| `tools/app/orchestrator.py` | **Orchestrator+Critic** (Mediator) для **однієї** відповіді | Не cross-actor, не довгоживучий, не знає про людей |
| `SAAS_DEEP_DIVE.md` org/member/role | tenant-ізоляція (мультитенант enabler) | Дає `org_id`/`role`, але модель доступу — **строго owner-scoped** (anti-IDOR: кожен запис фільтрується по `user_id`). Команда вимагає **спільної видимості** |
| `CONTEXT_MODULE.md` (паспорти) | персональний контекст 1 власника (`owner_uid`) | Немає **суб'єктів** (про кого), **аудиторії** (кому видно), графа зв'язків |
| Telegram-бот (`gateway/app/router.py`) | private-chat-центричний, whitelist по `user_id` | Групи (`group`/`supergroup`) не обробляються; немає ідентифікації членів, ambient-збору |

**Висновок:** потрібен новий доменний шар (граф зв'язків + видимість + процеси + проактивність)
поверх SaaS-tenant-фундаменту. Це **Стовп D**, а не пункт у наявному треку.

### 1.1 Найважливіше архітектурне рішення

> **Зсув моделі доступу: `owner-scoped` → `policy-scoped` (RBAC + граф зв'язків).**

Уся теперішня дисципліна (`AGENTS.md` §5, SAAS §4.0 IDOR) каже: *кожен `get_by_id` фільтрує по
`rec["user_id"]`*. Команда це **ламає за дизайном** — асистент менеджера **мусить** бачити спільний
контекст підлеглих/колег. Тому між «store» і «consumer» з'являється **шар політики видимості**
(`Visibility / ACL`), що відповідає на питання *«чи може актор A прочитати ресурс R суб'єкта B?»* на
основі ролі + ребра графа + рівня чутливості паспорта. Owner-scoped лишається **дефолтом** (приватне);
share — **явний opt-in**. Це наскрізна зміна, її треба закласти **до** написання фіч команди.

---

## 2. Цільова модель (доменні поняття)

```
Organization (workspace / tenant)         — вже є в SAAS-схемі
 └─ Squad (org-unit / «команда» в UI)      — NEW: піддерево ієрархії (відділ, проєктна група)
     └─ Member (людина)                    — вже є (members), + posada/seniority
         ├─ Delegate (AI-асистент особи)   — NEW: персона+делеговані повноваження (scopes)
         └─ relationships (ребра графа)    — NEW: reports_to / manages / assists / collaborates
 └─ Group (Telegram-група, прив'язана)     — NEW: канал спостереження + взаємодії
 └─ Process (бізнес-процес)                — NEW: cross-actor workflow зі станом і призначеннями
```

> **Naming (рішення проти колізії):** код-рівень людських юнітів — **`squad`** (бо `jarvis:team:` уже
> зайнято Agent Teams). Продуктовий термін у UI — «команда». Існуючі AI-`teams` у доках варто
> поступово перейменувати на **«Agent Crew»**, але це окремий косметичний PR (не блокер).

### 2.1 Делегат (ядро «менеджер ↔ асистент»)

**Делегат** = екземпляр асистента, прив'язаний до конкретного principal (людини), з:
- **персоною** (тон, мова, пріоритети, робочі години principal);
- **scopes делегованих повноважень** — що делегат може робити *від імені* principal без перепитування
  (напр. `read:team_context`, `propose:meeting`, `draft:reply`) і що — лише з підтвердженням (S4:
  гроші/незворотне/зовнішні відправлення → завжди HITL);
- **видимістю** — успадковує позицію principal у графі (бачить те, що бачить principal + share-и).

Делегати **координуються між собою** (delegate-to-delegate): напр. делегат менеджера питає делегата
підлеглого статус задачі → той відповідає з контексту підлеглого в межах дозволеної видимості. Це і є
«командна взаємодія між менеджерами та їх асистентами».

### 2.2 Один бот, багато персон (модель присутності)

Telegram віддає апдейти **одному споживачу на токен** (README §polling). Тому:
- **MVP:** один **org-бот** на організацію (`organizations.telegram_bot_token_enc`, уже передбачено в
  SAAS §4.8). У DM він — персональний делегат співрозмовника (персона за `from.id → member`); у групі —
  спільний асистент команди.
- **Пізніше (опційно):** окремий бот на менеджера (`delegate.bot_token_enc`) для приватних потоків.

Це поважає S3 (Telegram — канал): уся логіка персон/видимості — у `jarvis_core`, gateway лише маршрутизує.

---

## 3. Граф зв'язків (identity + relationships)

### 3.1 Нові таблиці (міграція `004_team_ecosystem.py`, розширює SAAS `003`)

```sql
-- Піддерево організації: відділи / проєктні групи
CREATE TABLE IF NOT EXISTS squads (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    parent_id   UUID REFERENCES squads(id) ON DELETE CASCADE,  -- ієрархія
    name        TEXT NOT NULL,
    kind        TEXT NOT NULL DEFAULT 'team',  -- team|department|project
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Членство людини в squad + посада
CREATE TABLE IF NOT EXISTS squad_members (
    squad_id    UUID NOT NULL REFERENCES squads(id) ON DELETE CASCADE,
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title       TEXT,            -- «Head of Sales», «PM», ...
    seniority   TEXT,            -- lead|senior|member
    PRIMARY KEY (squad_id, user_id)
);

-- Ребра графа зв'язків (directed, typed)
CREATE TABLE IF NOT EXISTS relationships (
    id          BIGSERIAL PRIMARY KEY,
    org_id      UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    src_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    dst_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind        TEXT NOT NULL,   -- reports_to|manages|assists|delegate_of|collaborates_with
    weight      REAL NOT NULL DEFAULT 1.0,  -- сила (для interaction-graph, оновлюється спостереженням)
    source      TEXT NOT NULL DEFAULT 'declared',  -- declared|observed
    meta        JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (org_id, src_user_id, dst_user_id, kind)
);
CREATE INDEX idx_rel_org_src ON relationships (org_id, src_user_id, kind);
CREATE INDEX idx_rel_org_dst ON relationships (org_id, dst_user_id, kind);

-- Делегат (AI-асистент особи)
CREATE TABLE IF NOT EXISTS delegates (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id        UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    principal_id  UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    persona       JSONB NOT NULL DEFAULT '{}'::jsonb,   -- тон, мова, робочі години
    scopes        TEXT[] NOT NULL DEFAULT ARRAY['read:self'],  -- делеговані повноваження
    proactive     BOOLEAN NOT NULL DEFAULT false,
    bot_token_enc TEXT,                                  -- опційний власний бот (пізніше)
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (org_id, principal_id)
);

-- Прив'язані Telegram-групи (канали спостереження)
CREATE TABLE IF NOT EXISTS tg_groups (
    chat_id     BIGINT PRIMARY KEY,         -- Telegram chat id (negative для груп)
    org_id      UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    squad_id    UUID REFERENCES squads(id) ON DELETE SET NULL,
    title       TEXT,
    ingest      TEXT NOT NULL DEFAULT 'off',  -- off|addressed|ambient (рівень згоди)
    consented_by UUID REFERENCES users(id),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Спостережене членство в групі (tg_id → member) — «ідентифікація через telegram id»
CREATE TABLE IF NOT EXISTS tg_group_members (
    chat_id     BIGINT NOT NULL REFERENCES tg_groups(chat_id) ON DELETE CASCADE,
    telegram_id BIGINT NOT NULL,
    user_id     UUID REFERENCES users(id),  -- NULL поки не злінкований (unknown member)
    last_seen   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (chat_id, telegram_id)
);
```

### 3.2 Доменний модуль графа (`jarvis_core/orggraph/`)

Домен живе в `jarvis_core` (P8, статут §5 — не дублювати gateway↔tools↔memory):

```
jarvis_core/orggraph/
  models.py      # Squad, Relationship, Delegate, OrgNode (frozen dataclasses)
  graph.py       # OrgGraph: ancestors()/descendants()/path()/neighbors(kind)/can_see()
  resolve.py     # identity: telegram_id → member → squad → manager chain
  visibility.py  # VisibilityPolicy: (actor, resource_owner, sensitivity) → bool (див. §4)
```

`OrgGraph` будується з трьох таблиць (`squads`, `squad_members`, `relationships`), кешується в Redis
(`jarvis:{org_id}:orggraph` з TTL + invalidation на write) — щоб ретрив не бив у БД щоразу.

### 3.3 Дві природи графа

1. **Declared graph** (`source='declared'`) — введений людиною/адміном: ієрархія, хто кому reports_to.
2. **Observed graph** (`source='observed'`, `weight`) — будується спостереженням взаємодій у групах/DM:
   частота згадок, відповіді один одному, спільні процеси → підсилює `weight` ребра `collaborates_with`.
   Це і є «розуміння зв'язків між користувачами» — не лише декларація, а **вивчені** зв'язки.

---

## 4. Видимість та доступ (Visibility / ACL) — наскрізний шар

Центральна зміна §1.1. Кожен паспорт/ресурс отримує **аудиторію**, ретрив фільтрується **політикою**.

### 4.1 Розширення паспорта (`jarvis_core/passport/models.py`)

```python
@dataclass(frozen=True)
class Passport:
    # ... наявні поля (kind, summary, tags, sensitivity, owner_uid, org_id) ...
    subjects: list[str] = field(default_factory=list)   # NEW: про кого (user_id/tg_id/person:tag)
    visibility: str = "private"   # NEW: private|squad|org|custom
    audience: list[str] = field(default_factory=list)   # NEW: явні user_id/squad_id (для custom)
    group_ref: int | None = None  # NEW: chat_id, якщо паспорт із групи
```

### 4.2 Політика (`jarvis_core/orggraph/visibility.py`)

```python
def can_read(actor: RequestContext, p: Passport, graph: OrgGraph) -> bool:
    if p.org_id != actor.org_id:
        return False                                  # tenant-ізоляція (SAAS)
    if p.sensitivity in ("health", "finance") and actor.user_id not in (p.owner_uid, *p.subjects):
        return False                                  # чутливе — лише власник/суб'єкт
    match p.visibility:
        case "private": return actor.user_id == p.owner_uid
        case "org":     return True                   # будь-хто в org
        case "squad":   return graph.share_squad(actor.user_id, p.owner_uid)
        case "custom":  return actor.user_id in p.audience or graph.in_audience(actor, p.audience)
    return False
```

Делегат успадковує видимість principal: `actor` делегата = principal + scope-розширення. Менеджер
(через граф `manages`/`reports_to`) отримує `squad`-видимість контексту підлеглих — але **ніколи**
health/finance без явного share. Це поважає privacy (THREAT_MODEL треба розширити — див. §8).

### 4.3 Ретрив стає graph-aware

`ContextQuery` (CONTEXT_MODULE §5) додає `as_actor` + пост-фільтр `can_read`. Memory повертає кандидатів
по org_id (груба межа), тонку межу (visibility) застосовує `jarvis_core` (бо домен) — або, для
продуктивності, SQL-предикат `visibility/audience` у `memory/app/context/`.

---

## 5. Присутність у групах і ambient-контекст

### 5.1 Gateway: обробка group/supergroup (зараз відсутня)

`gateway/app/router.py` нині бере `chat_id` як приватний чат. Додаємо розгалуження по `chat.type`:

```python
chat = message.get("chat", {})
if chat.get("type") in ("group", "supergroup"):
    await handle_group_message(message, chat, tg, tools, redis)   # NEW шлях
    return
# ... наявний private-flow без змін (S2: self-hosted не ламається) ...
```

`handle_group_message` (новий `gateway/app/bot/group.py`):
1. **Ідентифікація:** `message.from.id` + `new_chat_members`/`left_chat_member` → upsert `tg_group_members`
   (tg_id → user якщо злінкований; інакше «unknown», запит на лінк). Це «ідентифікація членів через tg id».
2. **Рівень згоди** (`tg_groups.ingest`):
   - `off` — бот мовчить, нічого не збирає (дефолт; S2/privacy);
   - `addressed` — реагує/збирає лише на **@mention** або reply на бота;
   - `ambient` — пасивно збирає всі повідомлення в паспорти (потребує явної згоди адміна групи).
3. **Адресація:** `@bot ...` або reply → звичайний agent-turn, але `RequestContext` несе `group_ref`,
   а делегат — персону того, хто звернувся.

### 5.2 Ambient-збір → паспорти (P9/P10)

Кожне зібране групове повідомлення йде канонічним конвеєром CONTEXT_MODULE (raw-path, batch-summarize),
але з командними тегами й аудиторією:

```
tags:     ["kind:group_msg", "group:<title>", "person:<from>", "squad:<id>", "topic:<...>"]
subjects: [<from_user_id>, <@mentioned_user_ids>]
visibility: "squad"          # дефолт для групи прив'язаної до squad
sensitivity: за Redactor (PII у групі → redact перед store)
```

Так бот «збирає контекст із усіх доступних джерел, розуміючи зв'язки»: групові паспорти стають
graph-aware пам'яттю, доступною делегатам команди за політикою видимості.

### 5.3 Redis-ключі (org-scoped, за дисципліною статуту)

| Ключ | Призначення |
|------|-------------|
| `jarvis:{org_id}:orggraph` | кеш зібраного графа (TTL + invalidation) |
| `jarvis:{org_id}:group:{chat_id}:buffer` | дебаунс-буфер ambient-повідомлень перед batch-summarize |
| `jarvis:{org_id}:group:{chat_id}:members` | гарячий кеш tg_id→user для швидкої ідентифікації |
| `jarvis:{org_id}:process:{id}` | стан бізнес-процесу (§6) |
| `jarvis:{org_id}:proactive:cursor:{user_id}` | курсор проактивного циклу делегата (§7) |

---

## 6. Оркестрація бізнес-процесів (BPO)

Над разовим `orchestrator.py` (Mediator для однієї відповіді) — **довгоживучі, cross-actor процеси**.

### 6.1 Модель `Process` (`jarvis_core/process/`)

```python
@dataclass
class ProcessStep:
    id: str
    title: str
    assignee_user_id: str          # людина АБО делегат
    kind: str                      # human_task|delegate_task|approval|notify|wait_event
    status: str                    # pending|active|blocked|done|skipped
    due: str | None                # SLA → інтеграція з reminders
    depends_on: list[str]

@dataclass
class Process:
    id: str
    org_id: str
    squad_id: str | None
    owner_user_id: str
    title: str
    template: str | None           # з бібліотеки шаблонів (onboarding, deal, incident...)
    steps: list[ProcessStep]
    status: str                    # draft|running|paused|done|cancelled
```

### 6.2 Двигун

`jarvis_core/process/engine.py` — машина станів (паттерн State + Mediator): рахує готові кроки
(depends_on satisfied) → диспетчеризує:
- `delegate_task` → bg_job агент-лупу делегата виконавця;
- `human_task` → нагадування/повідомлення в Telegram виконавцю (через gateway) з кнопками «✅ done / ⏸ blocked»;
- `approval` → HITL-підтвердження (S4) у відповідального;
- `wait_event` → підписка на сигнал із групи/контексту (Observer).

Стан — у Redis (`jarvis:{org_id}:process:{id}`) + знімок у Postgres (`processes`, `process_steps`,
audit у наявний `audit_log` SAAS §3.1). **Ієрархія команди** входить тут: маршрутизація approval вгору по
`reports_to`, ескалація по SLA до менеджера, видимість процесу — по `squad`.

### 6.3 Перевикористання, не переписування (P6/P4)

- Виконання кроку делегатом = наявний агент-луп (`tools/app/agent.py`) + субагенти/Agent Teams як
  «робоча сила» всередині кроку.
- Призначення/нагадування = наявні `reminders` (Redis ZSET) + gateway-поллер.
- НЕ вводимо Celery/Temporal (P6, статут §6) — машина станів на наявному async + bg_jobs достатня для старту.

---

## 7. Проактивний рушій (observe → propose → act)

CONTEXT_MODULE згадує «proposal-engine (bg_job)» як споживача — формалізуємо в делегата.

### 7.1 Цикл (за прапором `DELEGATE_PROACTIVE_ENABLED`, дефолт off — S2/S4)

```
OBSERVE   нові паспорти/події з останнього курсора (групи, DM, процеси, календар-конектор)
   ▼
REASON    агент-луп делегата над свіжим контекстом + графом:
          «що потребує уваги principal? які кроки процесів забуксували? хто чекає відповіді?»
   ▼
PROPOSE   список дій-кандидатів із обґрунтуванням і рівнем ризику
   ▼
GATE      S4: read-only/draft → можна авто; мутуюче/зовнішнє/гроші → ЗАВЖДИ підтвердження principal
   ▼
ACT/NOTIFY  виконати дозволене; решту — як пропозицію в Telegram («Пропоную… ✅/✏️/❌»)
```

Реалізація: новий `JOB_TYPE` `delegate_tick` у `jarvis_core/bg_jobs.py`, тригериться наявним
`gateway/app/context_scheduler.py` (прецедент ADR-008: запуск **із нагляду**, не прихований auto-cron).
Курсор — `jarvis:{org_id}:proactive:cursor:{user_id}`. Антиспам: rate-limit пропозицій/день на principal.

### 7.2 Що робить асистента «проактивним та автоматизованим»

- **Daily brief** делегата: ранковий дайджест по графу (що в команді змінилось, мої задачі, ризики).
- **Watcher-и:** «задача без відповіді 24г», «крок процесу прострочив SLA», «@mention мене в групі».
- **Авто-чернетки:** делегат готує draft-відповідь/підсумок зустрічі — principal лише апрувить (S4).

---

## 8. Cross-cutting (поважаємо принципи статуту)

| Концерн | Рішення | Принцип |
|---------|---------|---------|
| Self-hosted не ламається | усе за `TEAM_MODE`/`SAAS_MODE`; solo-користувач = org з 1, без груп/графа — наявний flow без змін | S2 |
| Telegram — лише канал | граф/видимість/процеси/проактивність — у `jarvis_core`; gateway лише I/O + маршрут груп | S3 |
| Human-in-the-loop | проактивні мутуючі/зовнішні дії + approval-кроки — завжди підтвердження | S4 |
| Separation of concerns | домен `jarvis_core/{orggraph,process,passport}`, store `memory`+Postgres, I/O `gateway` | P8 |
| Паспорт + теги всюди | груповий сигнал/крок процесу/пропозиція — кожен з `summary`+namespaced-тегами+embedding | P9/P10/C1 |
| Org-scope / anti-IDOR | усі нові ключі `jarvis:{org_id}:…`; усі нові `get_by_id` — ownership/visibility-гейт | SAAS §4.0 |
| **Privacy (нове, критично)** | груповий ambient = **дані третіх осіб** → явна згода `tg_groups.ingest`, redaction, ledger, opt-out; розширити [`THREAT_MODEL.md`](THREAT_MODEL.md) розділом «multi-party / group data» | S1/новий ризик |
| Композиція роутерів | нові розділи Platform/tools — `register(router)`, один рядок у `router.py` | P4/статут §5 |

### 8.1 Найбільший новий ризик — приватність груп

Збір повідомлень інших людей у групі — це обробка персональних даних третіх осіб. **Обов'язково:**
1. Дефолт `ingest='off'`; `ambient` лише після явної згоди адміна групи (commands `/jarvis_consent`).
2. Видимий **privacy ledger** (наявний `/context/ledger`) — що зібрано/кому видно.
3. Redaction PII перед store; health/finance ніколи не share поза власником.
4. Per-user opt-out (член може заборонити збір своїх повідомлень → паспорти його `subjects` не пишуться).
5. Розширити THREAT_MODEL: загроза «менеджер читає приватне підлеглого» закривається `VisibilityPolicy`.

---

## 9. Зміни по сервісах (інвентар)

| Шар | Файли (NEW / зміна) | Суть |
|-----|---------------------|------|
| **Domain** | `jarvis_core/orggraph/*` (NEW), `jarvis_core/process/*` (NEW), `jarvis_core/passport/models.py` (+subjects/visibility/audience) | граф, видимість, процеси, паспорт-аудиторія |
| **Storage** | `memory/migrations/004_team_ecosystem.py` (NEW), `memory/app/context/` (visibility-предикат), `memory/app/db.py` (squads/relationships/processes CRUD) | tenant-таблиці команди |
| **Tools** | `tools/app/routes/orggraph.py`, `routes/process.py`, `delegate_tick` у bg_jobs | API графа/процесів + проактивний тік |
| **Gateway I/O** | `gateway/app/bot/group.py` (NEW), `router.py` (розгалуження chat.type), `platform/{squads,relationships,delegates,processes}.py` (proxy), `static/platform.html` (таб «Команда / Процеси / Граф») | групи, Platform-консоль команди |
| **Auth/Context** | `jarvis_core/context.py` (RequestContext +delegate-as-actor), `platform/auth.py` (resolve delegate scopes) | актор = principal або делегат |

**Антипатерн, якого уникаємо:** не правити 18 platform-модулів і 20 tools-routes поодинці — нові розділи
додаються через наявний `proxy.py` + `register(router)` (SAAS §0.3 стратегія вже довела підхід).

---

## 10. API-контракти (нові)

```
# Org graph / squads
GET    /platform/api/squads                 → дерево squads + members
POST   /platform/api/squads                 { name, parent_id?, kind }
POST   /platform/api/relationships          { src, dst, kind }       # declared edge
GET    /platform/api/graph?user_id=         → neighbors + manager chain (для UI-візуалізації)

# Delegates
GET    /platform/api/delegates/me
PATCH  /platform/api/delegates/me           { persona, scopes, proactive }

# Groups
GET    /platform/api/groups                 → прив'язані tg-групи + ingest-рівень
POST   /platform/api/groups/{chat_id}/consent { ingest: off|addressed|ambient }

# Processes (BPO)
GET    /platform/api/processes              → список (visibility-filtered)
POST   /platform/api/processes              { title, template?, squad_id?, steps[] }
POST   /platform/api/processes/{id}/advance { step_id, status }       # human task update
GET    /platform/api/processes/{id}         → стан + audit
```

Telegram-команди (канал): `/team`, `/who <@user>` (хто це в графі), `/delegate` (налаштувати асистента),
`/process new|status`, `/jarvis_consent` (згода групи). Логіка — у `jarvis_core`, не в боті (S3).

---

## 11. Фази треку (TC-0 … TC-6)

Стартова умова всього треку — **SaaS PR#0 (✅) + PR#1 (✅ foundation) + PR#2 (tenant schema)**: без
`org_id`/`RequestContext` команда не має фундаменту. Послідовність:

| Фаза | Зміст | Старт-умова | Цінність |
|------|-------|-------------|----------|
| **TC-0** | `orggraph` домен + таблиці `squads/squad_members/relationships` + Platform таб «Команда» (declared graph) | SaaS PR#2 | ієрархія введена й видима |
| **TC-1** | `VisibilityPolicy` + паспорт `subjects/visibility/audience` + graph-aware ретрив | TC-0 | спільна пам'ять за політикою (ядро зсуву §1.1) |
| **TC-2** | Group presence: `chat.type` routing, ідентифікація членів, `tg_groups` + згода | TC-1 | бот живе в групах, ідентифікує по tg_id |
| **TC-3** | Ambient-збір → паспорти (raw-path batch) + observed-graph (`weight`) | TC-2 | «розуміння зв'язків» + контекст із груп |
| **TC-4** | Delegate: персона + scopes + delegate-as-actor; DM-персони | TC-1 | «менеджер ↔ асистент» формалізовано |
| **TC-5** | Proactive engine (`delegate_tick`, daily brief, watchers, HITL-gate) | TC-4 | «проактивний та автоматизований» |
| **TC-6** | BPO: `Process` engine, шаблони, approval/SLA-ескалація по ієрархії | TC-4 + reminders | «оркестрація бізнес-процесів» |

**Найкоротший шлях до демо-цінності:** TC-0 → TC-1 → TC-2 → TC-4 (граф + видимість + групи + делегат)
дає вже «асистент бачить команду й контекст групи». TC-5/TC-6 — проактивність і процеси — зверху.

### 11.1 Тест-матриця (обов'язкове перед кожною фазою)

| Тест | Фаза |
|------|------|
| `test_visibility_private_blocks_peer` / `test_manager_sees_squad_not_health` | TC-1 |
| `test_cross_org_graph_isolation` (граф org A не видно org B) | TC-0 |
| `test_group_ingest_off_collects_nothing` / `test_member_optout_skips_subject` | TC-2/3 |
| `test_delegate_scope_blocks_external_send_without_confirm` | TC-4/5 |
| `test_process_approval_escalates_by_reports_to` | TC-6 |
| `test_self_hosted_solo_no_team_unchanged` (S2 регрес) | усі |

---

## 12. Рішення для власника (потрібні до старту)

| # | Питання | Варіанти | Рекомендація |
|---|---------|----------|--------------|
| D-1 | Підняти це до «Стовпа D» у `AGENTS.md`/`PRODUCT_ROADMAP`? | так (4-й стовп) · лишити підтреком SaaS | **Стовп D** — обсяг і цінність окремі від tenant-enabler |
| D-2 | Модель присутності | один org-бот + персони · бот на менеджера | **org-бот + персони** (MVP, Telegram 1-consumer/токен) |
| D-3 | Дефолт ambient-збору | off · addressed | **off** (privacy-first; ambient лише з явної згоди) |
| D-4 | Naming колізія `team` | перейменувати AI→Agent Crew зараз · squad для людей | **`squad` для людей** зараз; rename AI — окремий косметичний PR |
| D-5 | Видимість у memory vs jarvis_core | SQL-предикат у memory · пост-фільтр у домені | **гібрид**: груба межа org у SQL, тонка visibility — `can_read` у домені (P8) |

---

## 13. Зв'язок з наявними roadmap

| Існуюче | Як використовується Стовпом D |
|---------|-------------------------------|
| SAAS org/member/role/`RequestContext` | фундамент ідентичності — D будує граф зверху |
| CONTEXT_MODULE паспорти P9/P10 | носій контексту; D додає `subjects/visibility/audience` |
| `orchestrator.py` (Mediator) | примітив для кроку процесу; BPO — довгоживуча обгортка |
| Agent Teams / subagents | «робоча сила» всередині `delegate_task` кроку |
| reminders (Redis ZSET) | SLA/нагадування кроків процесу |
| `context_scheduler.py` (ADR-008) | тригер `delegate_tick` проактивного циклу |
| Platform `proxy.py` + `register()` | додавання табів «Команда/Граф/Процеси» без розповзання |

---

## 14. Історія документа

| Дата | Версія | Зміна |
|------|--------|-------|
| 2026-06-17 | 0.1 | Початкова пропозиція Стовпа D: граф зв'язків, видимість, групи, делегати, проактивність, BPO |

---

*Це трек-пропозиція. Прийняття як «Стовп D» → оновити [`AGENTS.md`](../AGENTS.md) §2 і
[`PRODUCT_ROADMAP.md`](PRODUCT_ROADMAP.md) doc-map (D1 doc-code sync). Принципи — [`AGENTS.md`](../AGENTS.md);
tenant-фундамент — [`SAAS_DEEP_DIVE.md`](SAAS_DEEP_DIVE.md); контекст — [`CONTEXT_MODULE.md`](CONTEXT_MODULE.md).*
</content>
</invoke>
