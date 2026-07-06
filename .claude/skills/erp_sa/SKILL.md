---
name: erp_sa
description: >-
  MCP-розширення автозаповнення ERP Sparrow-Avia (erp.sparrow-avia.tech/import).
  Приймає файл та/або текст, розпізнає його ЛОКАЛЬНИМ Jarvis (текст/цифровий файл/скан-фото)
  і ПОВНІСТЮ заповнює відповідну import-форму в РЕАЛЬНОМУ браузері користувача через Chrome-міст
  (браузер уже за VPN і залогінений). Використовуй, коли користувач каже: "/erp_sa",
  "заповни ERP", "автозаповни sparrow", "розпізнай накладну/інвойс і заповни форму",
  "занеси цей документ в ERP", "autofill sparrow-avia", "імпорт у ERP з файлу".
  Це домен-конектор (Ports&Adapters): engine generic, Sparrow-конкретика в адаптері.
  Заповнення завжди під людський апрув (S4) — ніколи не сабмітить запис у прод-ERP сам.
---

# /erp_sa — автозаповнення ERP Sparrow-Avia

Робить рутину «переносити дані з листа/накладної/інвойсу в ERP-форму руками» одним ходом:
**завантаж → розпізнай (Jarvis) → знайди сторінку → заповни → підтверди**. Заповнення йде в
**тому самому браузері**, де відкрито ERP → **VPN і auth розв'язані «безкоштовно»** (S1).

> **Концепт і контракт:** [`docs/ERP_SA_AUTOFILL_CONCEPT.md`](../../../docs/ERP_SA_AUTOFILL_CONCEPT.md)
> (7 портів, tool-surface, фази). Дисципліна дзеркальна до [`jarvis`](../jarvis/SKILL.md) / `kaizen`.

## Маршрутизація інтентів

| Намір користувача | Дія |
|---|---|
| «розпізнай і заповни …», «занеси цей файл в ERP», «autofill» | tool **`autofill`** `{source, dry_run}` — головний happy-path |
| «просто розпізнай …», «що ти витягнеш із цього» | tool **`recognize`** `{source}` — лише структуровані поля, без заповнення |
| «які поля на цій сторінці», «зчитай форму» | tool **`inspect_form`** `{url?}` — селектори+лейбли форми через Chrome-міст |
| «заповни за цією мапою» | tool **`fill`** `{form_fill}` — низькорівнево (blast-radius allowlist) |
| апрув/скасування фінального submit | реюз `jarvis` `confirm_pending` → `confirm_approve {code}` / `confirm_cancel` |
| «підключи / встанови erp_sa» | проведи за [`references/install.md`](references/install.md) |

> **S4 (залізно):** `autofill`/`fill` тільки **заповнюють** поля. **Фінальний submit ERP-форми
> робить людина** (натискає «Зберегти») або йде через `confirm_approve`. Розширення **ніколи** не
> сабмітить запис у прод-ERP само. Перед заповненням за замовчуванням показуй превʼю (`dry_run`).

> **Blast-radius:** діємо **лише** на allowlisted ERP-роутах (`adapters/sparrow-avia/manifest.json`
> → `allowlist`). Перед кожною дією порт `fill` звіряє `location.href`. Інша сторінка/вкладка → відмова.

**Якщо Chrome-міст ще не піднятий** (extension не опитує `/chrome/poll`) → не імітуй заповнення;
спочатку проведи інсталяцію ([`references/install.md`](references/install.md)), потім клич `fill`.

## Що під капотом (фази §8 концепту)
- **MCP-адаптер (P1, generic):** [`engine/server.py`](engine/server.py) — FastMCP `erp_sa`, **7 tool-ів**
  (`recognize`/`inspect_form`/`autofill`/`fill`/`confirm_pending`/`confirm_approve`/`confirm_cancel`),
  транспорт stdio/http (`ERP_SA_MCP_TRANSPORT`). Зареєстрований у [`.mcp.json`](../../../.mcp.json)
  (`.venv` python) — Claude Code підхопить наступної сесії. 25 юніт-тестів, mypy-strict.
- **Engine (generic):** [`engine/ports.md`](engine/ports.md) — пайплайн `ingest→recognize→locate→map→fill→confirm`;
  порти `ingest`/`recognize`/`locate`/`map`/`fill`/`confirm_gate`/`audit`. Нуль рядка «Sparrow».
- **Recognize:** три шляхи вводу — вставлений текст, цифровий файл (xlsx/csv/pdf/docx), скан/фото
  (реюз `OLLAMA_MODEL_VISION`/`describe_image`). Інференс **локальний** (S1).
- **Fill:** реюз gateway [`client_api/chrome.py`](../../../gateway/app/client_api/chrome.py) +
  [`extension/`](../../../extension/) — реальний браузер юзера за VPN.
- **Adapter (sparrow-avia):** [`adapters/sparrow-avia/manifest.json`](adapters/sparrow-avia/manifest.json)
  — route-map (тип документа → сторінка), field-aliases (синоніми полів), allowlist. Єдине місце ERP-конкретики.

## Залізні інваріанти (зі статуту)
- **S1:** розпізнавання локальне; документ не тече в зовнішній AI. Audit — лише метадані (anti-leak; документи = PII).
- **S2:** усе за прапором `ENABLE_ERP_SA` (default off) → наявні канали не зачеплені.
- **S3:** engine у бекенді (канал ≠ мозок); skill і кожен канал (TG/web/MCP) — лише I/O-entrypoint.
- **S4:** фінальний submit — тільки через `confirm_gate`; ніколи не auto-submit.
- **S5/blast-radius:** DOM-first через селектори; дії лише на allowlisted ERP-роутах (deny-wins).

## Тести
`pytest .claude/skills/erp_sa/engine/tests -q` — маппинг полів, blast-radius allowlist, fail-fast,
anti-leak audit, adapter↔engine consistency. Без мережі, без ERP, без Chrome.
