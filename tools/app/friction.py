"""Friction-телеметрія (SY-1 «самозарядний backlog», SYNERGY_ROADMAP).

Реальний біль рантайму → паспорти `kind:friction` у `context_events`: plan-фаза
kaizen читає їх tag-запитом і ставить поруч із roadmap-кандидатами — backlog
поповнюється з телеметрії, а не лише з ручного підкидання задач (анти-`backlog_dry`).

Продюсер fast-path (P6: summary без LLM), fire-and-forget (нуль latency у
тул-шляху), best-effort (збій телеметрії ніколи не ламає хід агента).
Анти-leak: у паспорт іде лише ТИП помилки і лічильники — ані сирих аргументів,
ані трейсбеків (клас token/PII-leak, та сама дисципліна, що в ingest-логах).
За прапором `ENABLE_FRICTION_TELEMETRY` (дефолт off, ADR-008).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from .config import settings
from .memory_client import MemoryClient

logger = logging.getLogger("jarvis.tools.friction")

REASON_TOOL_FAIL = "tool_fail"
REASON_UNKNOWN_TOOL = "unknown_tool"
REASON_LOOP_EXHAUSTED = "loop_exhausted"

_SUMMARY_MAX = 300

_memory: MemoryClient | None = None
_tasks: set[asyncio.Task[None]] = set()


def _client() -> MemoryClient:
    global _memory
    if _memory is None:
        _memory = MemoryClient(settings.memory_url)
    return _memory


def reset_client() -> None:
    """Для тестів: скинути лінивий MemoryClient (новий підхопить свіжі settings)."""
    global _memory
    _memory = None


def record_friction(user_id: int, reason: str, *, summary: str, tool: str = "") -> None:
    """Планує ingest паспорта `kind:friction` у фоні; сам виклик нічого не чекає.

    `user_id == 0` (анонімні/системні виклики) пропускаємо — паспорт без власника
    не має партиції в сторі.
    """
    if not settings.enable_friction_telemetry or not user_id:
        return
    tags = [f"reason:{reason}", "module:tools"]
    if tool:
        tags.append(f"tool:{tool}")
    store: dict[str, Any] = {
        "user_id": user_id,
        "kind": "friction",
        "summary": summary[:_SUMMARY_MAX],
        "tags": tags,
        "source": "agent_loop",
        "sensitivity": "personal",
    }
    try:
        task = asyncio.create_task(_ingest(store))
    except RuntimeError:  # немає запущеного loop — телеметрія не варта падіння
        logger.debug("friction: no running loop, event dropped")
        return
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


async def drain() -> None:
    """Дочекатися запланованих ingest-ів (тести/shutdown)."""
    while _tasks:
        await asyncio.gather(*list(_tasks), return_exceptions=True)


async def _ingest(store: dict[str, Any]) -> None:
    try:
        await _client().context_ingest(store)
    except Exception as exc:  # noqa: BLE001 — best-effort за визначенням
        logger.debug("friction ingest failed: %s", exc)
