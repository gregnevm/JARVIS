"""Короткий контекст останніх повідомлень треду (short-term з Memory)."""
from __future__ import annotations

from .memory_client import MemoryClient

_MAX_MSG = 280
_MAX_TOTAL = 2000


async def build_thread_context(mem: MemoryClient, user_id: int, *, limit: int = 12) -> str:
    msgs = await mem.history(user_id, limit=limit)
    if not msgs:
        return ""
    lines: list[str] = []
    total = 0
    for m in msgs[-limit:]:
        role = str(m.get("role", "user"))
        tag = "U" if role == "user" else "A" if role == "assistant" else role[:1]
        body = str(m.get("content", "")).replace("\n", " ").strip()[:_MAX_MSG]
        if not body:
            continue
        line = f"{tag}: {body}"
        if total + len(line) > _MAX_TOTAL:
            break
        lines.append(line)
        total += len(line)
    if not lines:
        return ""
    return " Останні репліки: " + " | ".join(lines)
