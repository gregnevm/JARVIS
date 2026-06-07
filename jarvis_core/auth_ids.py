"""Спільний парсинг Telegram user_id та резолв власників Computer Use."""
from __future__ import annotations


def parse_comma_separated_ids(raw: str) -> set[int]:
    """Рядок '1, 2, 3' → set[int]; невалідні сегменти пропускаються."""
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


def resolve_computer_owner_ids(
    *,
    computer_owner_user_ids: str,
    admin_user_ids: str,
    allowed_user_ids: str,
    computer_mode_admins_only: bool = False,
) -> set[int]:
    """Логіка gateway `computer_owner_ids()` — єдина семантика для gateway і tools."""
    owners = parse_comma_separated_ids(computer_owner_user_ids)
    if owners:
        return owners

    admins = parse_comma_separated_ids(admin_user_ids)
    allowed = parse_comma_separated_ids(allowed_user_ids)
    # ADMIN_USER_IDS порожній → адміни = ALLOWED (як property admin_ids у gateway).
    admin_ids = admins if admin_user_ids.strip() else allowed

    if computer_mode_admins_only:
        return admin_ids
    if admin_user_ids.strip():
        return admin_ids
    return allowed
