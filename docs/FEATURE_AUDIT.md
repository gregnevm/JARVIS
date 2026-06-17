# FEATURE_AUDIT.md — чесний аудит роботоздатності фіч JARVIS

> **Дата:** 2026-06-17 · **Гілка:** `claude/saas-ecosystem-architecture-fqr650`
> **Метод:** статичне читання реалізації (НЕ довіра тестам — більшість мокає LLM/БД/Telegram)
> + прогін усіх тест-сьютів і mypy + 5 паралельних deep-аудитів по сервісах.
> **Призначення:** одне місце, де чесно записано «що реально працює end-to-end, що
> скаффолд, що дрейф». Робочий список фіксів — у §Робочий план (чекбокси).

---

## 0. Baseline (об'єктивні сигнали)

| Сервіс | pytest | mypy (strict) |
|--------|--------|---------------|
| jarvis_core | **84 passed** | ✅ clean (30 files) |
| gateway | **370 passed, 2 skipped** | ✅ clean (95 files) |
| memory | **72 passed** | ✅ clean (9 files) |
| tools | **401 passed** | ✅ clean (90 files) |
| twin | **41 passed** | ✅ clean (8 files) |
| hostagent | **77 passed, 6 skipped** | ✅ clean (4 files) |
| **Разом** | **1045 passed, 8 skipped, 0 failed** | ✅ |

`docker compose config` — валідний. 0 TODO/FIXME, 0 NotImplementedError у проді.
**Висновок:** фундамент дисциплінований і міцний. Дефекти — не в «гнилі», а у
(1) небезпечних дефолтах, (2) caller-trusted identity (IDOR-вектори під майбутній SaaS),
(3) точковому мертвому коді / дрейфі доку.

---

## 1. P0 — Security / Broken (виправляємо першими)

| # | Файл:рядок | Проблема | Фікс |
|---|-----------|----------|------|
| P0-1 | `gateway/app/config.py:69` | `webapp_dev_open=True` дефолт → Mini App `/app/*` без `initData` повертає uid 0 (auth bypass). Порушує AGENTS §5 «дефолт безпечний». | Дефолт `False`; refuse коли заданий `public_app_url`. |
| P0-2 | `gateway/app/webapp.py:250,294` | uid=0 sentinel: `app_trust`/`app_run_macro` без admin-guard → неавтентифіковані privileged-дії при dev-open. | uid 0 = unauthorized для privileged; або реальний admin-id. |
| P0-3 | `gateway/app/platform/proxy.py:100` + `platform/auth.py:33` | `resolve_uid` повертає caller-supplied `user_id` без role-check → platform-admin читає чужі jobs/memory/notes (IDOR). | Gate cross-uid за explicit admin/role (`RequestContext.role`). |
| P0-4 | `gateway/app/openai_api.py:45-63` | `/v1` user-id повністю caller-controlled (header/body) під 1 глобальним ключем → impersonation будь-якого юзера. | Bind key→allowed uid; інакше force `openai_default_user_id`. |
| P0-5 | `gateway/app/openai_api.py:100-160` | `/v1` без rate-limit і без usage-обліку → DoS/cost-діра (кожен виклик = дорогий agent-turn). | Застосувати `app.state.limiter`; per-key лічильники. |
| P0-6 | `tools/app/tools/coding_tools.py:41-45` | `_cli` б'є host-agent `/cli` напряму → оминає CLI-whitelist І `computer.jsonl` audit (суперечить AGENTS §5 tier-logging). | Маршрутизувати read-only coding-tools через audited-шлях (`log_action`). |
| P0-7 | `tools/app/computer_audit.py:18-50` | `_safe_args` лише трункейтить — НЕ редактить секрети; PS-скрипти/CLI-args з токенами лягають у `computer.jsonl` cleartext. | `default_redactor()` перед записом args/result. |

---

## 2. P1 — Реальні діри

