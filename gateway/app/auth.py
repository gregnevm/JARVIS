"""Whitelist-перевірка користувачів за Telegram user_id."""
from __future__ import annotations

from .config import settings


def is_allowed(user_id: int | None) -> bool:
    if user_id is None:
        return False
    return user_id in settings.allowed_ids
