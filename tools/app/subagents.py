"""Subagents (P8) — spawn із budget iters, async через bg jobs."""
from __future__ import annotations

import uuid
from typing import Any

from .redis_store import RedisIndexedStore, now_ts

_STORE = RedisIndexedStore(
    key_prefix="jarvis:subagent:",
    index_prefix="jarvis:subagent:index:",
    ttl=86400,
    history_max=50,
)


async def get_run(run_id: str) -> dict[str, Any] | None:
    return await _STORE.get(run_id)


async def create_spawn(
    user_id: int,
    task: str,
    *,
    budget_iters: int = 3,
    mode: str = "agent",
) -> dict[str, Any]:
    task = (task or "").strip()
    if not task:
        raise ValueError("task required")
    budget_iters = max(1, min(int(budget_iters), 8))
    run_id = uuid.uuid4().hex[:12]
    now = now_ts()
    rec: dict[str, Any] = {
        "id": run_id,
        "user_id": int(user_id),
        "status": "queued",
        "task": task[:4000],
        "budget_iters": budget_iters,
        "mode": (mode or "agent").strip().lower(),
        "result": "",
        "error": "",
        "iters_used": 0,
        "created_at": now,
        "updated_at": now,
    }
    await _STORE.save(rec)
    await _STORE.index_append(user_id, run_id)
    return rec


async def list_runs(user_id: int, limit: int = 20) -> list[dict[str, Any]]:
    return await _STORE.list_for_user(user_id, limit)


async def mark_running(run_id: str) -> dict[str, Any] | None:
    rec = await get_run(run_id)
    if rec is None:
        return None
    rec["status"] = "running"
    await _STORE.save(rec)
    return rec


async def finish_run(
    run_id: str,
    *,
    result: str = "",
    error: str = "",
    iters_used: int = 0,
    status: str = "done",
) -> dict[str, Any] | None:
    rec = await get_run(run_id)
    if rec is None:
        return None
    rec["status"] = status
    rec["result"] = (result or "")[:8000]
    rec["error"] = (error or "")[:2000]
    rec["iters_used"] = int(iters_used)
    await _STORE.save(rec)
    return rec
