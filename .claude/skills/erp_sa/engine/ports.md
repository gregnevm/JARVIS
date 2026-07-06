# `erp_sa` engine — контракт портів (статус)

> **SSOT контракту — [`docs/ERP_SA_AUTOFILL_CONCEPT.md` §3](../../../../docs/ERP_SA_AUTOFILL_CONCEPT.md).**
> Тут — лише статус-таблиця (щоб не плодити другий гексагон / дрейф контрактів, як DR6 у kaizen).

Гексагон автозаповнення: `ingest → recognize → locate → map → fill → confirm_gate`, наскрізь `audit`.

| # | Порт | Обов'язковий | Реалізовано | Реюз / джерело |
|---|---|---|---|---|
| 1 | `ingest` | ✅ | ✅ P1 (txt/csv/pdf/docx/xlsx) | `extract_source_text`; pypdf/python-docx/openpyxl |
| 2 | `recognize` | ✅ | ✅ P1 (text/digital) · ⏳ P2 (scan) | `chat`(mode=chat) + JSON-парс; scan → `OLLAMA_MODEL_VISION` |
| 3 | `locate` | ✅ | ✅ P1 | Chrome `eval` (`_INSPECT_JS`) + adapter `route_map` |
| 4 | `map` | ✅ | ✅ P1 | `map_fields` × adapter `field_aliases` |
| 5 | `fill` | ✅ | ✅ P1 (код + юніт; live — за VPN) | `/api/v1/chrome/*` + `extension/`; blast-radius allowlist |
| 6 | `confirm_gate` | ✅ (S4) | ✅ P1 | `/api/v1/confirm/*` (`confirm_*` tools) |
| 7 | `audit` | ✅ | ✅ P1 | `JsonlLog`, `Redactor` (лише метадані) |

> **Реалізовано P1** (`engine/server.py`, 25 юніт-тестів, mypy-strict): MCP-адаптер `erp_sa` з 7 tool-ами
> (`recognize`/`inspect_form`/`autofill`/`fill`/`confirm_*`), зареєстрований у `.mcp.json`. Пайплайн
> code-complete й покритий моками; **live-прогін проти реального ERP** чекає VPN + піднятого gateway +
> extension (`references/install.md`). **P2:** vision для сканів/фото.

**Fail-fast (DR3):** `ingest`+`recognize`+`fill`+`confirm_gate` порожні → engine не стартує.

**Dependency rule (DR2):** цей engine **не згадує «Sparrow»** — уся ERP-конкретика в
[`../adapters/sparrow-avia/manifest.json`](../adapters/sparrow-avia/manifest.json). Drift adapter↔engine
ловить `tests/` (за аналогією `jarvis` `test_manifest_matches_routes`).

**Інваріанти:** S1 (локальний recognize) · S2 (`ENABLE_ERP_SA` off default) · S3 (engine у бекенді) ·
S4 (submit лише через confirm) · S5/blast-radius (DOM-first, allowlist, deny-wins).