| # | Файл:рядок | Проблема | Фікс |
|---|-----------|----------|------|
| P1-1 | `gateway/app/bot/commands.py:35` | Мертві команди `/plan` `/improve` `/login` — мають робочі гілки, але відсутні в `COMMANDS` → падають у LLM. `/plan` рекламується в help. | Додати в `COMMANDS`. |
| P1-2 | `hostagent/app/main.py:879-885` | `/window/focus` — НЕ f-string: `\n`/`{{t}}`/`${{t}}` лишаються літералами → PS не компілюється. Поруч робочий `/uia/invoke` (908-915). | Переписати за патерном `/uia/invoke`. |
| P1-3 | `tools/app/precommit_gate.py:21` | `_EDIT_TOOLS` містить мертвий `"rename_symbol"` (не tool-name, а mode). | Прибрати dead-entry. |
| P1-4 | `gateway/app/ratelimit.py:30` | RL-ключ `rl:{user_id}:{window}` без org-префіксу (AGENTS §5). | `jarvis:{org_id}:rl:{user_id}:{window}`. |
| P1-5 | `memory/app/db.py:403-557` | Context-запити скоупляться лише `user_id`; `org_id` write-only (latent cross-tenant leak під SaaS). | `AND org_id=$N` у read/write-предикатах. |
| P1-6 | `memory/app/migrate.py:39-48` | `embed_dim_mismatch` порівнює два hardcoded-768 → структурно недосяжний; реальний column-dim/live-model ніколи не звіряється. | Звіряти з `len(embed("probe"))` та/або `pg_attribute` typmod. |
| P1-7 | `twin/app/main.py:72-77` | `/ingest/logs` ігнорує `delta_start_idx` → дублі при reset edge-state / спільному `edge_id`. | Honor `delta_start_idx` server-side. |
| P1-8 | `gateway/app/platform/auth.py:59` | `platform_password` тихо фолбекає на `admin_panel_password` (privilege surprise для високо-привілейованого `/platform`). | Вимагати `PLATFORM_PASSWORD` явно або warn. |
| P1-9 | `.env.example` (twin keys) | `TWIN_DATA_DIR`/`TWIN_REGISTRY_DB`/`TWIN_MIN_EVAL_PROMOTE` — dead (twin Settings без `env_prefix`, читає `DATA_DIR`/`REGISTRY_DB`/`MIN_EVAL_PROMOTE`). | `env_prefix="TWIN_"` у twin config АБО виправити ключі. |
| P1-10 | `.env.example` / ENV_CHECKLIST | Прапори, що код читає, але відсутні: `CODING_FIX_MAX_ROUNDS`, `CODING_REVIEW_AFTER_FIX`, `HOSTAGENT_EDIT_BATCH_MAX`, `CODE_EXEC_TIMEOUT`, `OLLAMA_FAIL_THRESHOLD`/`_COOLDOWN`, push-ключі тощо (D1-порушення). | Додати в `.env.example` + checklist. |
| P1-11 | docs (mobile track) | `CLIENTS_ROADMAP`/`AGENTS.md` кажуть «mobile ❌ / 0/10» — а є підписаний APK v1.0.0 (20 Java, chat/voice/push/pairing). Доки **недо-задекларовують**. | Синхронізувати CL-3 + AGENTS Стовп-C. |

---

## 3. P2 — Дрейф / поліш / архітектурний борг

| # | Місце | Нота |
|---|-------|------|
| P2-1 | `jarvis_core/context.py:40` `to_headers()`/`from_headers()` | Мертвий код: 0 прод-консюмерів (тільки тести). PR#4 «X-JARVIS-* propagation» НЕ підключений — `tools_request` шле лише `X-Request-ID`; user_id йде в JSON-body. → Або підключити, або відмітити PR#4 як not-done. |
| P2-2 | `memory/app/main.py:119` `/store` | «Naked» rows (без kind/summary/tags). Це **scope-неузгодженість**, не баг: C1-паспорт стосується `context_events`, raw-RAG — субстрат під ним. Форсувати summary на кожен меседж = LLM-виклик на меседж (ламає P6). → Уточнити C1-scope в AGENTS.md. |
| P2-3 | `jarvis_core/passport/tags.py` (P10 addressing) | Tag-as-handle («виклик `module:scam-shield`») — 0 резолверів у коді, лише index-роль. → Реалізувати dispatch або знизити claim. |
| P2-4 | `memory` redaction | `default_redactor()` імпортнутий, але не викликається в `/context/ingest`. → Застосувати на summary/payload. |
| P2-5 | `edge/rag.py` + AGENTS:134 | «SQLite-vec» — дрейф: насправді pure-Python cosine/keyword full-scan (cap 5000), дефолт = keyword. → Виправити доку або інтегрувати sqlite-vec. |
| P2-6 | `gateway/app/openai_api.py:152` | `/v1/models` hardcoded (не з ModelRegistry, P7); `/v1/embeddings`/`/v1/responses` відсутні (коректно `[ ]` в roadmap). |
| P2-7 | `gateway/app/streaming.py:99` | Порожній стрім → повний re-run agent-turn (дубль side-effects). → Розрізняти transport-fail vs legit-empty. |
| P2-8 | docs paths | `tools/app/toolkit.py`→пакет; `tools/main.py`→`tools/app/main.py`; `gateway/config.py`→`gateway/app/config.py`; відсутній `memory/project_jarvis.md`; міграція `003_saas_tenant`→`004` (колізія з `003_context_passports`). |
| P2-9 | ENV_CHECKLIST | `REMINDER_POLL_SECONDS` 5→20; `COMPUTER_PROFILE` приклад "standard"→дефолт "safe". |

---

## 4. Свідомо НЕ чіпаємо у цьому проході (потребує рішення власника / окремий трек)

