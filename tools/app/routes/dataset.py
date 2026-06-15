"""Dataset export and reminders ICS."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from ..config import settings


def register(router: APIRouter) -> None:
    @router.get("/reminders/ics")
    async def reminders_ics_ep(user_id: int) -> Any:
        from ..reminders import export_ics

        body = await export_ics(user_id)
        if not body.strip():
            raise HTTPException(status_code=404, detail="no reminders")
        return Response(
            content=body,
            media_type="text/calendar; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="jarvis-reminders.ics"'},
        )

    @router.get("/dataset/stats")
    async def dataset_stats_ep(user_id: int | None = None) -> dict[str, Any]:
        from ..train_scheduler import retrain_status

        return retrain_status(user_id)

    @router.post("/dataset/export/mark")
    async def dataset_export_mark_ep(user_id: int | None = None) -> dict[str, Any]:
        from ..train_scheduler import mark_exported

        return mark_exported(user_id)

    @router.post("/dataset/export/sharegpt")
    async def dataset_export_ep(user_id: int | None = None, limit: int = 0) -> dict[str, Any]:
        from ..dataset_export import write_sharegpt_jsonl
        from ..train_scheduler import mark_exported

        dest = Path(settings.data_dir) / "twin" / "export" / "sharegpt.jsonl"
        info = write_sharegpt_jsonl(dest, user_id=user_id, limit=limit)
        info["scheduler"] = mark_exported(user_id)
        return info
