# Встановлення конектора `/jarvis` (Фаза 1, stdio)

## 0. Передумова: локальний gateway піднятий
Конектор ходить у `JARVIS_BASE_URL` (дефолт `http://localhost:8000`). Перевір (підстав свій пароль —
`PLATFORM_PASSWORD` або `ADMIN_PANEL_PASSWORD`):
```powershell
curl http://localhost:8000/api/v1/whoami -u admin:$env:ADMIN_PANEL_PASSWORD
```
Має повернути `{org_id, user_id, role, plan, ...}` (а не 401/connection refused).

## 1. Залежності конектора
MCP-SDK не входить у бекенд JARVIS — це клієнтська залежність. Встанови в те Python-середовище,
яким Claude Code запускатиме сервер:
```powershell
python -m pip install -r O:\JARVIS\.claude\skills\jarvis\connector\requirements.txt
```
> Репо-`.venv` за дефолтом `mcp` не має — або доінсталюй у нього, або вкажи інший python у кроці 3.

## 2. Креденшел (порт `auth`)
`sk-jarvis-*` per-org ще не реалізований (AP-1). Робочі режими self-hosted:
- **Basic (найпростіше):** пароль — `PLATFORM_PASSWORD` **або** `ADMIN_PANEL_PASSWORD` (gateway приймає
  обидва; юзер за дефолтом `admin`). Конектор підхоплює будь-який із них з env у такому ж порядку.
- **Bearer JWT:** отримай пару через `POST /api/v1/auth/login`, передай як `JARVIS_API_KEY`.

## 3. Реєстрація в Claude Code
```powershell
claude mcp add jarvis `
  --env JARVIS_BASE_URL=http://localhost:8000 `
  --env JARVIS_BASIC_PASSWORD=твій_пароль `
  -- python "O:\JARVIS\.claude\skills\jarvis\connector\server.py"
```
`JARVIS_BASIC_PASSWORD` = значення твого `PLATFORM_PASSWORD`/`ADMIN_PANEL_PASSWORD`.
Bearer-варіант: заміни `--env JARVIS_BASIC_PASSWORD=...` на `--env JARVIS_API_KEY=<jwt|sk-...>`.

Перевір: `claude mcp list` → `jarvis` у списку; тули `jarvis.whoami`, `jarvis.chat`.

## 4. Дим-тест
- `jarvis.whoami` → твій org/plan з локального інстансу.
- `jarvis.chat {"text":"привіт","mode":"auto"}` → відповідь **локального** інференсу.

## Реєстрація без CLI (`.mcp.json`)
У корені репо є project-scope [`.mcp.json`](../../../../.mcp.json) — Claude Code підхопить сервер
`jarvis` наступної сесії **без** `claude mcp add` і без секрета (спрацьовує `.env`-fallback). Команда
вказує на `.venv/Scripts/python.exe` (там стоїть `mcp`). Прибрати реєстрацію = видалити блок із `.mcp.json`.

## Транспорт (опційно)
`JARVIS_MCP_TRANSPORT=stdio` (дефолт, S1 локально) `| http` (streamable-http) `| sse` — для remote-хоста.

## ⚠️ S1 — що бачить хост-AI
Контент `chat`/`code` проходить через хост-AI (Claude Code у хмарі); інференс JARVIS лишається локальним.
**Redaction увімкнено за дефолтом** (`JARVIS_REDACT=1`): секрети (ключі/токени/картки/IBAN) у вихідних
результатах скрабляться перед поверненням у хост (реюз `jarvis_core` Redactor). Вимкнути — `JARVIS_REDACT=0`
(тоді хост бачить сире). Слід-аудит (`data/logs/jarvis_connector.jsonl`) і так пише лише метадані, не payload.

## Юніт-тести (без мережі, без MCP-SDK)
```powershell
pytest O:\JARVIS\.claude\skills\jarvis\connector\tests -q
```
