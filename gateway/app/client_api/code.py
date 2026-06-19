"""Code — dispatch задач кодування (всі режими) для будь-якого клієнта.

За замовчуванням — РІДНИЙ coding-агент (repo-aware diff-edit/тести/рефактор через
computer-use + coding tools, S1 локально). Дія виконується на PC-ендпоінті (remote dispatch
через наявний computer-use). Опційний Claude-міст — за прапором (cloud, явний opt-in, не дефолт).
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from jarvis_core.context import RequestContext

from .._helpers import require_mode
from ..agent_payload import build_agent_payload
from ..config import settings
from .deps import resolve_client_context

logger = logging.getLogger("jarvis.gateway.client_api.code")


class CodeTask(BaseModel):
    text: str
    target: str = "local"  # local (рідний агент) | claude (опційний міст, за прапором)


def _uid(ctx: RequestContext) -> int:
    if ctx.legacy_uid is not None:
        return int(ctx.legacy_uid)
    try:
        return int(ctx.user_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="no numeric user id")


def register(router: APIRouter) -> None:
    @router.get("/code/modes")
    async def code_modes() -> dict[str, Any]:
        """Доступні режими/бекенди кодування + стан прапорів.

        `local`/`claude` — валідні REST `target` для `/code/task`. `bridges`
        (cursor/continue) — окрема категорія: вони дispatch-аться через Telegram-флоу
        (`/cursor`), НЕ є `target`-ами `/code/task` (тому validator там приймає лише
        `{local, claude}`).
        """
        return {
            "local": {"available": True, "desc": "рідний coding-агент (repo tools, diff-edit, тести)"},
            "claude": {"available": bool(getattr(settings, "enable_claude_code_bridge", False)),
                       "desc": "Claude-міст (cloud, opt-in за ENABLE_CLAUDE_CODE_BRIDGE)"},
            "bridges": {"cursor": getattr(settings, "cursor_tasks_enabled", False),
                        "continue": getattr(settings, "enable_continue_dev", False),
                        "via": "telegram", "rest_target": False},
        }

    @router.post("/code/task")
    async def code_task(body: CodeTask, request: Request,
                        ctx: RequestContext = Depends(resolve_client_context)) -> dict[str, Any]:
        """Dispatch задачі кодування. local → рідний агент (computer-режим із coding tools)."""
        text = (body.text or "").strip()
        if not text:
            raise HTTPException(status_code=400, detail="text required")
        # Fail-fast (P2): лише задокументовані таргети; раніше невідомий target
        # (напр. "cursor") тихо падав у local-гілку замість 400.
        target = require_mode(body.target or "local", {"local", "claude"}, field="target")
        if target == "claude" and not getattr(settings, "enable_claude_code_bridge", False):
            raise HTTPException(status_code=503,
                                detail="Claude bridge disabled (set ENABLE_CLAUDE_CODE_BRIDGE)")
        uid = _uid(ctx)
        # Рідний шлях: агент у computer-режимі задіює coding tools (repo_*/code_edit) на PC.
        payload = build_agent_payload(user_id=uid, chat_id=uid, text=text,
                                      source="code", mode="computer")
        reply = await request.app.state.tools.process(payload)
        return {"reply": reply, "target": target}
