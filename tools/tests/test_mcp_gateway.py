"""P5 MCP gateway allowlist."""
import asyncio
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


class _FakeStdin:
    def __init__(self) -> None:
        self.buf = b""

    def write(self, data: bytes) -> None:
        self.buf += data

    async def drain(self) -> None:  # noqa: D401
        pass


class _FakeProc:
    returncode = None


def _session_with_streams(stdout_bytes: bytes) -> tuple[mcp_gateway._McpSession, _FakeStdin]:
    sess = mcp_gateway._McpSession({"name": "fake", "command": "true"})
    reader = asyncio.StreamReader()
    reader.feed_data(stdout_bytes)
    reader.feed_eof()
    stdin = _FakeStdin()
    proc = _FakeProc()
    proc.stdout = reader  # type: ignore[attr-defined]
    proc.stdin = stdin  # type: ignore[attr-defined]
    sess._proc = proc  # type: ignore[assignment]
    return sess, stdin


async def test_read_message_newline_delimited():
    # MCP stdio = одне JSON-RPC повідомлення на рядок (саме так відповідає реальний сервер).
    sess, _ = _session_with_streams(b'{"jsonrpc":"2.0","id":1,"result":{"ok":true}}\n')
    msg = await sess._read_message()
    assert msg["id"] == 1 and msg["result"]["ok"] is True


async def test_write_message_has_no_content_length_framing():
    sess, stdin = _session_with_streams(b"")
    await sess._write_message({"jsonrpc": "2.0", "id": 2, "method": "ping", "params": {}})
    # Рівно один рядок, із завершальним \n, без LSP-style Content-Length і без внутрішніх \n.
    assert stdin.buf.endswith(b"\n")
    assert b"Content-Length" not in stdin.buf
    assert b"\n" not in stdin.buf[:-1]


def _session_with_rpc_result(result):
    """A bare session whose `_rpc` (tools/call) returns a canned CallToolResult."""
    sess = mcp_gateway._McpSession({"name": "fake", "command": "true"})

    async def _fake_rpc(method, params=None):
        assert method == "tools/call"
        return result

    sess._rpc = _fake_rpc  # type: ignore[method-assign]
    return sess


async def test_call_tool_returns_text_content_on_success():
    sess = _session_with_rpc_result({"content": [{"type": "text", "text": "hello"}]})
    assert await sess.call_tool("greet", {}) == "hello"


async def test_call_tool_surfaces_iserror_as_failure():
    # MCP tool failure (isError=true) must NOT be returned as a plain success observation.
    sess = _session_with_rpc_result(
        {"content": [{"type": "text", "text": "boom: bad arg"}], "isError": True}
    )
    out = await sess.call_tool("do_thing", {})
    assert "boom: bad arg" in out
    assert "do_thing" in out and "помилку" in out  # explicit failure marker for the agent loop


async def test_call_tool_iserror_false_is_normal_success():
    sess = _session_with_rpc_result(
        {"content": [{"type": "text", "text": "ok"}], "isError": False}
    )
    assert await sess.call_tool("do_thing", {}) == "ok"  # no error marker when isError is falsy


async def test_call_tool_iserror_with_empty_content_still_marks_failure():
    # A failing tool that sends no error text must still surface as a failure, not empty success.
    sess = _session_with_rpc_result({"content": [], "isError": True})
    out = await sess.call_tool("do_thing", {})
    assert "do_thing" in out and "помилку" in out


async def test_call_tool_non_dict_result_falls_back_to_str():
    # An off-spec server returning a bare value (not a CallToolResult dict) → str fallback.
    sess = _session_with_rpc_result("just a string")
    assert await sess.call_tool("t", {}) == "just a string"
