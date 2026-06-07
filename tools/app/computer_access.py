"""Хто може керувати Windows-хостом (Computer Use + скріншоти)."""
from __future__ import annotations

from jarvis_core.auth_ids import parse_comma_separated_ids, resolve_computer_owner_ids

from .config import settings

_DENIED = (
    "Керування цим комп'ютером доступне лише власнику "
    "(COMPUTER_OWNER_USER_IDS у .env)."
)


def computer_owner_ids() -> set[int]:
    """Явний список → інакше ADMIN_USER_IDS → інакше ALLOWED_USER_IDS (.env)."""
    return resolve_computer_owner_ids(
        computer_owner_user_ids=settings.computer_owner_user_ids,
        admin_user_ids=settings.admin_user_ids,
        allowed_user_ids=settings.allowed_user_ids,
        computer_mode_admins_only=settings.computer_mode_admins_only,
    )


def can_use_computer(user_id: int) -> bool:
    if not settings.enable_computer_use:
        return False
    if int(user_id) <= 0:
        return False
    owners = computer_owner_ids()
    if not owners:
        return False
    return int(user_id) in owners


def admin_user_ids() -> set[int]:
    return parse_comma_separated_ids(settings.admin_user_ids)


def admin_powershell_denied_message(user_id: int) -> str | None:
    """Admin PowerShell (UAC) — лише ADMIN_USER_IDS і COMPUTER_ALLOW_ADMIN=true."""
    if not settings.computer_allow_admin:
        return "Admin PowerShell вимкнено (COMPUTER_ALLOW_ADMIN=false)."
    admins = admin_user_ids()
    if not admins:
        return "ADMIN_USER_IDS не задано — admin PowerShell заблоковано."
    if int(user_id) not in admins:
        return "Admin PowerShell лише для ADMIN_USER_IDS."
    return None


def computer_denied_message(user_id: int) -> str | None:
    if can_use_computer(user_id):
        return None
    if not settings.enable_computer_use:
        return "Computer Use вимкнено (ENABLE_COMPUTER_USE=false)."
    return _DENIED
