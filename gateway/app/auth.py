"""Whitelist і admin-права за Telegram user_id."""
from __future__ import annotations

from .config import settings


def is_allowed(user_id: int | None) -> bool:
    if user_id is None:
        return False
    return user_id in settings.allowed_ids


def can_use_computer_mode(user_id: int | None) -> bool:
    if user_id is None:
        return False
    if not settings.computer_mode_admins_only:
        return user_id in settings.allowed_ids
    return is_admin(user_id)


def computer_mode_denied_message(user_id: int | None, mode: str) -> str | None:
    if mode.lower() != "computer":
        return None
    if can_use_computer_mode(user_id):
        return None
    return "Режим computer доступний лише адмінам (COMPUTER_MODE_ADMINS_ONLY)."


def is_admin(user_id: int | None) -> bool:
    if user_id is None:
        return False
    admins = settings.admin_ids
    if not admins:
        return user_id in settings.allowed_ids
    return user_id in admins
