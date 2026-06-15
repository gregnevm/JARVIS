"""MCP Gateway MVP (P5) — stdio subprocess clients з allowlist config."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from .config import settings

logger = logging.getLogger("jarvis.tools.mcp")

_MCP_TIMEOUT = 30.0
_sessions: dict[str, "_McpSession"] = {}


def _load_servers() -> list[dict[str, Any]]:
    raw = (settings.mcp_servers_json or "").strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("invalid MCP_SERVERS_JSON")
        return []
    if not isinstance(data, list):
        return []
    out: list[dict[str, Any]] = []
    for item in data:
        if isinstance(item, dict) and item.get("name") and item.get("command"):
            out.append(item)
    return out


def _server_cfg(name: str) -> dict[str, Any]:
    for s in _load_servers():
        if str(s.get("name")) == name:
            return s
    raise ValueError(f"unknown MCP server: {name}")


class _McpSession:
    """Minimal MCP stdio client (JSON-RPC + Content-Length framing)."""

    def __init__(self, cfg: dict[str, Any]) -> None:
        self.name = str(cfg["name"])
        self._cfg = cfg
        self._proc: asyncio.subprocess.Process | None = None
        self._req_id = 0
        self._lock = asyncio.Lock()

    async def _ensure(self) -> None:
        if self._proc and self._proc.returncode is None:
            return
        cmd = [str(self._cfg["command"])] + [str(a) for a in (self._cfg.get("args") or [])]
        env = None
        if self._cfg.get("env") and isinstance(self._cfg["env"], dict):
            import os

            env = {**os.environ, **{str(k): str(v) for k, v in self._cfg["env"].items()}}
        self._proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            env=env,
            limit=8 * 1024 * 1024,  # великі tools/list-відповіді не повинні впиратись у 64 КБ readline
        )
        # MCP stdio handshake: initialize (request) → initialized (notification).
        # Викликаємо raw-варіанти: _ensure уже працює під self._lock (asyncio.Lock не реентрантний).
        await self._rpc_raw(
            "initialize",
            {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "jarvis", "version": "1.0"}},
        )
        await self._rpc_raw("notifications/initialized", {}, notify=True)

    async def _read_message(self) -> dict[str, Any]:
        # MCP stdio = JSON-RPC по одному повідомленню на рядок (newline-delimited, без Content-Length).
        assert self._proc and self._proc.stdout
        while True:
            line = await asyncio.wait_for(self._proc.stdout.readline(), timeout=_MCP_TIMEOUT)
            if not line:
                raise RuntimeError("MCP stdout closed")
            line = line.strip()
            if line:
                return json.loads(line.decode("utf-8"))

    async def _write_message(self, msg: dict[str, Any]) -> None:
        assert self._proc and self._proc.stdin
        # ensure_ascii=False лишає Unicode; json.dumps не вставляє \n всередині → одне повідомлення = один рядок.
        data = json.dumps(msg, ensure_ascii=False).encode("utf-8") + b"\n"
        self._proc.stdin.write(data)
        await self._proc.stdin.drain()

    async def _rpc_raw(self, method: str, params: dict[str, Any] | None = None, *, notify: bool = False) -> Any:
        """Один JSON-RPC обмін без локу/handshake — викликати лише з-під self._lock."""
        if notify:
            await self._write_message({"jsonrpc": "2.0", "method": method, "params": params or {}})
            return None
        self._req_id += 1
        rid = self._req_id
        await self._write_message({"jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}})
        while True:
            resp = await self._read_message()
            if resp.get("id") == rid:
                if "error" in resp:
                    raise RuntimeError(str(resp["error"]))
                return resp.get("result")
            # чужий id / нотифікація сервера — пропускаємо

    async def _rpc(self, method: str, params: dict[str, Any] | None = None) -> Any:
        async with self._lock:
            await self._ensure()
            return await self._rpc_raw(method, params)

    async def list_tools(self) -> list[dict[str, Any]]:
        result = await self._rpc("tools/list")
        tools = result.get("tools") if isinstance(result, dict) else []
        return tools if isinstance(tools, list) else []

    async def call_tool(self, tool: str, arguments: dict[str, Any]) -> str:
        result = await self._rpc("tools/call", {"name": tool, "arguments": arguments or {}})
        if not isinstance(result, dict):
            return str(result)
        content = result.get("content")
        if isinstance(content, list):
            parts = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(str(block.get("text") or ""))
            text = "\n".join(parts)
        else:
            text = json.dumps(result, ensure_ascii=False)
        if len(text) > settings.fetch_max_chars:
            text = text[: settings.fetch_max_chars] + " …[truncated]"
        return text or "(empty MCP result)"

    async def close(self) -> None:
        if self._proc and self._proc.returncode is None:
            self._proc.terminate()
            try:
                await asyncio.wait_for(self._proc.wait(), timeout=2)
            except TimeoutError:
                self._proc.kill()
        self._proc = None


async def _session(name: str) -> _McpSession:
    if name not in _sessions:
        _sessions[name] = _McpSession(_server_cfg(name))
    return _sessions[name]


async def list_servers_status() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for cfg in _load_servers():
        name = str(cfg["name"])
        item: dict[str, Any] = {"name": name, "command": cfg.get("command"), "connected": False, "tools": 0}
        try:
            sess = await _session(name)
            tools = await sess.list_tools()
            item["connected"] = True
            item["tools"] = len(tools)
        except Exception as exc:  # noqa: BLE001
            item["error"] = str(exc)[:200]
        out.append(item)
    return out


async def list_tools(server: str) -> list[dict[str, Any]]:
    sess = await _session(server)
    return await sess.list_tools()


async def call_tool(server: str, tool: str, arguments: dict[str, Any]) -> str:
    _server_cfg(server)  # allowlist check
    sess = await _session(server)
    return await sess.call_tool(tool, arguments or {})
