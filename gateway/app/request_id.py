"""X-Request-ID для трасування gateway → tools."""
from __future__ import annotations

import uuid
from contextvars import ContextVar

_request_id: ContextVar[str] = ContextVar("request_id", default="")


def new_request_id() -> str:
    return uuid.uuid4().hex[:12]


def set_request_id(rid: str) -> None:
    _request_id.set(rid)


def get_request_id() -> str:
    return _request_id.get() or ""
