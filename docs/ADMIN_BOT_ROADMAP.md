# JARVIS — Admin Bot Roadmap (бот як ендпоінт адміна)

> **Версія:** 1.0 (2026-06-16)
> **Статус:** Living document.
> **Мета:** перетворити Telegram-бота з тонкого набору адмін-команд на **єдину точку
> керування всім JARVIS** — спостережність, операції, керування доступом, алерти й аудит —
> із чату, з тими ж гарантіями (confirm-tier, audit-trail), що й Computer Use.

**Пов'язані документи**

| Документ | Роль |
|----------|------|
| [`AGENTS.md`](../AGENTS.md) | Конституція — принципи безпеки (S-серія), admin-gating |
| [`docs/PRODUCT_ROADMAP.md`](PRODUCT_ROADMAP.md) | Парасолька — Стовп C (Multi-platform), Telegram-клієнт |
| [`docs/PLATFORM_ROADMAP.md`](PLATFORM_ROADMAP.md) | HTTP admin panel `/admin/api/*`, Platform-консоль — паритет verbs |
| [`docs/AGENT_MODE_ROADMAP.md`](AGENT_MODE_ROADMAP.md) | Confirm-tier, session-trust, `computer.jsonl` audit — патерн для адмін-дій |
| [`docs/SAAS_DEEP_DIVE.md`](SAAS_DEEP_DIVE.md) | RequestContext (org/role) — основа для user-management v2 |
| [`docs/THREAT_MODEL.md`](THREAT_MODEL.md) | Модель загроз для адмін-каналу |

---

## 1. Позиціонування

### 1.1 Що означає «бот як ендпоінт адміна»

Адмін має керувати всім стеком (gateway, tools, memory, tts, twin, postgres, redis, ollama,
host-agent) **не відкриваючи SSH/Docker/Portainer**, а з Telegram — звідусіль, з телефону.
Бот — це не «ще кілька команд», а **операційний пульт**: бачу стан → отримую алерт про збій →
вживаю дію (рестарт/підміна моделі/скид кешу) → дія підтверджена й залогована.

### 1.2 North Star (admin-контур)

> Push о 03:14: «🔴 ollama OOM на vision-моделі, 3 fail за 2 хв». Адмін із телефону: `/admin status`
> (бачить tools degraded), `/admin logs tools 30` (читає трасу), `/admin model vision qwen2.5vl:3b`
> (підміна на легшу) → confirm → ✅ → `/admin audit 5` (бачить, що дію залоговано). Без ноутбука.

### 1.3 Принципи (незмінні)

