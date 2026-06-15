"""Background agent jobs (P2) — окремо від macro scheduler (`jobs.py` / `jarvis:jobs` ZSET)."""
from __future__ import annotations

import uuid
from typing import Any

from jarvis_core.bg_jobs import normalize_payload

from .redis_store import RedisIndexedStore, now_ts
from .redis_util import get_redis

_STORE = RedisIndexedStore(
    key_prefix="jarvis:bgjob:",
    index_prefix="jarvis:bgjob:index:",
    ttl=None,
    history_max=100,
)
_QUEUE = "jarvis:bgjob:queue"


async def get_job(job_id: str, user_id: int | None = None) -> dict[str, Any] | None:
    return await _STORE.get(job_id, owner_user_id=user_id)


async def create_job(user_id: int, text: str, mode: str = "auto") -> dict[str, Any]:
    return await create_typed_job(
        user_id,
        "agent_turn",
        {"text": text, "mode": (mode or "auto").strip().lower() or "auto"},
    )


async def create_typed_job(user_id: int, job_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    job_type = (job_type or "agent_turn").strip()
    payload = normalize_payload(job_type, payload)

    job_id = uuid.uuid4().hex[:12]
    now = now_ts()
    rec: dict[str, Any] = {
        "id": job_id,
        "user_id": int(user_id),
        "type": job_type,
        "status": "queued",
        "progress": 0,
        "payload": payload,
        "result": "",
        "error": "",
        "created_at": now,
        "updated_at": now,
    }
    r = get_redis()
    await _STORE.save(rec)
    await r.lpush(_QUEUE, job_id)
    await _STORE.index_append(user_id, job_id)
    return rec


async def create_research_job(user_id: int, query: str, max_hops: int = 3) -> dict[str, Any]:
    return await create_typed_job(
        user_id,
        "deep_research",
        {"query": query, "max_hops": max_hops},
    )


async def create_subagent_job(
    user_id: int,
    task: str,
    *,
    budget_iters: int = 3,
    run_id: str = "",
    mode: str = "agent",
) -> dict[str, Any]:
    return await create_typed_job(
        user_id,
        "subagent",
        {
            "task": task,
            "budget_iters": budget_iters,
            "run_id": run_id,
            "mode": mode,
        },
    )


async def create_team_job(
    user_id: int,
    task: str,
    *,
    team_id: str = "",
    budget_per_role: int = 3,
    roles: list[str] | None = None,
) -> dict[str, Any]:
    return await create_typed_job(
        user_id,
        "agent_team",
        {
            "task": task,
            "team_id": team_id,
            "budget_per_role": budget_per_role,
            "roles": roles or [],
        },
    )


async def create_orchestrator_job(
    user_id: int,
    task: str,
    *,
    run_id: str = "",
    worker_budget: int = 5,
    max_revisions: int = 1,
) -> dict[str, Any]:
    return await create_typed_job(
        user_id,
        "orchestrator",
        {
            "task": task,
            "run_id": run_id,
            "worker_budget": worker_budget,
            "max_revisions": max_revisions,
        },
    )


async def update_progress(job_id: str, progress: int, message: str = "") -> dict[str, Any] | None:
    rec = await get_job(job_id)
    if rec is None:
        return None
    rec["progress"] = max(0, min(int(progress), 99))
    if message:
        rec["progress_msg"] = str(message)[:500]
    await _STORE.save(rec)
    return rec


async def list_jobs(user_id: int, limit: int = 20) -> list[dict[str, Any]]:
    return await _STORE.list_for_user(user_id, limit)


async def cancel_job(job_id: str, user_id: int) -> bool:
    rec = await get_job(job_id)
    if rec is None or int(rec.get("user_id", 0)) != int(user_id):
        return False
    if rec.get("status") != "queued":
        return False
    rec["status"] = "cancelled"
    await _STORE.save(rec)
    await get_redis().lrem(_QUEUE, 0, job_id)
    return True


async def dequeue_job() -> dict[str, Any] | None:
    """FIFO dequeue; пропускає скасовані."""
    r = get_redis()
    for _ in range(20):
        jid = await r.rpop(_QUEUE)
        if not jid:
            return None
        rec = await get_job(str(jid))
        if rec is None:
            continue
        if rec.get("status") != "queued":
            continue
        rec["status"] = "running"
        rec["progress"] = 10
        await _STORE.save(rec)
        return rec
    return None


async def finish_job(
    job_id: str,
    *,
    result: str = "",
    error: str = "",
    status: str = "done",
) -> dict[str, Any] | None:
    rec = await get_job(job_id)
    if rec is None:
        return None
    rec["status"] = status
    rec["progress"] = 100
    rec["result"] = (result or "")[:8000]
    rec["error"] = (error or "")[:2000]
    await _STORE.save(rec)
    return rec
