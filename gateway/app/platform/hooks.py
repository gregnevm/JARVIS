"""P10 Platform Hooks status."""
from __future__ import annotations

from fastapi import APIRouter

from .proxy import register_tools_get


def register(router: APIRouter) -> None:
    register_tools_get(router, "/platform/api/hooks", "hooks_status")
