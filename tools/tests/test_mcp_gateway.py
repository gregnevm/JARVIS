"""P5 MCP gateway allowlist."""
import json

import pytest

from app import mcp_gateway


async def test_unknown_server_rejected(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(mcp_gateway.settings, "mcp_servers_json", "[]")
    with pytest.raises(ValueError, match="unknown"):
        await mcp_gateway.call_tool("nope", "tool", {})


async def test_list_servers_empty(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(mcp_gateway.settings, "mcp_servers_json", "")
    servers = await mcp_gateway.list_servers_status()
    assert servers == []


async def test_load_servers_parses(monkeypatch: pytest.MonkeyPatch):
    cfg = [{"name": "demo", "command": "echo", "args": ["hi"]}]
    monkeypatch.setattr(mcp_gateway.settings, "mcp_servers_json", json.dumps(cfg))
    loaded = mcp_gateway._load_servers()
    assert loaded[0]["name"] == "demo"
