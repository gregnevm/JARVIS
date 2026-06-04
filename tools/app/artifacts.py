"""Канвас Mini App: артефакти в Redis (спільний із gateway).

Інструмент show_in_app і директива [[app:kind|title|content]] пишуть сюди.
Ключі: artifact:<user_id> — поточний; artifacts:<user_id> — LIST історії (≤20).
"""
from __future__ import annotations

import json
import time
import uuid
from typing import Any

import redis.asyncio as aioredis

from .config import settings

ALLOWED_KINDS = {"html", "markdown", "url", "image", "code"}

ARTIFACT_TTL = 6 * 3600
MAX_HISTORY = 20
_MAX_CONTENT = 200_000

_redis: aioredis.Redis | None = None


def current_key(user_id: int) -> str:
    return f"artifact:{int(user_id)}"


def list_key(user_id: int) -> str:
    return f"artifacts:{int(user_id)}"


def _client() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis


async def aclose() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None


def validate_artifact(kind: str, content: str, title: str = "") -> str | dict[str, Any]:
    """Повертає запис {id, ts, kind, title, content} або текст помилки."""
    kind = (kind or "").strip().lower()
    content = (content or "").strip()
    title = (title or "").strip()[:120]
    if kind not in ALLOWED_KINDS:
        return f"Невідомий тип контенту: {kind}. Доступні: {', '.join(sorted(ALLOWED_KINDS))}."
    if not content:
        return "Порожній контент — нема чого показувати."
    if kind in ("url", "image") and not content.startswith(("http://", "https://", "data:")):
        return "Для url/image потрібне http(s) або data: посилання."
    if len(content) > _MAX_CONTENT:
        return f"Завеликий контент (>{_MAX_CONTENT} символів)."
    return {
        "id": uuid.uuid4().hex[:8],
        "ts": int(time.time()),
        "kind": kind,
        "title": title,
        "content": content,
    }


async def push_record(redis: aioredis.Redis, user_id: int, record: dict[str, Any]) -> None:
    """Записує артефакт як поточний + на початок історії."""
    payload = json.dumps(record, ensure_ascii=False)
    uid = int(user_id)
    await redis.set(current_key(uid), payload, ex=ARTIFACT_TTL)
    await redis.lpush(list_key(uid), payload)
    await redis.ltrim(list_key(uid), 0, MAX_HISTORY - 1)
    await redis.expire(list_key(uid), ARTIFACT_TTL)


async def push_artifact(
    redis: aioredis.Redis, user_id: int, kind: str, content: str, title: str = ""
) -> str:
    """Зберігає артефакт. Повертає ok-повідомлення або текст помилки."""
    built = validate_artifact(kind, content, title)
    if isinstance(built, str):
        return built
    try:
        await push_record(redis, user_id, built)
    except Exception as exc:  # noqa: BLE001
        return f"Не вдалося показати у застосунку: {exc}"
    label = f" «{built['title']}»" if built.get("title") else ""
    return f"Показав{label} у застосунку (Канвас) ✅. Відкрий Mini App, щоб переглянути."


async def show_in_app(user_id: int, kind: str, content: str, title: str = "") -> str:
    return await push_artifact(_client(), user_id, kind, content, title)


async def get_current(redis: aioredis.Redis, user_id: int) -> dict[str, Any] | None:
    raw = await redis.get(current_key(user_id))
    if not raw:
        return None
    try:
        rec = json.loads(raw)
        return rec if isinstance(rec, dict) else None
    except (ValueError, TypeError):
        return None


async def list_history(redis: aioredis.Redis, user_id: int) -> list[dict[str, Any]]:
    try:
        raw = await redis.lrange(list_key(user_id), 0, MAX_HISTORY - 1)
    except Exception:  # noqa: BLE001
        return []
    out: list[dict[str, Any]] = []
    for item in raw:
        try:
            rec = json.loads(item)
            if isinstance(rec, dict):
                out.append(rec)
        except (ValueError, TypeError):
            continue
    return out


async def clear_user(redis: aioredis.Redis, user_id: int) -> None:
    uid = int(user_id)
    await redis.delete(current_key(uid), list_key(uid))
