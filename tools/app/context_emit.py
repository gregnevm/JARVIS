"""Fire-and-forget ingest контекст-паспортів із tools (SY-1 friction, SY-5 confirm).

Спільна обв'язка для телеметрійних продюсерів: лінивий MemoryClient, фонова
відправка без очікування (нуль latency у гарячому шляху), best-effort —
збій стору ніколи не ламає викликача. Store-dict мусить нести `user_id`
(партиція) і `kind`; теги нормалізує memory-роут (P10-інваріант).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from .config import settings
from .memory_client import MemoryClient

logger = logging.getLogger("jarvis.tools.context_emit")

_memory: MemoryClient | None = None
_tasks: set[asyncio.Task[None]] = set()


def _client() -> MemoryClient:
    global _memory
    if _memory is None:
        _memory = MemoryClient(settings.memory_url)
    return _memory


def reset_client() -> None:
    """Для тестів: скинути лінивий MemoryClient."""
    global _memory
    _memory = None


def emit_context_event(store: dict[str, Any]) -> None:
    """Планує ingest у фоні; сам виклик синхронний і нічого не чекає."""
    try:
        task = asyncio.create_task(_ingest(store))
    except RuntimeError:  # немає запущеного loop — телеметрія не варта падіння
        logger.debug("context_emit: no running loop, event dropped")
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
        logger.debug("context emit failed: %s", exc)
