"""Confirm-mesh MVP (SY-5): confirm-запит → push + паспорти confirm_request/decision.

S4-подія стає видимою поза чатом: створення pending-підтвердження шле ntfy-push
із deep-link на канал апруву (SY-5.1), а сам запит і рішення (approve/cancel)
пишуться паспортами у `context_events` (SY-5.2) — «що я дозволив минулого
тижня» стає звичайним ретривом. Повний mesh (fan-out, first-responder-wins,
гасіння карток) — після SY-B2.

Усе fire-and-forget і best-effort: push/паспорт ніколи не блокують і не ламають
сам confirm-цикл. За прапором `ENABLE_CONFIRM_PUSH` (дефолт off, ADR-008).
Анти-leak: у push і паспорт іде `describe_action`-опис (уже обрізаний), без
сирих аргументів інструмента.
"""
from __future__ import annotations

import asyncio
import logging

from jarvis_core.push import publish_ntfy

from .config import settings
from .context_emit import emit_context_event

logger = logging.getLogger("jarvis.tools.confirm_events")

DECISION_APPROVED = "approved"
DECISION_CANCELLED = "cancelled"

_DESC_MAX = 300

_push_tasks: set[asyncio.Task[bool]] = set()


def _enabled(user_id: int) -> bool:
    return settings.enable_confirm_push and user_id > 0


def notify_confirm_request(
    user_id: int, code: str, *, tool: str, description: str, tier: str
) -> None:
    """Pending створено → push із deep-link + паспорт kind:confirm_request."""
    if not _enabled(user_id):
        return
    desc = description[:_DESC_MAX]
    emit_context_event(
        {
            "user_id": user_id,
            "kind": "confirm_request",
            "summary": f"[{tier}] {desc}",
            "tags": ["priority:high", "module:computer", f"tool:{tool}", f"tier:{tier.lower()}"],
            "source": "confirm_mesh",
            "sensitivity": "personal",
            "ref": f"confirm:{code}",
            "payload": {"code": code, "tool": tool},
        }
    )
    try:
        task = asyncio.create_task(
            publish_ntfy(
                enabled=settings.push_enabled,
                url=settings.ntfy_url,
                topic=settings.ntfy_topic,
                message=f"Підтвердь дію (код {code}): {desc}",
                title=f"JARVIS · confirm [{tier}]",
                click=settings.confirm_push_click_url.strip() or None,
            )
        )
    except RuntimeError:
        logger.debug("confirm push: no running loop, dropped")
        return
    _push_tasks.add(task)
    task.add_done_callback(_push_tasks.discard)


def emit_confirm_decision(user_id: int, code: str, decision: str, *, tool: str = "") -> None:
    """Approve/cancel → паспорт kind:confirm_decision (аудит-трейл S4-дій)."""
    if not _enabled(user_id):
        return
    tags = ["module:computer", f"status:{decision}"]
    if tool:
        tags.append(f"tool:{tool}")
    emit_context_event(
        {
            "user_id": user_id,
            "kind": "confirm_decision",
            "summary": f"Confirm {code}: {decision}" + (f" ({tool})" if tool else ""),
            "tags": tags,
            "source": "confirm_mesh",
            "sensitivity": "personal",
            "ref": f"confirm:{code}",
            "payload": {"code": code, "decision": decision, "tool": tool},
        }
    )


async def drain() -> None:
    """Дочекатися push-тасок (тести/shutdown); паспорти — `context_emit.drain`."""
    while _push_tasks:
        await asyncio.gather(*list(_push_tasks), return_exceptions=True)
