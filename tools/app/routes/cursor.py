"""Cursor task endpoints."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from ..schemas import CursorTaskBody
from ._helpers import require_text


def register(router: APIRouter) -> None:
    @router.post("/cursor/tasks")
    async def cursor_tasks_submit(body: CursorTaskBody) -> dict[str, Any]:
        from .. import cursor_tasks

        task = require_text(body.task)
        return await cursor_tasks.submit(body.user_id, task, async_mode=body.async_mode)

    @router.post("/cursor/tasks/run")
    async def cursor_tasks_run(body: CursorTaskBody) -> dict[str, Any]:
        from .. import cursor_tasks

        task = require_text(body.task)
        result = await cursor_tasks.execute(task, user_id=body.user_id)
        result["text"] = cursor_tasks.format_result(result)
        return result
