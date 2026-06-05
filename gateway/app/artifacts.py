"""Канвас Mini App на gateway: парсинг [[app:...]] + той самий Redis-протокол, що в tools."""
from __future__ import annotations

import json
import logging
import re
import time
import uuid
from dataclasses import dataclass
from typing import Any

import redis.asyncio as aioredis

logger = logging.getLogger("jarvis.gateway.artifacts")

# Синхронізовано з tools/app/artifacts.py
ALLOWED_KINDS = {"html", "markdown", "url", "image", "code"}
ARTIFACT_TTL = 6 * 3600
MAX_HISTORY = 20
_MAX_CONTENT = 200_000

# [[app:kind|content]] або [[app:kind|title|content]] (title без '|')
_APP_DIRECTIVE_RE = re.compile(
    r"\[\[\s*app\s*:\s*(\w+)\s*\|(?:([^|]*)\|)?(.*?)\s*\]\]",
    re.DOTALL | re.IGNORECASE,
)


def current_key(user_id: int) -> str:
    return f"artifact:{int(user_id)}"


def list_key(user_id: int) -> str:
    return f"artifacts:{int(user_id)}"


@dataclass(frozen=True)
class AppDirective:
    kind: str
    content: str
    title: str = ""


def parse_app_directives(text: str) -> tuple[str, list[AppDirective]]:
    """Вирізає [[app:kind|title|content]] з тексту відповіді."""
    if not text or "[[app" not in text.lower():
        return (text or "").strip(), []

    directives: list[AppDirective] = []

    def _take(match: re.Match[str]) -> str:
        kind = match.group(1).lower()
        if kind not in ALLOWED_KINDS:
            return match.group(0)
        title = (match.group(2) or "").strip()
        content = (match.group(3) or "").strip()
        if not content:
            return ""
        directives.append(AppDirective(kind=kind, content=content, title=title))
        return ""

    clean = _APP_DIRECTIVE_RE.sub(_take, text)
    clean = re.sub(r"\n{3,}", "\n\n", clean).strip()
    return clean, directives


def _validate(kind: str, content: str, title: str) -> str | dict[str, Any]:
    kind = kind.strip().lower()
    content = content.strip()
    title = title.strip()[:120]
    if kind not in ALLOWED_KINDS:
        return f"bad kind: {kind}"
    if not content:
        return "empty content"
    if kind in ("url", "image") and not content.startswith(("http://", "https://", "data:")):
        return "bad url"
    if len(content) > _MAX_CONTENT:
        return "too large"
    return {
        "id": uuid.uuid4().hex[:8],
        "ts": int(time.time()),
        "kind": kind,
        "title": title,
        "content": content,
    }


async def push_record(redis: aioredis.Redis, user_id: int, record: dict[str, Any]) -> None:
    payload = json.dumps(record, ensure_ascii=False)
    uid = int(user_id)
    await redis.set(current_key(uid), payload, ex=ARTIFACT_TTL)
    await redis.lpush(list_key(uid), payload)
    await redis.ltrim(list_key(uid), 0, MAX_HISTORY - 1)
    await redis.expire(list_key(uid), ARTIFACT_TTL)


async def store_directives(
    redis: aioredis.Redis, user_id: int, directives: list[AppDirective]
) -> None:
    for d in directives:
        built = _validate(d.kind, d.content, d.title)
        if isinstance(built, str):
            logger.warning("skip app directive: %s", built)
            continue
        try:
            await push_record(redis, user_id, built)
        except Exception as exc:  # noqa: BLE001
            logger.warning("app artifact push failed: %s", exc)


async def apply_app_directives(
    redis: aioredis.Redis, user_id: int, text: str
) -> str:
    """Вирізає app-директиви, пушить у Redis. Повертає чистий текст."""
    clean, directives = parse_app_directives(text)
    if directives:
        await store_directives(redis, user_id, directives)
    return clean


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
