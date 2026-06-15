# JARVIS — Threat Model (ops, v1)

Self-hosted single-tenant. Фокус: **Telegram → gateway → tools → host**.

## Активи

| Актив | Ризик |
|-------|--------|
| `TELEGRAM_BOT_TOKEN`, `.env` | Повний контроль бота |
| `HOSTAGENT_TOKEN` | PowerShell/FS/екран на Windows |
| `data/` (sessions, learned, macros) | Витік діалогів / whitelist |
| Postgres / Redis | Памʼять, нагадування, rate limits |
| Ollama на хості | Інференс, prompt injection → tools |

## Поверхні атаки

### Telegram / gateway

- **Whitelist** — `ALLOWED_USER_IDS` + `/allow`; гості з обмеженим rate limit.
- **Admin** — `ADMIN_USER_IDS`; Computer owner — `COMPUTER_OWNER_USER_IDS`.
- **Webhook** — `TELEGRAM_WEBHOOK_SECRET` у prod.
- **Mini App** — HMAC `initData`; `WEBAPP_DEV_OPEN=false` у prod.

### Computer Use

- Tier T0–T4; confirm на mutating; **admin PS** — подвійне підтвердження.
- `COMPUTER_RATE_LIMIT_PER_HOUR`, audit `computer.jsonl`.
- Hostagent: `HOSTAGENT_FS_ROOTS`, `HOSTAGENT_ALLOW_ADMIN=0` за замовч.

### Agent tools

- `web_fetch` / `web_search` — SSRF: лише http(s), таймаути, обрізка тексту.
- `code_exec` — вимкнено за замовч (`ENABLE_CODE_EXEC=false`).
- `browser_*` — ізольований headless Chromium у tools.
- Uploads — `data/uploads/`, розмір лімітів Telegram/tools.

### MCP Gateway (P5)

- **Allowlist only** — сервери лише з `MCP_SERVERS_JSON` у `.env`; користувач/модель не задають `command`.
- **stdio subprocess** — один процес на server; timeout 30s; результат обрізається.
- **Admin config** — зміна MCP servers лише через `.env` + redeploy; Platform UI read-only.
- **Untrusted tools** — MCP tools еквівалентні зовнішньому коду; не увімкнювати сторонні servers без review.
- **Network** — MCP server сам керує egress; не додавати servers з arbitrary shell у prod.

### Connectors (P6)

- Integration tokens (`NOTION_TOKEN`, `SLACK_BOT_TOKEN`) — лише в `.env`, не в чаті.
- OAuth flows — out of scope MVP; rotation вручну через `.env`.

### OpenAI-compatible API (P11)

- **Opt-in** — `ENABLE_OPENAI_API=true` + `OPENAI_API_KEY`; інакше `/v1/*` → 404.
- **Bearer only** — без ключа в query string; не логувати Authorization.
- **User binding** — `X-JARVIS-User-Id` або `OPENAI_DEFAULT_USER_ID`; інакше перший ALLOWED.
- **Same tool surface** — той самий agent loop, що Telegram; не expose admin/computer без whitelist.

### Training / Twin

- LoRA promote — `TWIN_MIN_EVAL_PROMOTE` + `training/eval/gate.py`.
- Session export — лише адмін/ops scripts.

## Рекомендації (пріоритет)

1. Ротація токена (M4) після витоку в лог/чат.
2. Не комітити `.env`; обмежити доступ до `data/`.
3. `WEBAPP_DEV_OPEN=false`, named tunnel лише для `/app`.
4. Регулярний `verify_stack.ps1` + [`BACKUP.md`](BACKUP.md).

## Out of scope (v1)

- Multi-tenant SaaS isolation
- WAF перед Ollama
- Hardware HSM для ключів
