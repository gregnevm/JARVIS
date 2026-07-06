"""AP-7.4 — client-API MCP-хаб: прапор-гейт, проксі до tools, валідація.

Тестуємо handler-функції ПРЯМО (без TestClient) — швидко й без lifespan-залежностей.
asyncio_mode=auto (pyproject) → async-тести без маркера.
"""
from __future__ import annotations

import pytest
from app.client_api import mcp
from app.config import settings
from fastapi import HTTPException


@pytest.fixture
def enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "enable_mcp_hub", True)


async def test_disabled_returns_404(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "enable_mcp_hub", False)
    with pytest.raises(HTTPException) as ei:
        await mcp.list_mcp_servers(ctx=None)
    assert ei.value.status_code == 404


async def test_list_servers_proxies(monkeypatch: pytest.MonkeyPatch, enabled: None) -> None:
    calls: list[tuple[str, str]] = []

    async def ft(method: str, path: str, payload: object = None) -> dict[str, object]:
        calls.append((method, path))
        return {"servers": ["filesystem"]}

    monkeypatch.setattr(mcp, "_tools", ft)
    out = await mcp.list_mcp_servers(ctx=None)
    assert out == {"servers": ["filesystem"]}
    assert calls == [("GET", "/mcp/servers")]


async def test_call_proxies_body(monkeypatch: pytest.MonkeyPatch, enabled: None) -> None:
    captured: dict[str, object] = {}

    async def ft(method: str, path: str, payload: object = None) -> dict[str, object]:
        captured.update({"method": method, "path": path, "payload": payload})
        return {"text": "ok"}

    monkeypatch.setattr(mcp, "_tools", ft)
    out = await mcp.call_mcp_tool(
        mcp.McpCallBody(server="fs", tool="read", arguments={"p": 1}), ctx=None
    )
    assert out == {"text": "ok"}
    assert captured["method"] == "POST"
    assert captured["path"] == "/mcp/call"
    assert captured["payload"] == {"server": "fs", "tool": "read", "arguments": {"p": 1}}


async def test_empty_server_or_tool_400(monkeypatch: pytest.MonkeyPatch, enabled: None) -> None:
    with pytest.raises(HTTPException) as ei:
        await mcp.call_mcp_tool(mcp.McpCallBody(server=" ", tool="read"), ctx=None)
    assert ei.value.status_code == 400
