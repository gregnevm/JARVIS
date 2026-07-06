"""Перевірка Telegram WebApp initData (Mini App)."""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl

from fastapi import HTTPException

from .auth import is_admin, is_allowed
from .config import settings

_MAX_AUTH_AGE = 24 * 3600


def parse_init_data(init_data: str) -> dict[str, str] | None:
    if not init_data:
        return None
    try:
        return dict(parse_qsl(init_data, strict_parsing=True))
    except ValueError:
        return None


def valid_signature(pairs: dict[str, str], bot_token: str) -> bool:
    received = pairs.get("hash", "")
    if not received:
        return False
    check = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs) if k != "hash")
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    calc = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(calc, received)


def user_id_from_init_data(init_data: str | None) -> int:
    """Повертає Telegram user_id або кидає 401/403."""
    pairs = parse_init_data(init_data or "")
    if pairs is None:
        raise HTTPException(status_code=401, detail="no init data")

    token = settings.telegram_bot_token
    if not token or not valid_signature(pairs, token):
        raise HTTPException(status_code=401, detail="bad signature")

    # Fail closed: без валідного числового auth_date неможливо перевірити свіжість initData,
    # тож вважаємо його простроченим. Telegram завжди шле auth_date; підпис покриває лише
    # наявні ключі, тож раніше payload без auth_date проходив із НЕОБМЕЖЕНИМ вікном реплею.
    auth_date = pairs.get("auth_date")
    if not auth_date or not auth_date.isdigit() or time.time() - int(auth_date) > _MAX_AUTH_AGE:
        raise HTTPException(status_code=401, detail="init data expired")

    try:
        user = json.loads(pairs.get("user", "{}"))
        return int(user["id"])
    except (KeyError, ValueError, TypeError):
        raise HTTPException(status_code=401, detail="no user") from None


def authorize_allowed(init_data: str | None) -> int:
    user_id = user_id_from_init_data(init_data)
    if not is_allowed(user_id):
        raise HTTPException(status_code=403, detail="not allowed")
    return user_id


def authorize_admin(init_data: str | None) -> int:
    user_id = user_id_from_init_data(init_data)
    if not is_admin(user_id):
        raise HTTPException(status_code=403, detail="admin only")
    return user_id


def admin_app_url() -> str:
    """HTTPS URL Mini App адмін-панелі для Telegram web_app кнопок."""
    raw = (settings.public_admin_app_url or "").strip()
    if raw.startswith("https://"):
        return raw
    app = settings.mini_app_https_url
    if not app:
        return ""
    return app[: -len("/app")] + "/admin"
