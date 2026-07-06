# Підключення `/erp_sa`

## Передумови (реюз наявної інфри JARVIS)
1. **Gateway піднятий** локально (`http://localhost:8000`) — той самий, що для `jarvis`-конектора.
2. **Chrome-міст активний:** [`extension/`](../../../../extension/) встановлено в браузері й воно опитує
   `GET /api/v1/chrome/poll`. Це той браузер, де ти **за VPN** і **залогінений в ERP**.
3. **Прапор** `ENABLE_ERP_SA=true` у `.env` (S2: дефолт off; вимкнено → skill не активний).
4. **Auth** до gateway — як у `jarvis` конектора (Basic `PLATFORM_PASSWORD`/`ADMIN_PANEL_PASSWORD`
   або co-located `.env`). Секрет ніколи в MCP-конфігу.

## Розпізнавання сканів/фото (P2)
- Постав `OLLAMA_MODEL_VISION` у `.env` (напр. `llava:7b` або `qwen2.5vl:7b`).
- На тісній VRAM (8 ГБ) — `OLLAMA_VISION_ON_DEMAND=true` (вивантажує chat/agent перед vision).
- Порожній `OLLAMA_MODEL_VISION` → шлях `scan` вимкнено (text/digital працюють).

## Перший запуск (P1, dry-run first)
1. Відкрий import-сторінку ERP за VPN у браузері з extension.
2. `erp_sa.inspect_form` → зафіксуй реальні селектори у
   [`adapters/sparrow-avia/manifest.json`](../adapters/sparrow-avia/manifest.json) (закриває `_seed`).
3. `erp_sa.autofill {source, dry_run: true}` → перевір мапу «розпізнане → поле форми», нічого не чіпаючи.
4. Прибери `dry_run` → поля заповнюються в браузері. **Submit тиснеш сам** (S4).

## Межі (S1/S4)
- Розпізнавання **локальне** (Ollama) — документ не йде у зовнішній AI.
- Розширення **ніколи** не сабмітить запис у прод-ERP — фінальний «Зберегти» за людиною.
- Дії **лише** на allowlisted ERP-роутах (`manifest.allowlist`); інша сторінка → відмова.