- **Native fix-loop → conversational agent.** `fix_tests`/`code_plan`/`code_review` реальні, але викликаються лише з REST/CLI/Platform/bg-job — НЕ з NL-loop у Telegram. Headline-UX «у репо падає тест — розберись» наразі не зашитий у `classify_mode`. → Великий трек CA, окреме рішення.
- **`code_exec` sandbox.** `subprocess -I` ≠ sandbox (AGENTS §6 сам це визнає). Дефолт `enable_code_exec=False` — єдиний захист. → Потрібен реальний sandbox (firejail/nsjail) перед увімкненням.
- **SaaS JWT membership.** `issue_access` self-asserts owner/studio/default_org — чесний single-tenant MVP. → Реальний membership-resolve коли SaaS-mode живий (SAAS_DEEP_DIVE PR#5).
- **Ship APK артефакт.** `/apk` коректний, але `.apk` не в репо. → Потрібен прогін `mobile/build-apk.ps1`.
- **hostagent server-side allowlist.** `/powershell`/`/cli` захищені лише токеном; whitelist+HITL у tools-шарі. → Defense-in-depth: дублювати guard на hostagent-боці.

---

## 5. Робочий план (працюємо по списку, batch-ами, звіт після кожного)

### Batch 1 — Security-дефолти + швидкі баги (P0/P1, без ambiguity) ✅
- [x] P0-7 computer.jsonl secret redaction (+ розширено редактор: sk-jarvis-*, Bearer, key=value)
- [x] P0-6 coding_tools `_cli` → audited path (log_action T1 у computer.jsonl)
- [x] P0-1 webapp_dev_open → False (+ .env.example, безпечний дефолт)
- [x] P0-2 uid=0 guards на app_set_mode/app_trust/app_run_macro (`_require_identified`)
- [x] P1-2 /window/focus malformed PS (переписано за патерном /uia/invoke)
- [x] P1-3 precommit_gate dead entry прибрано
- [x] P1-1 dead commands /plan /improve /login → у COMMANDS

### Batch 2 — Multi-tenant ground-work (AGENTS §5) ✅ (частково)
- [x] P1-4 ratelimit org-prefix (`jarvis:{org_id}:rl:...` через redis_key)
- [~] P1-5 memory context org_id scoping — **відкладено**: 0 поточного впливу (синтетична
  org), належить треку team-ecosystem (owner→policy scope). Форсувати зараз = P6/YAGNI.
- [~] P2-1 PR#4 headers — **доковий фікс у Batch 5** (код шле user_id у body; to_headers() мертвий → позначити not-done чесно)
- [x] P0-3 platform resolve_uid role-guard (cross-uid лише адміну; load-bearing під SaaS)

### Batch 3 — Correctness ✅
- [x] P1-6 memory embed_dim guard — додано перевірку РЕАЛЬНОЇ розмірності pgvector-колонки
- [x] P1-7 twin /ingest/logs delta_start_idx (дедуп re-push)
- [x] P2-4 memory redactor on ingest (summary+payload backstop)

### Batch 4 — /v1 hardening ✅
- [x] P0-5 /v1 rate-limit (429 на той самий лічильник, що Telegram)
- [x] P0-4 /v1 user-id binding (caller uid лише з allowed_ids — anti-impersonation)

### Batch 5 — Doc-sync (D1) ✅
- [x] P1-11 mobile track sync (AGENTS.md Стовп-C + CLIENTS_ROADMAP CL-3.2/3.4/3.6/3.8 + maturity 7/10)
- [x] P1-9 twin env keys (validation_alias TWIN_DATA_DIR/REGISTRY_DB/MIN_EVAL_PROMOTE — тепер ЖИВІ)
- [x] P1-10 missing env flags (15 прапорів додано в .env.example: coding/research/subagent/ollama/push/hooks)
- [x] P2-1 PR#4 headers — позначено НЕ підключеним (context.py docstring)
- [x] P2-5 sqlite-vec drift (AGENTS.md: SQLite + in-Python cosine/keyword, НЕ sqlite-vec)
- [x] P2-8 doc paths (toolkit.py→пакет, tools/main.py, gateway/config.py, broken ref, міграція 003→004)
- [x] P2-9 ENV_CHECKLIST (REMINDER_POLL 5→20, COMPUTER_PROFILE standard→safe)
- [x] P2-2/3 C1-scope clarify (паспорт=context_events, raw-RAG=субстрат) + P10 addressing→«заплановано»
- [x] PRODUCT_ROADMAP CA-5/CA-6 синхронізовано з треком (done)

---

## 6. Підсумок проходу

**Зроблено:** 5 батчів, ~24 пункти. Baseline тестів: 1045 → **1055 passed** (+10 регресій),
mypy strict чистий усіх 6 сервісів, compose валідний. Кожен фікс має регресійний тест.

**Свідомо відкладено** (нульовий поточний вплив / належить окремому треку — §4):
- P1-5 memory org_id read-scoping → трек team-ecosystem (owner→policy scope).
- Native fix-loop → conversational agent (великий CA-трек).
- code_exec реальний sandbox; SaaS JWT membership; ship APK артефакт; hostagent server-side allowlist.

---

*Оновлюй чекбокси в цьому файлі в тому ж PR, що й фікс (D1).*
