"""Task queue — багатокрокові remote-задачі з прогресом."""
from __future__ import annotations

import json
import time
from typing import Any

import redis.asyncio as aioredis

from .config import settings

_QUEUE_PREFIX = "jarvis:tasks:"
_ACTIVE_PREFIX = "jarvis:tasks:active:"
_TTL = 86400

_redis: aioredis.Redis | None = None


def _client() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis


def _qkey(user_id: int) -> str:
    return f"{_QUEUE_PREFIX}{int(user_id)}"


def _akey(user_id: int) -> str:
    return f"{_ACTIVE_PREFIX}{int(user_id)}"


async def enqueue(user_id: int, goal: str, steps: list[str] | None = None) -> dict[str, Any]:
    task = {
        "goal": goal.strip()[:500],
        "steps": steps or [],
        "done": [],
        "created": int(time.time()),
        "status": "active",
    }
    await _client().setex(_akey(user_id), _TTL, json.dumps(task, ensure_ascii=False))
    await _client().rpush(_qkey(user_id), goal.strip()[:500])
    await _client().expire(_qkey(user_id), _TTL)
    return task


async def get_active(user_id: int) -> dict[str, Any] | None:
    raw = await _client().get(_akey(user_id))
    if not raw:
        return None
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None


async def mark_step_done(user_id: int, step: str) -> dict[str, Any] | None:
    task = await get_active(user_id)
    if not task:
        return None
    raw_done = task.get("done")
    done: list[str] = [str(x) for x in raw_done] if isinstance(raw_done, list) else []
    done.append(step[:200])
    task["done"] = done
    await _client().setex(_akey(user_id), _TTL, json.dumps(task, ensure_ascii=False))
    return task


async def cancel(user_id: int) -> bool:
    await _client().delete(_akey(user_id), _qkey(user_id))
    return True


async def list_tasks(user_id: int) -> str:
    task = await get_active(user_id)
    if not task:
        return "Немає активних задач."
    done = task.get("done") or []
    lines = [f"🎯 {task.get('goal', '?')}", f"Статус: {task.get('status', 'active')}"]
    if done:
        lines.append("Виконано:")
        lines.extend(f"  ✅ {s}" for s in done[-10:])
    return "\n".join(lines)
