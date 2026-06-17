"""Tools REST route modules — композиція замість моноліту main.py."""
from __future__ import annotations

from fastapi import APIRouter, FastAPI

from . import (
    agent,
    bgjobs,
    coding,
    computer,
    connectors,
    core,
    cursor,
    dataset,
    hooks,
    improve,
    lora,
    mcp,
    orchestrator,
    research,
    scheduler,
    skills,
    subagents,
    teams,
    tools_basic,
)

_ROUTE_MODULES = (
    core,
    tools_basic,
    agent,
    computer,
    dataset,
    scheduler,
    bgjobs,
    coding,
    research,
    mcp,
    connectors,
    skills,
    subagents,
    hooks,
    teams,
    orchestrator,
    improve,
    lora,
    cursor,
)


def mount_routes(app: FastAPI) -> None:
    """Реєструє всі Tools endpoints на app (URL без змін)."""
    router = APIRouter()
    for mod in _ROUTE_MODULES:
        mod.register(router)
    app.include_router(router)
