# AO-CTX — Пам'ять у 3 рівні: pinned-блоки + sleep-time консолідація

> **Статус:** PROPOSAL (design-first; імплементація — окремий PR після Go).
> **Джерело:** пункт №3 шортлиста [`COMPETITIVE_ANALYSIS.md`](../COMPETITIVE_ANALYSIS.md) §3.3
> (Letta MemFS/sleep-time, Mem0 salience extraction, LongMemEval).
> **Стосунок до наявного:** еволюція «Context GC v2» ([`ARCHITECTURE_OPTIMIZATION_PLAN.md`](../ARCHITECTURE_OPTIMIZATION_PLAN.md) AO-2)
> поверх конвеєра [`CONTEXT_MODULE.md`](../CONTEXT_MODULE.md); НЕ переписування. P7: цей док — SSOT дизайну tier-ів.

## 1. Проблема

`context_events` — один плаский шар: паспорти пишуться і дістаються semantic+tags+time,
але (а) стабільні факти про оператора (стиль, контрагенти, правила бізнесу) щоразу
конкурують за retrieval-топ з ефемерними подіями; (б) сирі події не дистилюються — знання
залишається розмазаним по сотнях паспортів; (в) немає «завжди в контексті» шару — агент
перечитує те, що мало б бути закріпленим.

Поле 2026 зійшлося на 3 рівнях (Letta, Mem0, Leon, QwenPaw/ReMe): **pinned working
context** / **verbatim archive** / **distilled knowledge**.

## 2. Мапа на наш стек (мінімальний дельта-дизайн)

| Tier | Що | Де в нас | Дельта |
|---|---|---|---|
| **T1 pinned** | 5–15 коротких блоків, ЗАВЖДИ в промпті (профіль оператора, бізнес-правила, активні цілі) | нема (найближче — `user_profile.py` prompt-block) | нова таблиця `context_pins` (block_id, title, body ≤1k, updated_at, source_passport_ids) + InputDecorator інжектить усі pins |
| **T2 archive** | дослівні паспорти подій | `context_events` — **вже є** | без змін (він і є архів) |
| **T3 distilled** | салієнтні факти, витягнуті з пачок T2 (Mem0-паттерн: «факт», не транскрипт) | частково: паспорти вже мають summary | `kind=distilled` у `context_events` (без нової таблиці; тег-неймспейс `distilled:*`) |

**Sleep-time консолідація** (Letta-паттерн, ~5x економія test-time compute): розширення
наявного bg-job `context_retention` — не новий механізм. Раз на добу (idle-вікно):
1. взяти нові T2-паспорти з останнього прогону (batch);
2. локальним Ollama витягти салієнтні факти → T3-паспорти (`kind=distilled`, з
   `source_passport_ids` — provenance обов'язковий);
3. запропонувати оновлення T1-pins **через human-gate** (S4: pins впливають на кожен
   промпт → зміна = confirm у Telegram, як computer-дії);
4. GC: T2 старші за retention без тегів-виключень — у cold storage/purge (це і був AO-2).

## 3. Guardrails дизайну

- **Без нового сервісу і без нової vector-БД** — pgvector лишається; T1 — маленька
  реляційна таблиця (embedding не потрібен: pins ідуть у промпт цілком).
- **Provenance fail-closed:** T3 без `source_passport_ids` не пишеться («голий» store = баг, C1).
- **Human-gate на T1** — sleep-time агент НЕ має права мовчки міняти те, що бачить
  кожен промпт (антиін'єкційна межа: скомпрометований паспорт не може самопідвищитись у pin).
- **Бюджет промпта:** сумарний розмір pins ≤ `CONTEXT_PINS_MAX_CHARS` (дефолт 2000);
  ліміт — у settings, fail-closed обрізання за пріоритетом блоків.
- Прапор `ENABLE_MEMORY_TIERS=false` (дефолт) до стабілізації.

## 4. Eval-якір (перед Go — виміряти, після — порівняти)

LongMemEval-подібний набір поверх наших даних (COMPETITIVE_ANALYSIS §3.7): ~15 питань
5 типів (recall / preference / knowledge-update / temporal / multi-session) у
`training/eval/task_scenarios.json` (категорія `memory`, live-стек). Go/NoGo фази 2:
tier-retrieval має бити плаский retrieval на цьому наборі, інакше зупиняємось на T3-дистиляції.

## 5. Фази (кожна — свій PR, свій roadmap-tick)

- **Ф1 (S):** ✅ `kind=distilled` + `build_distilled` (job `context_distill`) + provenance
  (`source_passport_ids` у payload, fail-closed) + retention 3650д. Без T1. Реалізовано:
  `jarvis_core/passport/jobs.py`, `tools/app/context_jobs.py`.
- **Ф2 (M):** `context_pins` + InputDecorator + human-gate оновлень + memory-eval набір. Go/NoGo по §4.
- **Ф3 (опц.):** MemFS-стиль дзеркало pins у markdown (git-історія змін пам'яті — дешевий
  аудит, Letta-паттерн) — лише якщо Ф2 доведе цінність.

## 6. Що свідомо НЕ робимо

- Не тягнемо Letta/Mem0 як залежності (guardrail проти framework-rewrite; паттерни — так, код — ні).
- Не «vector clock»/CRDT — синхронізація Edge↔Twin поза скоупом цього proposal.
- Не чіпаємо схему `context_events` (нове значення `kind` — не міграція структури).
