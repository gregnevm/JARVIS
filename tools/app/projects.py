"""Активний проєкт користувача (P1) — стан у Redis, резолв через memory-сервіс.

`jarvis:project:{user_id}` → project_id. Агент читає це на старті turn, щоб
скоупити RAG (project_id) і вкласти system_prompt проєкту. Видалений/чужий проєкт
самоочищається (fail-safe → загальний контекст).
"""
from __future__ import annotations

import logging
from typing import Any

from .redis_util import get_redis

logger = logging.getLogger("jarvis.tools.projects")

_KEY = "jarvis:project:"


async def active_project_id(user_id: int) -> int | None:
    try:
        raw = await get_redis().get(f"{_KEY}{int(user_id)}")
    except Exception as exc:  # noqa: BLE001 — стан проєкту не критичний
        logger.debug("active project read failed: %s", exc)
        return None
    if not raw:
        return None
    try:
        return int(raw)
    except (ValueError, TypeError):
        return None


async def set_active_project(user_id: int, project_id: int | None) -> None:
    r = get_redis()
    key = f"{_KEY}{int(user_id)}"
    try:
        if project_id is None:
            await r.delete(key)
        else:
            await r.set(key, str(int(project_id)))
    except Exception as exc:  # noqa: BLE001
        logger.warning("active project set failed: %s", exc)


def project_prompt_block(project: dict[str, Any]) -> str:
    """Фрагмент system-промпта для активного проєкту."""
    name = str(project.get("name") or "").strip()
    sp = str(project.get("system_prompt") or "").strip()
    block = f" Активний проєкт: «{name}»." if name else ""
    if sp:
        block += f" Інструкції проєкту: {sp}"
    files_part = project_files_block(project.get("files_content") or [])
    if files_part:
        block += files_part
    return block


def project_files_block(files: list[Any]) -> str:
    """Форматує вміст project_files для system prompt."""
    if not files:
        return ""
    parts: list[str] = [" Файли проєкту:"]
    for f in files:
        if not isinstance(f, dict):
            continue
        name = str(f.get("name") or "file").strip()
        content = str(f.get("content") or "").strip()
        if not content:
            continue
        parts.append(f" --- {name} ---\n{content}")
    return "".join(parts) if len(parts) > 1 else ""
