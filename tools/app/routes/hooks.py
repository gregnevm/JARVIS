"""Hooks endpoints."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter


def register(router: APIRouter) -> None:
    @router.get("/hooks/status")
    async def hooks_status_ep() -> dict[str, Any]:
        from .. import hooks

        return hooks.hook_status()

    @router.post("/hooks/reload")
    async def hooks_reload_ep() -> dict[str, Any]:
        from .. import hooks

        hooks.reload_hooks()
        return hooks.hook_status()
