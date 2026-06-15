"""Planning Mode (P3) — structured plans у Redis з approve/execute flow."""
from __future__ import annotations

import uuid
from typing import Any

from .redis_store import RedisIndexedStore, now_ts

_STORE = RedisIndexedStore(
    key_prefix="jarvis:plan:",
    index_prefix="jarvis:plan:index:",
    ttl=86400,
    history_max=50,
)
_MAX_STEPS = 8

_VALID_STATUS = frozenset(
    {"draft", "pending", "approved", "executing", "done", "cancelled", "denied"}
)


async def get_plan(plan_id: str, user_id: int | None = None) -> dict[str, Any] | None:
    return await _STORE.get(plan_id, owner_user_id=user_id)


def _normalize_steps(steps: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for i, step in enumerate(steps[:_MAX_STEPS], start=1):
        if isinstance(step, str):
            out.append({"id": i, "title": step[:200], "detail": step[:2000], "status": "pending"})
            continue
        if not isinstance(step, dict):
            continue
        title = str(step.get("title") or step.get("name") or f"Крок {i}")[:200]
        detail = str(step.get("detail") or step.get("description") or title)[:2000]
        out.append({"id": int(step.get("id") or i), "title": title, "detail": detail, "status": "pending"})
    return out


async def create_plan(
    user_id: int,
    *,
    summary: str,
    steps: list[Any],
    risks: list[Any] | None = None,
    source_text: str = "",
    status: str = "pending",
) -> dict[str, Any]:
    plan_id = uuid.uuid4().hex[:12]
    now = now_ts()
    rec: dict[str, Any] = {
        "id": plan_id,
        "user_id": int(user_id),
        "status": status if status in _VALID_STATUS else "pending",
        "summary": (summary or "")[:4000],
        "steps": _normalize_steps(steps or []),
        "risks": [str(r)[:500] for r in (risks or [])[:10]],
        "source_text": (source_text or "")[:4000],
        "current_step": 0,
        "result": "",
        "created_at": now,
        "updated_at": now,
    }
    await _STORE.save(rec)
    await _STORE.index_append(user_id, plan_id)
    return rec


async def list_plans(user_id: int, limit: int = 20) -> list[dict[str, Any]]:
    return await _STORE.list_for_user(user_id, limit)


async def approve_plan(plan_id: str, user_id: int) -> dict[str, Any] | None:
    rec = await get_plan(plan_id)
    if rec is None or int(rec.get("user_id", 0)) != int(user_id):
        return None
    if rec.get("status") not in ("pending", "draft"):
        return rec
    rec["status"] = "approved"
    await _STORE.save(rec)
    return rec


async def deny_plan(plan_id: str, user_id: int) -> dict[str, Any] | None:
    rec = await get_plan(plan_id)
    if rec is None or int(rec.get("user_id", 0)) != int(user_id):
        return None
    if rec.get("status") not in ("pending", "draft", "approved"):
        return rec
    rec["status"] = "denied"
    await _STORE.save(rec)
    return rec


async def set_executing(plan_id: str) -> dict[str, Any] | None:
    rec = await get_plan(plan_id)
    if rec is None:
        return None
    rec["status"] = "executing"
    await _STORE.save(rec)
    return rec


async def advance_step(plan_id: str, step_index: int, *, status: str = "done") -> dict[str, Any] | None:
    rec = await get_plan(plan_id)
    if rec is None:
        return None
    steps = rec.get("steps")
    if not isinstance(steps, list) or step_index < 0 or step_index >= len(steps):
        return rec
    step = steps[step_index]
    if isinstance(step, dict):
        step["status"] = status
    rec["current_step"] = step_index + 1
    await _STORE.save(rec)
    return rec


async def finish_plan(plan_id: str, *, result: str = "", status: str = "done") -> dict[str, Any] | None:
    rec = await get_plan(plan_id)
    if rec is None:
        return None
    rec["status"] = status if status in _VALID_STATUS else "done"
    rec["result"] = (result or "")[:8000]
    await _STORE.save(rec)
    return rec
