---
name: ai_tester
description: >-
  MCP-рушій автономного самотестування фіч платформи JARVIS. Тестує власними силами: генерує
  запити до client-API, симулює ендпоінти через ПАТЕРН ДЕКОРАТОР (підміна джерела даних
  фікстурою/збоєм без зміни бекенду), оцінює oracle-ом і за результатом запускає coder-MCP та
  Computer-Use-MCP у bounded-циклі test→fix→retest. Використовуй, коли користувач каже:
  "/ai_tester", "протестуй фічі", "самотест jarvis", "прожени self-test", "симулюй ендпоінт",
  "відтвори падіння", "тест-фікс луп", "автотест платформи", "перевір усі ендпоінти".
  Це ENGINE (Ports&Adapters): ядро generic, реєстр фіч JARVIS — в адаптері. S4: фікси лише
  диспатчаться, апрув мутацій — завжди людський. Не для CI-тестів репо (то pytest/kaizen).
---

# /ai_tester — рушій самотестування (engine + adapter + skill)

Робить із «прогнати всі фічі руками» один MCP-виклик. Та сама дисципліна, що в `erp_sa`/`jarvis`:
**engine (generic) + adapter (jarvis) + skill (роутер)**. Вимога «всі модулі — MCP» виконана
буквально: рушій сам є MCP-сервером, кожен порт = MCP-тул, а ремедіація бʼє в ті самі endpoint-и,
що стоять за `mcp__jarvis__code` / `mcp__jarvis__computer`.

> **Порти і статус:** [`engine/ports.md`](engine/ports.md). **Реєстр фіч:**
> [`adapters/jarvis/manifest.json`](adapters/jarvis/manifest.json). **Інсталяція:**
> [`references/install.md`](references/install.md).

## Маршрутизація інтентів

| Намір користувача | Дія |
|---|---|
| «підключи / встанови ai_tester» | проведи за [`references/install.md`](references/install.md) |
| «чи готовий тестер», «чому тести не їдуть» | tool **`ready`** (клич першим: gateway/auth/фічі) |
| «які фічі тестуються» | tool **`features`** |
| «протестуй все», «прожени самотест» | tool **`run`** `{}` (suite без mutating; звіт у артефакти) |
| «протестуй фічу X», «перевір chat» | tool **`run`** `{feature}` |
| «прожени офлайн/детерміновано» | tool **`run`** `{mode: "replay"}` (sim-фікстури, без мережі) |
| «онови фікстури з живого» | tool **`run`** `{mode: "record"}` |
| «симулюй ендпоінт», «підмінь відповідь», «відтвори падіння» | tool **`simulate`** `{feature, fault?, fixture_json?}` — декоратор підміняє джерело даних |
| «тест-фікс луп», «тестуй і чини по колу» | tool **`loop_run`** `{feature?, max_rounds?}` — лише mode `http`; **S4: зупиняється на awaiting_confirm** |
| «відправ фікс кодеру» | tool **`dispatch_fix`** `{feature, extra?}` — той самий важіль, що `mcp__jarvis__code` |
| «перевір UI/на ПК», «скріншот» | tool **`verify_ui`** `{text}` / **`screenshot`** — важіль `mcp__jarvis__computer` |
| «покажи звіт» | tool **`report`** |
| апрув/скасування дії, що очікує | `confirm_pending` → `confirm_approve {code}` / `confirm_cancel` |

> **S4 (залізно):** `loop_run`/`dispatch_fix`/`verify_ui` лише **диспатчать** ремедіацію. Мутуючий
> крок чекає людського `confirm_approve` — рушій **ніколи** не апрувить сам; луп повертає
> `awaiting_confirm` + код. Покажи користувачу `confirm_pending` перед апрувом. Suite за
> замовчуванням не чіпає mutating-фічі (`code_task`, `driver_exec`) — лише явний виклик.

## Цикл (те, що просив користувач)

```
features (scenario) ──► source (Http | Replay | Fault | Record — ДЕКОРАТОРИ) ──► oracle
      ▲                                                                            │
      │                                            pass ──► report (артефакт)      │
      └── retest ◄── [людський confirm_approve, S4] ◄── dispatch: coder-MCP / Computer-Use-MCP ◄── fail
```

## Що під капотом
- **Ядро (generic):** [`engine/server.py`](engine/server.py) — FastMCP, **12 tool-ів**, транспорт
  stdio/http/sse (`AI_TESTER_MCP_TRANSPORT`); порти `endpoint`/`auth`/`source`/`scenario`/`oracle`/
  `dispatch`/`loop`/`report`/`confirm_gate`/`audit`. Тестоване без MCP-SDK (lazy-імпорт) і без мережі.
- **Adapter (jarvis):** manifest — 10 фіч client-API (ендпоінт + oracle + sim-фікстура + on_fail).
  Нова фіча платформи = новий запис у manifest, нуль змін ядра (Open/Closed). Гейтовані фічі
  (`ENABLE_CONTEXT_API`/`ENABLE_MCP_HUB`) дають `skipped_gated`, не fail; driver/code роути
  безумовні — вимкнений computer-use видно у тілі (`enabled:false`), не статусом.
- **Артефакти:** `data/artifacts/ai_tester/run-*.json` (+`last_run.json`) — лише метадані
  (anti-leak, S1); recordings-* (record-режим) містять зредаговані тіла відповідей і разом з усім
  каталогом під `.gitignore`. Audit — `data/logs/ai_tester.jsonl`, redaction перед виходом.

## Залізні інваріанти (зі статуту)
- **S1:** дефолтний endpoint локальний; звіти/audit без сирих відповідей; redaction default on.
- **S2:** тестер клієнтський — **нуль diff у бекенді**; симуляція = декоратор джерела, не мок у gateway.
- **S3:** рушій = I/O-оркестрація портів, не мозок; фікси робить coder/computer платформи.
- **S4:** мутації тільки через `confirm_gate`; авто-апрув відсутній як код-шлях.

## Тести
`pytest .claude/skills/ai_tester/engine/tests -q` — декоратори джерела, oracle, bounded-луп,
S4 (нуль авто-апрувів), anti-leak, drift manifest↔engine, FastMCP-wiring. Без мережі й без MCP-SDK.
