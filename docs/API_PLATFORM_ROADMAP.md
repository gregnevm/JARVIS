# JARVIS — API Platform Roadmap (Стовп A)

> **Версія:** 1.1 (2026-06-16)
> **Статус:** Living document.
> **Мета:** довести JARVIS від «один глобальний OpenAI-сумісний ключ» до **повноцінної платформи
> розробника** як OpenAI/Anthropic Platform — per-org ключі, повний `/v1`, usage, console, playground, SDK.

**Пов'язані документи**

| Документ | Роль |
|----------|------|
| [`AGENTS.md`](../AGENTS.md) | Конституція — Стовп A, принципи |
| [`docs/PRODUCT_ROADMAP.md`](PRODUCT_ROADMAP.md) | Парасолька — трек A фазовий статус |
| [`docs/SAAS_DEEP_DIVE.md`](SAAS_DEEP_DIVE.md) | **Enabler** — tenant/identity/keys/billing impl (PR#0…#7) |
| [`docs/PLATFORM_ROADMAP.md`](PLATFORM_ROADMAP.md) | Web-консоль — дім для developer-console табів |
| [`docs/THREAT_MODEL.md`](THREAT_MODEL.md) | Auth/IDOR/rate-limit поверхня |

> **Зв'язок із SAAS_DEEP_DIVE:** цей файл — **продуктовий** погляд (що бачить розробник, фази).
> SAAS_DEEP_DIVE — **імплементаційний** (таблиці БД, Redis-ключі, PR-послідовність). Tenant-механіка
> (org/user/api_keys/usage_events) живе там; тут — як вона стає продуктом.

---

## 1. Позиціонування

### 1.1 Що означає «як OpenAI/Anthropic Platform»

| OpenAI/Anthropic Platform | JARVIS-ціль | Де в коді |
|----------------------------|-------------|-----------|
| `Bearer sk-…` per-account keys | per-org keys, scopes, prefix-hash, revoke | `gateway/app/saas/api_keys.py` (новий) |
| `/v1/chat/completions`, `embeddings`, `models`, `responses` | повний `/v1` surface | `gateway/app/openai_api.py` |
| Dashboard: usage, logs, billing | developer-console таби в `/platform` | `gateway/app/platform/*`, `platform.html` |
| Playground | workbench → playground для `/v1` | `gateway/app/platform/workbench.py` |
| Rate-limits per key | org-scoped rate-limit + plan limits | `gateway/app/ratelimit.py`, `saas/plan_limits.py` |
| SDK (python/node) | thin клієнти + OpenAPI | новий `sdk/` |
| Usage/billing | usage_events + Stripe (cloud) | `saas/billing.py` (новий) |

**Ключова теза:** OpenAI-сумісний `/v1` вже існує (opt-in), і агентний фундамент (jobs, teams,
research) можна виставити як async-ендпоїнти. Бракує **identity-шару** (per-org keys замість одного
глобального), **повноти `/v1`**, **developer-console UX** і **usage/метерингу**. Усе це сидить на
tenant-фундаменті з SAAS_DEEP_DIVE.

### 1.2 North Star (Стовп A)

> Розробник заходить на `/platform`, створює org, генерує `sk-jarvis-live-…`, копіює quickstart,
> ставить `base_url=https://my-jarvis/v1` у OpenAI SDK — і код працює без змін. У консолі бачить
> usage за день, останні запити, ліміти плану. Self-hosted — той самий UX, лише один synthetic org.

### 1.3 Принципи (Стовп A)

- **Drop-in сумісність:** OpenAI SDK має працювати зміною лише `base_url`+`api_key` (S-сумісність).
- **Self-hosted = synthetic org:** `SAAS_MODE=false` → один org, ключі опційні, нічого не ламається (S2).
- **Keys ніколи не в логах:** показ ключа один раз; зберігаємо лише `prefix` + `hash` (S-безпека).
- **404, не 403, на cross-tenant:** не розкривати існування чужих ресурсів (THREAT_MODEL).

---

## 2. Baseline (стан на 2026-06-15)

### 2.1 Реалізовано

| Компонент | Стан | Файл |
|-----------|------|------|
| `POST /v1/chat/completions` | ✅ opt-in (`ENABLE_OPENAI_API`) | `gateway/app/openai_api.py` |
| `GET /v1/models` | ✅ | `gateway/app/openai_api.py` |
| Bearer auth | ✅ один глобальний `OPENAI_API_KEY` | `_auth_bearer()` |
| SSE stream | ✅ | `StreamingResponse` |
| user-id resolution | ✅ header/body/default | `_resolve_user_id()` |
| Async-агент (jobs/teams/research) | ✅ внутрішньо, не як `/v1` | `tools/app/bg_jobs.py` |

### 2.2 Оцінка зрілості (чесно)

| Критерій | Оцінка | Коментар |
|----------|--------|----------|
| `/v1` сумісність | **6/10** | chat+models+embeddings є (AP-0, AP-2.1); немає responses/usage |
| Identity / keys | **2/10** | один глобальний ключ; немає org/scopes/revoke |
| Developer console | **2/10** | немає keys/usage/playground UI |
| Метеринг / ліміти | **3/10** | rate-limit глобальний; немає per-key usage |
| SDK / docs | **1/10** | немає клієнтів/OpenAPI/quickstart |
| Білінг | **0/10** | лише blueprint у SAAS |

### 2.3 Розриви (gap list)

| # | Gap | Вплив |
|---|-----|-------|
| AB1 | Один глобальний ключ замість per-org | Немає мультикористувацького API |
| AB2 | Немає `/v1/embeddings`, `/v1/responses`, `/v1/usage` | Неповна сумісність |
| AB3 | Немає developer-console (keys/usage/playground) | Розробник не self-serve |
| AB4 | Rate-limit і metrics глобальні (SAAS §0.2) | Немає per-key метерингу/білінгу |
| AB5 | `get_by_id` без ownership (SAAS §4.0 IDOR) | Cross-tenant читання — блокер перед публічним API |
| AB6 | Немає SDK/OpenAPI/quickstart | Високий поріг входу |

---

## 3. Фази розвитку (AP-0…AP-6)

```
AP-0 (/v1 baseline ✅) ─► [enabler: SAAS PR#0 IDOR + PR#1 tenant ctx] ─► AP-1 (keys)
   ─► AP-2 (/v1 повнота) ─► AP-3 (console+playground) ─► AP-4 (limits/metering)
   ─► AP-5 (SDK+docs) ─► AP-6 (billing, cloud-only)
```

---

## AP-0 — `/v1` baseline · ✅ **done**

| # | Задача | Статус |
|---|--------|--------|
| AP-0.1 | `POST /v1/chat/completions` (opt-in) | [x] |
| AP-0.2 | Bearer auth + SSE stream | [x] |
| AP-0.3 | `GET /v1/models` | [x] |

---

## AP-1 — API-ключі (per-org) · **блокується SAAS PR#0/#1**

**Мета:** замість одного `.env`-ключа — керовані per-org ключі.

| # | Задача | DoD | Статус |
|---|--------|-----|--------|
| AP-1.0 | **SAAS PR#0** — IDOR fix (`get_by_id` ownership) | Cross-tenant get → 404 | [ ] |
| AP-1.1 | **SAAS PR#1** — `jarvis_core/context.py` RequestContext + tenant headers | `X-JARVIS-Org-Id/User-Id` | [ ] |
| AP-1.2 | `api_keys` таблиця (prefix, hash, scopes, revoked_at) | Міграція `003_saas_tenant` | [ ] |
| AP-1.3 | `gateway/app/saas/api_keys.py` — CRUD + lookup by prefix | bcrypt hash, show-once | [ ] |
| AP-1.4 | `/v1` auth → per-org key замість глобального; fallback на global для self-hosted | Backward compat | [ ] |
| AP-1.5 | Scopes enforcement (`chat`, `embeddings`, `jobs`) | 403 поза scope | [ ] |

**Вихід AP-1:** `POST /saas/api/keys` створює `sk-jarvis-live-…`; `/v1` приймає його; revoke працює.

---

## AP-2 — `/v1` повнота · **3–4 тижні**

**Мета:** drop-in для OpenAI SDK по основних ендпоїнтах.

| # | Задача | DoD | Статус |
|---|--------|-----|--------|
| AP-2.1 | `POST /v1/embeddings` (nomic-embed-text) | OpenAI-формат відповіді | [x] `gateway/app/openai_api.py` → memory `/embed`; str|list[str] input, OpenAI list-формат, 502 на backend-збій |
| AP-2.2 | `POST /v1/responses` (агентний, tool-use) — мапа на `AgentRunner` | tools[] + tool_calls | [ ] |
| AP-2.3 | `GET /v1/models` із реальним каталогом (CHAT/AGENT/VISION/EMBED/LoRA) | tags із Ollama | [ ] |
| AP-2.4 | `GET /v1/usage` — токени/запити за період (per-key) | usage_events агрегат | [ ] |
| AP-2.5 | `POST /v1/jobs` + `GET /v1/jobs/{id}` — async (research/team/coding) | Reuse bg_jobs | [ ] |
| AP-2.6 | Error-codes per OpenAI (401/402/404/429) | Сумісні тіла помилок | [ ] |

**Вихід AP-2:** `openai.OpenAI(base_url=…).chat/embeddings/models` працюють незмінно.

---

## AP-3 — Developer console + playground · **3–4 тижні**

**Мета:** self-serve у `/platform` (нова nav-група «Developer»).

| # | Задача | DoD | Статус |
|---|--------|-----|--------|
| AP-3.1 | Tab **API Keys** — create/list/revoke, show-once | `platform.html` + `saas/api_keys` | [ ] |
| AP-3.2 | Tab **Usage** — графіки токенів/запитів, per-key breakdown | `/v1/usage` charts | [ ] |
| AP-3.3 | Tab **Playground** — `/v1` запит із UI (model, messages, stream) | Reuse Workbench SSE | [ ] |
| AP-3.4 | Tab **API Logs** — останні запити (status, latency, tokens) | request_id трейс | [ ] |
| AP-3.5 | **Quickstart** панель — curl/python/node snippet із підставленим ключем | Copy-paste готовий | [ ] |

**Вихід AP-3:** розробник не торкається `.env` — усе через консоль.

---

## AP-4 — Ліміти й метеринг · **2–3 тижні**

**Мета:** per-key/per-org rate-limit і usage для білінгу.

| # | Задача | DoD | Статус |
|---|--------|-----|--------|
| AP-4.1 | Org-scoped rate-limit ключі (SAAS §1.4) | `jarvis:{org}:rl:…` | [ ] |
| AP-4.2 | `usage_events` запис на кожен виклик (turn/token/embed/job) | append-only + nightly rollup | [ ] |
| AP-4.3 | `plan_limits.py` enforcement (free/pro/team/studio) | 402 при перевищенні | [ ] |
| AP-4.4 | Per-org metrics (розщепити глобальні, SAAS §0.2) | `jarvis:{org}:metrics:*` | [ ] |
| AP-4.5 | Soft/hard ліміти + grace (fail-open ops, fail-closed billing) | Config | [ ] |

**Вихід AP-4:** перевищення ліміту → 402; usage видно в консолі й готовий до білінгу.

---

## AP-5 — SDK + docs · **2–3 тижні**

| # | Задача | DoD | Статус |
|---|--------|-----|--------|
| AP-5.1 | OpenAPI-спека для `/v1` + `/saas/api/*` | `/openapi.json` повна | [ ] |
| AP-5.2 | Python SDK (thin, або «use openai with base_url») | README quickstart | [ ] |
| AP-5.3 | JS/TS SDK (або openai-node інструкція) | README quickstart | [ ] |
| AP-5.4 | Docs-сайт / `docs/api/` — endpoints, auth, errors, rate-limits | Згенеровано з OpenAPI | [ ] |
| AP-5.5 | Postman/insomnia колекція | Експорт | [ ] |

**Вихід AP-5:** «5 хв від signup до першого виклику» (KPI).

---

## AP-6 — Білінг (cloud-only) · **блокується SAAS PR#5**

| # | Задача | DoD | Статус |
|---|--------|-----|--------|
| AP-6.1 | Stripe products/prices (pro/team/studio + metered overage) | SAAS §9 | [ ] |
| AP-6.2 | Checkout + Customer Portal | `saas/billing.py` | [ ] |
| AP-6.3 | Webhooks (subscription lifecycle, grace) | signature verify | [ ] |
| AP-6.4 | Tab **Billing** у консолі (plan badge, usage bar, upgrade) | `platform.html` | [ ] |

> Self-hosted (`SAAS_MODE=false`) **не** вмикає білінг — Стовп A повністю юзабельний без нього.

**Вихід AP-6:** cloud-інстанс монетизується; self-hosted лишається безкоштовним.

---

## 4. `/v1` surface (ціль)

```
POST /v1/chat/completions     ✅ (AP-0)        — chat, stream
POST /v1/embeddings           ✅ (AP-2.1)      — nomic-embed-text
POST /v1/responses            ⏳ (AP-2.2)      — агентний, tool-use
GET  /v1/models               ✅→⏳ (AP-2.3)   — реальний каталог
GET  /v1/usage                ⏳ (AP-2.4)      — per-key метеринг
POST /v1/jobs · GET /v1/jobs/{id}  ⏳ (AP-2.5) — async (research/team/coding)
```

Auth: `Authorization: Bearer sk-jarvis-…` → org/scopes derive. Self-hosted: глобальний ключ як fallback.

---

## 5. KPI

| KPI | Ціль | Як міряти |
|-----|------|-----------|
| OpenAI SDK drop-in (chat/embeddings/models) | 100% незмінно | інтеграційні тести |
| Час signup → перший виклик | < 5 хв | ручне QA quickstart |
| Cross-tenant витоки | 0 | tenant-isolation тести (SAAS §11) |
| Ключ у логах | 0 | grep audit |
| Per-key usage точність | 100% | звірка usage_events vs metrics |

---

## 6. Свідомо не робимо

- **Публічний `/v1` без AP-1.0 IDOR fix** — блокер безпеки.
- **Зберігати сирий ключ** — лише prefix+hash, показ один раз.
- **Білінг у self-hosted** — `SAAS_MODE=false` ніколи не вимагає оплати.
- **403 на cross-tenant** — завжди 404 (не розкривати існування).
- **Зовнішній LLM за `/v1` дефолт** — локальний inference; cloud-pool лише cloud-edition.

---

## 7. Залежності

| Залежність | Звідки |
|------------|--------|
| Tenant context, keys, usage_events, billing | [`SAAS_DEEP_DIVE.md`](SAAS_DEEP_DIVE.md) PR#0…#7 |
| Console-таби (keys/usage/playground/billing) | [`PLATFORM_ROADMAP.md`](PLATFORM_ROADMAP.md) + `platform.html` |
| `/v1/responses` агентний | `AgentRunner` (Стовп B) |
| Async jobs | bg_jobs / teams / research (PLATFORM P2/P4/P9) |

---

## 8. Історія оновлень

| Дата | Версія | Зміна |
|------|--------|-------|
| 2026-06-15 | 1.0 | Початковий roadmap Стовпа A (AP-0…AP-6); продуктовий шар над SAAS_DEEP_DIVE |
| 2026-06-16 | 1.1 | AP-2.1 `/v1/embeddings` (gateway → memory nomic-embed-text, OpenAI-формат) |

---

*Оновлюйте чекбокси при закритті задач. Принципи: [`AGENTS.md`](../AGENTS.md) · Impl: [`SAAS_DEEP_DIVE.md`](SAAS_DEEP_DIVE.md)*
