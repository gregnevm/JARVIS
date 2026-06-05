"""Whitelist і admin-права за Telegram user_id."""
from __future__ import annotations

from typing import TYPE_CHECKING

from .config import settings

if TYPE_CHECKING:
    from .access_store import AccessStore

_store: AccessStore | None = None


def bind_access_store(store: AccessStore | None) -> None:
    """Підключає динамічний whitelist (погоджені через /allow)."""
    global _store
    _store = store


def get_access_store() -> AccessStore | None:
    return _store


def allowed_ids_snapshot() -> set[int]:
    """Усі ID з доступом: .env + погоджені через бота."""
    ids = set(settings.allowed_ids)
    if _store is not None:
        ids |= _store.approved_ids
    return ids


def is_allowed(user_id: int | None) -> bool:
    if user_id is None:
        return False
    if user_id in settings.allowed_ids:
        return True
    if _store is not None and user_id in _store.approved_ids:
        return True
    return False


def _parse_owner_ids(raw: str) -> set[int]:
    ids: set[int] = set()
    for part in (raw or "").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ids.add(int(part))
        except ValueError:
            continue
    return ids


def computer_owner_ids() -> set[int]:
    """Власник ПК: COMPUTER_OWNER_USER_IDS, інакше адміни, інакше ALLOWED з .env (не /allow)."""
    owners = _parse_owner_ids(settings.computer_owner_user_ids)
    if owners:
        return owners
    if settings.computer_mode_admins_only:
        return settings.admin_ids
    admins = settings.admin_ids
    if settings.admin_user_ids.strip():
        return admins
    return settings.allowed_ids


def can_use_computer(user_id: int | None) -> bool:
    if user_id is None:
        return False
    return int(user_id) in computer_owner_ids()


def can_use_computer_mode(user_id: int | None) -> bool:
    return can_use_computer(user_id)


def can_change_agent_mode(user_id: int | None) -> bool:
    """Глобальний режим chat/agent/hybrid/computer — лише адмін (не друзі)."""
    return is_admin(user_id)


def agent_mode_denied_message(user_id: int | None) -> str | None:
    if can_change_agent_mode(user_id):
        return None
    return "Змінювати режим агента можуть лише адміни (ADMIN_USER_IDS)."


def computer_denied_message(user_id: int | None) -> str | None:
    if can_use_computer(user_id):
        return None
    return (
        "Керування цим комп'ютером доступне лише власнику "
        "(COMPUTER_OWNER_USER_IDS у .env)."
    )


def computer_mode_denied_message(user_id: int | None, mode: str) -> str | None:
    if mode.lower() != "computer":
        return None
    return computer_denied_message(user_id)


def is_admin(user_id: int | None) -> bool:
    if user_id is None:
        return False
    admins = settings.admin_ids
    if not admins:
        return user_id in settings.allowed_ids
    return user_id in admins
