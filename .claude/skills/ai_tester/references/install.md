# ai_tester — інсталяція MCP-сервера

## 1. Хост Claude Code (репо-локально — вже зроблено)

Запис у кореневому [`.mcp.json`](../../../../.mcp.json):

```json
"ai_tester": {
  "command": ".venv/Scripts/python.exe",
  "args": [".claude/skills/ai_tester/engine/server.py"],
  "env": { "AI_TESTER_BASE_URL": "http://localhost:8000" }
}
```

Креденшели НЕ кладемо в конфіг (S1): рушій сам підтягне `PLATFORM_PASSWORD` з co-located
репо-`.env` (як jarvis/erp_sa). Альтернатива — явні `AI_TESTER_API_KEY` (Bearer) або
`AI_TESTER_BASIC_PASSWORD` (Basic) у блоці `env`.

Поза репо (будь-який MCP-хост):

```bash
claude mcp add ai_tester -- python .claude/skills/ai_tester/engine/server.py
```

Залежності: `pip install -r .claude/skills/ai_tester/engine/requirements.txt` (mcp, httpx).

## 2. Опційно: віддати рушій рантайм-агенту JARVIS

Щоб сам агент платформи міг ганяти самотести (`mcp_call` через керований хаб), додай у `.env`:

```
MCP_SERVERS_JSON=[{"name":"ai_tester","command":".venv/Scripts/python.exe","args":[".claude/skills/ai_tester/engine/server.py"]}]
```

і ввімкни `ENABLE_MCP_HUB=true` (гейт gateway). Це allowlist-механізм tools-сервісу — сервери
задаються лише через `.env` (THREAT_MODEL), модель command не вигадує.

## 3. Смоук після інсталяції

1. `ready` → `gateway: true`, видно identity і 10 фіч.
2. `run {mode: "replay"}` → зелений suite офлайн (sim-фікстури, мережа не потрібна).
3. `run {}` → живий прогін; гейтовані фічі чесно `skipped_gated`.
4. `simulate {feature: "chat", fault: "empty_reply"}` → `fail` (oracle ловить тиху деградацію).