- **Read — без confirm, mutate — з confirm, destructive — confirm + typed-token** (risk-tier, як Computer Use).
- **Кожна адмін-дія — в audit-trail** (`admin_audit.jsonl`): хто/що/коли/результат/код.
- **Паритет verbs** між ботом, `/admin/api/*` (web) і майбутнім CLI — одна логіка, три транспорти.
- **Admin-gating централізований** через `is_admin()` (`gateway/app/auth.py:90`), ніколи не дублюється ad-hoc.
- **Жодних незворотних дій із бота без typed-token** (напр. `/admin svc stop` вимагає ввести ім'я сервісу).

---

## 2. Baseline (стан на 2026-06-16)

### 2.1 Реалізовано

| Компонент | Файл |
|-----------|------|
| `/admin` меню (Mini App + inline) | `gateway/app/bot/admin.py:140` |
| `/admin mode X` / `reset` / `rl USER_ID` з confirm | `gateway/app/bot/admin.py:165-189` |
| Confirm-flow (6-hex код, Redis TTL 300s, inline + `/confirm`) | `gateway/app/bot/admin.py:34-110` |
| `/allow`, `/pending` — керування доступом | `gateway/app/bot/commands.py`, `access_store.py` |
| HTTP admin panel (`/admin/api/mode|access|ratelimit|computer`) | `gateway/app/admin_panel.py:229+` |
| Platform-консоль (`/platform/api/*`) | `gateway/app/platform/router.py:33` |
| Admin-gating (`is_admin`, `ADMIN_USER_IDS` + fallback) | `gateway/app/auth.py:90`, `config.py:148` |
| Computer confirm як HTTP-ендпоінт (патерн) | `tools/app/routes/computer.py`, `computer_confirm.py` |

### 2.2 Оцінка зрілості (чесно)

| Критерій | Оцінка | Коментар |
|----------|--------|----------|
| Спостережність із бота | **2/10** | `/status` лише Ollama/Twin; нема агрегованого health усіх сервісів, logs, metrics |
| Проактивні алерти | **0/10** | бот ніколи сам не пише адміну про збій |
| Операційні дієслова | **3/10** | лише mode/rl; нема restart/reload/model-swap/reindex/cache/flags |
| Керування юзерами | **4/10** | allow/deny/revoke є; нема list/quota/role/per-user-mode |
| Аудит адмін-дій | **1/10** | confirm є, але дії не пишуться в окремий audit-trail; не запитуються з бота |
| Безпека адмін-каналу | **5/10** | confirm-код + TTL є; нема risk-tier, typed-token, rate-limit на адмін-команди |
| Структура команд | **3/10** | ad-hoc `parts[]`-парсинг у `admin.py`; нема декларативного реєстру/help |

### 2.3 Розриви (gap list)

| # | Gap | Вплив |
|---|-----|-------|
| AB-G1 | Нема агрегованого health/logs/metrics усіх сервісів із бота | Адмін не бачить стан без Docker/SSH |
| AB-G2 | Бот не пушить алерти про збої | Інциденти помічають пізно (вручну) |
| AB-G3 | Нема операційних verbs (restart/reload/model/reindex/cache/flag) | Будь-яка операція — поза ботом |
| AB-G4 | User-management тонкий (нема list/quota/role) | Масштабування доступу ручне |
| AB-G5 | Адмін-дії не в audit-trail, не запитувані | Немає підзвітності/розслідування |
| AB-G6 | Нема risk-tier/typed-token/rate-limit для адмін-дій | Один код для всього, ризик для destructive |
| AB-G7 | Ad-hoc парсинг команд, нема help/реєстру | Кожна нова verb — копіпаст; крихко |

---

## 3. Фази розвитку (AB-0…AB-6)

```
AB-0 (baseline ✅) ─► AB-1 (observability) ─► AB-2 (alerts/push)
                              │                      │
                              ▼                      ▼
                    AB-3 (ops verbs) ─► AB-4 (users v2) ─► AB-5 (audit) ─► AB-6 (framework/security)
                                                                                  │
                                                                                  ▼
                                                                        AB-7 (CLI/HTTP parity, опц.)
```

---

## AB-0 — Baseline · ✅ **done**

| # | Задача | Статус |
|---|--------|--------|
| AB-0.1 | `/admin` меню + Mini App + inline confirm | [x] |
| AB-0.2 | `/admin mode|reset|rl` з 6-hex confirm-кодом (Redis TTL) | [x] |
| AB-0.3 | `/allow` + `/pending` access-management | [x] |
| AB-0.4 | HTTP admin panel `/admin/api/*` | [x] |

**Вихід:** із бота можна змінити режим/rl і погодити доступ. Це **тонкий пульт**, не операційний.

---

## AB-1 — Observability з бота · **наступний спринт (1–2 тижні)**

**Мета:** один екран — увесь стан стека з Telegram.

| # | Задача | DoD | Пріоритет | Статус |
|---|--------|-----|-----------|--------|
| AB-1.1 | `/admin status` — агрегований health усіх сервісів (gateway/tools/memory/tts/twin/postgres/redis/ollama/host-agent) | Один меседж: 🟢/🟡/🔴 + latency | P0 | [ ] |
| AB-1.2 | Reuse `/admin/api/overview` + `/admin/api/health` як джерело (не дублювати збір) | Бот = тонкий рендер JSON | P0 | [ ] |
| AB-1.3 | `/admin logs <service> [N]` — tail останніх N рядків / останні помилки | Default N=20, ліміт 100, escape HTML | P1 | [ ] |
| AB-1.4 | `/admin metrics` — req/min, rate-limit hits, активні сесії, глибина черг bg-jobs | Структуровано, з Redis/лічильників | P1 | [ ] |
| AB-1.5 | Inline-кнопки на `status` (🔄 refresh, → logs degraded-сервісу) | Callback без повторної команди | P2 | [ ] |

**Вихід AB-1:** `/admin status` → бачу що `tools` degraded → тапаю «logs» → читаю трасу. Без Docker.

---

## AB-2 — Проактивні алерти (push) · **2–3 тижні**

**Мета:** бот сам пише адміну, коли щось ламається.

| # | Задача | DoD | Статус |
|---|--------|-----|--------|
| AB-2.1 | Watchdog-петля в gateway: health-poll сервісів кожні N сек | Конфіг `ADMIN_WATCHDOG_INTERVAL` | [ ] |
| AB-2.2 | Тригери: service-down, error-rate spike, ollama OOM/timeout, VRAM/disk threshold | Поріг у config | [ ] |
| AB-2.3 | Push у `ADMIN_USER_IDS` через `TelegramClient.send_message` з severity (🟡/🔴) | Reuse наявного push-каналу | [ ] |
| AB-2.4 | Dedup + cooldown (не спамити тим самим алертом) | Redis-ключ per-alert + TTL | [ ] |
| AB-2.5 | Quiet-hours + `/admin alerts on|off|mute 1h` | Per-admin налаштування | [ ] |
| AB-2.6 | Recovery-нотифікація (🟢 «tools відновлено») | Парний до 2.2 | [ ] |

**Вихід AB-2:** падіння сервісу о 03:00 → адмін отримує 🔴-пуш із сервісом і причиною за <N сек.

---

## AB-3 — Операційні дієслова · **3–4 тижні**

**Мета:** не лише дивитись — діяти. Усі mutate → confirm-tier, усі → audit (AB-5).

| # | Задача | DoD | Статус |
|---|--------|-----|--------|
| AB-3.1 | `/admin svc restart|reload <service>` через host-agent/docker | Confirm-tier, typed-token для restart | [ ] |
| AB-3.2 | `/admin model <chat|agent|vision> <name>` — гаряча підміна Ollama-моделі | Reuse twin/ModelRegistry, confirm | [ ] |
| AB-3.3 | `/admin reindex <project_id|all>` — тригер scoped-RAG переіндексації | Reuse `POST /projects/{id}/reindex` (CA-2.4) | [ ] |
| AB-3.4 | `/admin cache clear <rl|session|rag>` — точковий скид | Confirm, без зачіпання чужих ключів | [ ] |
| AB-3.5 | `/admin flag <NAME> on|off` — рантайм-тогл whitelisted feature-flags | Лише безпечна підмножина (`ENABLE_*`), Redis-override | [ ] |
| AB-3.6 | Усі verbs повертають структурований результат + лог-рядок | Уніфікований формат відповіді | [ ] |

**Вихід AB-3:** `/admin model vision qwen2.5vl:3b` → confirm → ✅ підміна на льоту, без редагування `.env` + рестарту.

---

## AB-4 — Керування юзерами v2 · **3–5 тижнів**

**Мета:** повноцінний user-management із бота, готовий до multi-tenant.

| # | Задача | DoD | Статус |
|---|--------|-----|--------|
| AB-4.1 | `/admin users` — список approved + pending + last-seen + поточний режим | Пагінація inline | [ ] |
| AB-4.2 | `/admin user <id>` — картка: mode, rl-стан, quota, роль, історія | Reuse `access_store` + лічильники | [ ] |
| AB-4.3 | Set quota / per-user mode / роль із бота (confirm) | Запис у `access_store`/context | [ ] |
| AB-4.4 | Прив'язка до `RequestContext` (org/role) із SAAS PR | Готовність до org-scoped адмінів | [ ] |
| AB-4.5 | `/admin block <id>` / `unblock` — м'який бан (окремо від revoke) | Стан у access-store | [ ] |

**Вихід AB-4:** `/admin user 42` → бачу хто, скільки запитів, який режим → ставлю quota → confirm.

---

## AB-5 — Аудит адмін-дій · **2–3 тижні** (паралельно з AB-3)

**Мета:** кожна адмін-дія підзвітна й розслідувана.

| # | Задача | DoD | Статус |
|---|--------|-----|--------|
| AB-5.1 | `admin_audit.jsonl` — append {ts, admin_id, verb, args, result, confirm_code, transport} | Як `computer.jsonl` | [ ] |
| AB-5.2 | Хук у `execute_action` + усіх AB-3 verbs — пише запис | Один decorator/wrapper | [ ] |
| AB-5.3 | `/admin audit [N]` — останні N дій із бота | Default 10, escape | [ ] |
| AB-5.4 | Surface у Platform-консолі (read-only таблиця) | Reuse logs-router | [ ] |
| AB-5.5 | Прив'язка до THREAT_MODEL (хто може читати audit) | Лише адмін | [ ] |

**Вихід AB-5:** будь-яку адмін-дію видно: хто, коли, що, з яким результатом — із бота й web.

---

## AB-6 — Command-framework + хардненг безпеки · **3–4 тижні**

**Мета:** прибрати ad-hoc парсинг, ввести risk-tier і паритет verbs.

| # | Задача | DoD | Статус |
|---|--------|-----|--------|
| AB-6.1 | Декларативний реєстр admin-verbs: `{verb, args, risk_tier, handler, help}` | Заміна `parts[]`-ланцюга в `admin.py` | [ ] |
| AB-6.2 | Risk-tiers: `read`(no confirm) / `write`(confirm) / `destructive`(confirm + typed-token) | Уніфіковано для всіх verbs | [ ] |
| AB-6.3 | `/admin help` — автогенерований з реєстру | Завжди актуальний | [ ] |
| AB-6.4 | Admin session-trust (як computer) — батч read/low-risk без повтор-confirm | Redis TTL, opt-in | [ ] |
| AB-6.5 | Rate-limit на адмін-команди (анти-fat-finger / анти-abuse) | Окремий ліміт від user-rl | [ ] |
| AB-6.6 | Спільний executor: бот / `/admin/api` / CLI кличуть один шар verbs | DRY, один audit-хук | [ ] |

**Вихід AB-6:** нова адмін-команда = один запис у реєстрі (verb+tier+handler); help і audit «безкоштовно».

---

## AB-7 — CLI / HTTP parity · **опційно, після AB-6**

**Мета:** ті самі дії з терміналу/скрипта, не лише з Telegram.

| # | Задача | DoD | Статус |
|---|--------|-----|--------|
| AB-7.1 | `jarvis admin <verb> ...` CLI поверх `/admin/api` | Token-auth (`JARVIS_ADMIN_TOKEN`) | [ ] |
| AB-7.2 | Headless ops для скриптів/cron (напр. нічний reindex) | Policy-gate, без інтерактиву | [ ] |
| AB-7.3 | Webhook-out для алертів (Slack/email опц.), не лише Telegram | Reuse AB-2 тригерів | [ ] |

---

## 4. KPI

| KPI | Baseline (2026-06) | Ціль AB-3 | Ціль AB-6 | Як міряти |
|-----|--------------------|-----------|-----------|-----------|
| Час до виявлення інциденту | ручний (∞) | <60 c (push) | <30 c | від збою до алерту |
| Операцій доступних із бота | ~3 | ~10 | ~15 | чеклист verbs |
| Адмін-дій у audit-trail | 0% | 80% | 100% | `admin_audit.jsonl` покриття |
| MTTR (рестарт/підміна моделі) | хвилини+SSH | <60 c з бота | <30 c | заміри |
| Destructive-дій без typed-token | можливо | 0 | 0 | audit |
| Паритет verbs бот↔web↔CLI | ~50% | — | >90% | чеклист |

---

## 5. Свідомо не робимо

- **Прямий shell-доступ із бота** (`/admin exec <будь-що>`) — лише whitelisted verbs (S-серія AGENTS.md).
- **Незворотні дії без typed-token** (stop сервісу, drop даних, revoke org).
- **Дублювання admin-gating** — лише через `is_admin()`; жодних локальних id-перевірок.
- **Окремий збір health у боті** — бот рендерить `/admin/api/*`, не паралельний моніторинг.
- **Зовнішні алерт-канали за дефолт** — Telegram-push первинний; Slack/email лише opt-in (AB-7.3).

---

## 6. Залежності та ризики

| Ризик | Мітигація |
|-------|-----------|
| Restart/stop сервісу з телефону «зламає» прод | typed-token, confirm-tier, recovery-push (AB-2.6) |
| Алерт-спам у збійному стані | dedup + cooldown (AB-2.4), severity-фільтр |
| Підміна моделі на льоту → OOM | перевірка VRAM перед swap, fallback на легшу |
| Розповзання ad-hoc verbs | реєстр + спільний executor (AB-6.1/6.6) до масштабування |
| Audit-файл росте | ротація як у `computer.jsonl`, ліміт читання з бота |

---

## 7. Мапінг на існуючі roadmap-и

| Цей документ | Будівельний блок | Звідки |
|--------------|------------------|--------|
| AB-1 observability | `/admin/api/overview|health` | PLATFORM (admin panel) |
| AB-2 alerts | push-канал `TelegramClient`, reminders | Gateway / Стовп C |
| AB-3 ops verbs | host-agent, ModelRegistry, reindex | AGENT_MODE / CA-2.4 / Twin |
| AB-4 users v2 | `access_store`, RequestContext | PLATFORM P8/P9 / SAAS PR#1 |
| AB-5 audit | `computer.jsonl` патерн | AGENT_MODE / Computer Use |
| AB-6 framework | confirm-tier, session-trust | AGENT_MODE / THREAT_MODEL |
| AB-7 CLI/HTTP | `/admin/api`, token-auth | API_PLATFORM |

---

## 8. Історія оновлень

| Дата | Версія | Зміна |
|------|--------|-------|
| 2026-06-16 | 1.0 | Початковий roadmap admin-контуру (AB-0…AB-7) після аудиту наявної admin-поверхні |

---

*Оновлюйте чекбокси при закритті задач. Принципи: [`AGENTS.md`](../AGENTS.md) · Парасолька: [`PRODUCT_ROADMAP.md`](PRODUCT_ROADMAP.md)*
