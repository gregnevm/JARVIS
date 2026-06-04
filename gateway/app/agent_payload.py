"""Єдиний builder payload для Tools /agent."""
from __future__ import annotations

from typing import Any

from .request_id import get_request_id


def build_agent_payload(
    *,
    user_id: int,
    chat_id: int,
    text: str,
    source: str = "text",
    mode: str = "auto",
    message_thread_id: int | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    rid = (request_id or get_request_id() or "").strip()
    payload: dict[str, Any] = {
        "user_id": user_id,
        "chat_id": chat_id,
        "text": text,
        "type": source,
        "mode": mode,
    }
    if message_thread_id is not None:
        payload["message_thread_id"] = message_thread_id
    if rid:
        payload["request_id"] = rid
    return payload
