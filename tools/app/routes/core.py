"""Core endpoints: health, status, dashboard, mode."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from ..config import settings
from ..runtime import clear_agent_mode, get_agent_mode, set_agent_mode
from ..schemas import ModeRequest


def register(router: APIRouter) -> None:
    @router.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @router.get("/status")
    async def status_ep(request: Request) -> dict[str, Any]:
        return await request.app.state.jarvis.dashboard()

    @router.get("/dashboard")
    async def dashboard_ep(request: Request) -> dict[str, Any]:
        return await request.app.state.jarvis.dashboard()

    @router.post("/mode")
    async def set_mode_ep(req: ModeRequest) -> dict[str, str]:
        m = req.mode.lower().strip()
        if m == "computer" and not settings.enable_computer_use:
            raise HTTPException(
                status_code=400,
                detail="Computer Use вимкнено (ENABLE_COMPUTER_USE=false).",
            )
        try:
            set_agent_mode(req.mode)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"mode": get_agent_mode(), "status": "ok"}

    @router.delete("/mode")
    async def reset_mode_ep() -> dict[str, str]:
        return {"mode": clear_agent_mode(), "status": "reset"}
