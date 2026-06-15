"""MCP gateway endpoints."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from ..schemas import McpCallRequest


def register(router: APIRouter) -> None:
    @router.get("/mcp/servers")
    async def mcp_servers_ep() -> dict[str, Any]:
        from .. import mcp_gateway

        return {"servers": await mcp_gateway.list_servers_status()}

    @router.get("/mcp/{server_name}/tools")
    async def mcp_tools_ep(server_name: str) -> dict[str, Any]:
        from .. import mcp_gateway

        try:
            tools = await mcp_gateway.list_tools(server_name)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"server": server_name, "tools": tools}

    @router.post("/mcp/call")
    async def mcp_call_ep(req: McpCallRequest) -> dict[str, Any]:
        from .. import mcp_gateway

        try:
            text = await mcp_gateway.call_tool(req.server, req.tool, req.arguments)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"text": text}
