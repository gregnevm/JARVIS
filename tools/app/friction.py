"""Friction-телеметрія (SY-1 «самозарядний backlog», SYNERGY_ROADMAP).

Реальний біль рантайму → паспорти `kind:friction` у `context_events`: plan-фаза
kaizen читає їх tag-запитом і ставить поруч із roadmap-кандидатами — backlog
поповнюється з телеметрії, а не лише з ручного підкидання задач (анти-`backlog_dry`).

Продюсер fast-path (P6: summary без LLM), fire-and-forget (обв'язка —
`context_emit`), best-effort. Анти-leak: у паспорт іде лише ТИП помилки і
лічильники — ані сирих аргументів, ані трейсбеків (клас token/PII-leak).
За прапором `ENABLE_FRICTION_TELEMETRY` (дефолт off, ADR-008).
"""
from __future__ import annotations

from typing import Any

from .config import settings
from .context_emit import emit_context_event

REASON_TOOL_FAIL = "tool_fail"
REASON_UNKNOWN_TOOL = "unknown_tool"
REASON_LOOP_EXHAUSTED = "loop_exhausted"

_SUMMARY_MAX = 300


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
    emit_context_event(store)
