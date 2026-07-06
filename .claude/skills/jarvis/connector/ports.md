# jarvis-connector — статус портів (Фази 1-4)

> **Контракт портів — НЕ тут.** SSOT контракту — [`docs/JARVIS_CONNECTOR_CONCEPT.md` §3](../../../../docs/JARVIS_CONNECTOR_CONCEPT.md).
> Цей файл — лише **таблиця заповненості** (щоб не плодити другий гексагон, CTO-рек R2 / DR6).

| # | Порт | Стан | Зв'язування |
|---|------|------|-------------|
| 1 | `endpoint` | ✅ | `base_url` дефолт `http://localhost:8000` (S1); транспорт `stdio`\|`http`\|`sse` (`JARVIS_MCP_TRANSPORT`) |
| 2 | `auth` | ✅ | Bearer (`JARVIS_API_KEY`) / Basic (`PLATFORM_PASSWORD`/`ADMIN_PANEL_PASSWORD`) / co-located `.env`-fallback; fail-fast |
| 3 | `capabilities` | ✅ | **12 tool-ів** (P1 whoami/chat · P2 context_* · P3 code/computer/confirm_* · P4 mcp_list/mcp_call) |
| 4 | `identity` | ✅ | `whoami` → `GET /api/v1/whoami` |
| 5 | `confirm_gate` | ✅ | `confirm_pending/approve/cancel`; конектор **ніколи** не апрувить сам (S4) |
| 6 | `redaction` | ✅ | скраб секретів у вихідних результатах ПЕРЕД хост-AI (S1), реюз SSOT `jarvis_core.passport.Redactor`; **default on**, opt-out `JARVIS_REDACT=0` |
| 7 | `audit` | ✅ | `make_audit` → SSOT `JsonlLog`; лише метадані, C1-теги; `confirm_approve` → `human-approved` |

**MCP-хаб (P4):** `mcp_list`/`mcp_call` → gateway `/api/v1/mcp/*` (новий модуль `client_api/mcp.py`,
за прапором `ENABLE_MCP_HUB`, default off — S2). JARVIS = керований хаб: downstream-сервери агрегатора
доступні хосту з нашою auth попереду.

**Гейти gateway:** `context_*`→`ENABLE_CONTEXT_API`; `computer`→`ENABLE_COMPUTER_USE`;
`mcp_*`→`ENABLE_MCP_HUB`; `code.target=claude`→`ENABLE_CLAUDE_CODE_BRIDGE`. Вимкнено → 404/503 пробрасується.

**S4-дисципліна:** `code`/`computer` лише дispatch-ять; виконання чекає людського `confirm_approve` — auto-confirm неможливий за конструкцією.
**Adapter-binding:** маршрути — у [`../adapters/jarvis/manifest.json`](../adapters/jarvis/manifest.json) = `server._ROUTES` (drift під тестом).

**Усі 7 портів заповнені.** Єдиний лишок поза контрактом: per-org `sk-jarvis` key (P5 — enabler-блок на AP-1).
