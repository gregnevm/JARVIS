"""Macro scheduler: /tasks, /jobs (ZSET)."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter


def register(router: APIRouter) -> None:
    @router.get("/tasks")
    async def tasks_list_ep(user_id: int) -> dict[str, str]:
        from ..tasks import list_tasks

        return {"text": await list_tasks(user_id)}

    @router.delete("/tasks")
    async def tasks_cancel_ep(user_id: int) -> dict[str, str]:
        from ..tasks import cancel

        await cancel(user_id)
        return {"status": "cancelled"}

    @router.get("/jobs")
    async def jobs_list_ep(user_id: int) -> dict[str, str]:
        from ..jobs import list_jobs

        return {"text": await list_jobs(user_id)}

    @router.get("/jobs/due")
    async def jobs_due_ep() -> dict[str, Any]:
        from ..jobs import due_jobs

        return {"jobs": await due_jobs()}
