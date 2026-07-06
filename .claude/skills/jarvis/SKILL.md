---
name: jarvis
description: >-
  Вихідний MCP-конектор до платформи JARVIS — роз'єм, який втикається в Claude Code / будь-який
  MCP-хост і дозволяє керувати ЛОКАЛЬНИМ інстансом JARVIS звідти (chat, identity; далі — контекст,
  coding-агент, computer-use). Використовуй, коли користувач каже: "/jarvis", "спитай jarvis",
  "що jarvis відповість", "підключи jarvis як конектор", "встанови mcp jarvis", "jarvis whoami",
  "постав задачу jarvis". Це КЛІЄНТСЬКИЙ конектор (Ports&Adapters): ядро generic, JARVIS-конкретика
  в адаптері. Не для самопокращення репо (то — kaizen/self-improve).
---

# /jarvis — конектор-адаптер-скіл

Робить JARVIS **вихідним MCP-сервером**: те, що ти втикаєш у хост і керуєш платформою звідти.
Дзеркальне до `kaizen` (той покращує репо зсередини; цей — експонує платформу назовні), та сама
дисципліна **connector (generic) + adapter (jarvis) + skill (роутер)**.

> **Концепт і контракт:** [`docs/JARVIS_CONNECTOR_CONCEPT.md`](../../../docs/JARVIS_CONNECTOR_CONCEPT.md)
> (7 портів, tool-surface, фази). **P1-спека:** [`docs/JARVIS_CONNECTOR_P1.spec.md`](../../../docs/JARVIS_CONNECTOR_P1.spec.md).

## Маршрутизація інтентів

| Намір користувача | Дія |
|---|---|
| «підключи / встанови jarvis як конектор», «mcp add» | проведи за [`references/install.md`](references/install.md) |
| «спитай jarvis …», «що jarvis відповість …» | tool **`chat`** `{text, mode}` (mode дефолт `auto`) |
| «jarvis whoami», «хто я в jarvis», «який план» | tool **`whoami`** |
| «що jarvis знає про …», «пошукай у памʼяті» | tool **`context_search`** / `context_recent` / `context_ingest` (за `ENABLE_CONTEXT_API`) |
| «постав задачу jarvis написати код» | tool **`code`** `{text, target}` — **S4: confirm-gated** (див. нижче) |
| «хай jarvis зробить на ПК …» | tool **`computer`** `{text}` — **S4: confirm-gated** (за `ENABLE_COMPUTER_USE`) |
| апрув/скасування дії, що очікує | `confirm_pending` → `confirm_approve {code}` / `confirm_cancel` |
| «які MCP-сервери в jarvis», «виклич X через jarvis» | `mcp_list` / `mcp_call {server, tool, arguments}` (за `ENABLE_MCP_HUB`) |

> **S4 (залізно):** `code`/`computer` лише **дispatch-ять** дію. Мутуючий крок виконується на реальній
> машині й **чекає людського `confirm_approve`** — конектор сам **ніколи** не апрувить. Перед апрувом
> покажи користувачу, що саме в `confirm_pending`.

**Якщо MCP-сервер `jarvis` ще не підключений** (нема тулів `jarvis.*`) → не вигадуй відповідь
платформи; спочатку проведи інсталяцію (`references/install.md`), потім клич тули.

## Що під капотом (Фази 1-4)
- **Ядро (generic):** [`connector/server.py`](connector/server.py) — FastMCP, **12 tool-ів**, транспорт
  stdio/http/sse (`JARVIS_MCP_TRANSPORT`); порти `endpoint`/`auth`/`capabilities`/`identity`/`confirm_gate`/`audit`.
  Тестоване без MCP-SDK (lazy-імпорт).
- **MCP-хаб (P4):** gateway [`client_api/mcp.py`](../../../gateway/app/client_api/mcp.py) за `ENABLE_MCP_HUB` (default off, S2).
- **Adapter (jarvis):** [`adapters/jarvis/manifest.json`](adapters/jarvis/manifest.json) — base URL,
  auth-режими, маршрути `/api/v1/*`. Єдине місце JARVIS-конкретики.
- **Порти-статус:** [`connector/ports.md`](connector/ports.md) (контракт — у концепті §3, не дублюється).

## Залізні інваріанти (зі статуту)
- **S1:** `endpoint` за дефолтом локальний; інференс локальний. Caveat: chat-контент бачить хост-AI
  (повна `redaction` — Фаза 4). Audit пише лише метадані, не сирий payload.
- **S2:** конектор клієнтський — **нуль diff у бекенді** (gateway/tools незмінні).
- **S3:** конектор = новий канал (I/O), не мозок. Бізнес-логіка лишається в tools/`jarvis_core`.
- **S4 (Фаза 3):** мутуючі/computer-дії підуть лише через `confirm_gate` — ніколи не auto-confirm.

## Тести
`pytest .claude/skills/jarvis/connector/tests -q` — маппинг tool→endpoint, fail-fast, anti-leak,
adapter↔core consistency. Без мережі й без MCP-SDK.
