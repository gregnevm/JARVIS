"""External connectors status."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter


def register(router: APIRouter) -> None:
    @router.get("/connectors/status")
    async def connectors_status_ep() -> dict[str, Any]:
        from ..connectors import calendar, notion, slack

        return {
            "notion": {"configured": notion.is_configured()},
            "slack": {"configured": slack.is_configured()},
            "calendar": {"configured": calendar.is_configured()},
        }
