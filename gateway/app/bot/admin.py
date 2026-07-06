"""Адмін-команди з обовʼязковим підтвердженням (inline + /confirm)."""
from __future__ import annotations

import logging
import secrets

import redis.asyncio as aioredis

from .._helpers import AGENT_MODES
from ..auth import is_admin
from ..services import ServicesClient
from ..telegram import TelegramClient
from ..telegram_webapp_auth import admin_app_url
from ._helpers import require_admin_or_reply
from .dashboard import esc
from .keyboards import admin_confirm_keyboard, admin_menu_keyboard

logger = logging.getLogger("jarvis.gateway.admin")

_PENDING_PREFIX = "jarvis:admin:pending:"
_PENDING_TTL = 300


def is_admin_command(text: str) -> bool:
    t = (text or "").strip().lower()
    return t.startswith("/admin") or t.startswith("/confirm")


def _pending_key(user_id: int) -> str:
    return f"{_PENDING_PREFIX}{user_id}"


async def save_pending(redis: aioredis.Redis, user_id: int, action: str) -> str:
    """Зберігає дію; повертає короткий код для /confirm."""
    code = secrets.token_hex(3)
    payload = f"{code}:{action}"
    await redis.setex(_pending_key(user_id), _PENDING_TTL, payload)
    return code


async def load_pending(redis: aioredis.Redis, user_id: int, code: str | None = None) -> str | None:
    raw = await redis.get(_pending_key(user_id))
    if not raw:
        return None
    text = raw.decode() if isinstance(raw, (bytes, bytearray)) else str(raw)
    stored_code, _, action = text.partition(":")
    if code is not None and stored_code != code.lower().strip():
        return None
    return action


async def clear_pending(redis: aioredis.Redis, user_id: int) -> None:
    await redis.delete(_pending_key(user_id))


def _describe_action(action: str) -> str:
    if action == "mode:reset":
        return "скинути режим агента до значення з <code>.env</code>"
    if action.startswith("mode:"):
        return f"встановити режим <code>{esc(action.split(':', 1)[1])}</code>"
    if action.startswith("rl:"):
        uid = action.split(":", 1)[1]
        return f"скинути rate-limit для user <code>{esc(uid)}</code>"
    return esc(action)


async def execute_action(
    action: str,
    svc: ServicesClient,
    redis: aioredis.Redis,
) -> str:
    if action == "mode:reset":
        res = await svc.reset_mode()
        if res.get("error"):
            return f"🔴 Помилка: {esc(res['error'])}"
        return f"✅ Режим скинуто → <code>{esc(res.get('mode', '?'))}</code> (з .env)"
    if action.startswith("mode:"):
        mode = action.split(":", 1)[1]
        res = await svc.set_mode(mode)
        if res.get("error"):
            return f"🔴 Помилка: {esc(res['error'])}"
        return f"✅ Режим: <code>{esc(res.get('mode', mode))}</code>"
    if action.startswith("rl:"):
        import time

        uid = action.split(":", 1)[1]
        window = int(time.time() // 60)
        await redis.delete(f"rl:{uid}:{window}", f"rl:{uid}:{window - 1}")
        return f"✅ Rate-limit скинуто для <code>{esc(uid)}</code>"
    return "🔴 Невідома дія"


async def request_confirmation(
    chat_id: int,
    user_id: int,
    action: str,
    tg: TelegramClient,
    redis: aioredis.Redis,
) -> None:
    code = await save_pending(redis, user_id, action)
    desc = _describe_action(action)
    await tg.send_message(
        chat_id,
        f"⚠️ <b>Підтверди адмін-дію</b>\n\n{desc}\n\n"
        f"Код: <code>{esc(code)}</code> (діє 5 хв)\n"
        "Натисни кнопку або надішли <code>/confirm КОД</code>",
        parse_mode="HTML",
        reply_markup=admin_confirm_keyboard(action, code),
    )


async def handle_admin_command(
    text: str,
    chat_id: int,
    user_id: int,
    tg: TelegramClient,
    svc: ServicesClient,
    redis: aioredis.Redis,
) -> bool:
    if not is_admin(user_id):
        await tg.send_message(chat_id, "⛔ Ця команда лише для адмінів (ADMIN_USER_IDS).")
        return True

    raw = (text or "").strip()
    lower = raw.lower()
    parts = lower.split()

    if parts[0].startswith("/confirm"):
        code = parts[1] if len(parts) > 1 else ""
        action = await load_pending(redis, user_id, code or None)
        if not action:
            await tg.send_message(chat_id, "Немає активного запиту або код невірний/прострочений.")
            return True
        await clear_pending(redis, user_id)
        result = await execute_action(action, svc, redis)
        await tg.send_message(chat_id, result, parse_mode="HTML")
        return True

    if parts[0].split("@")[0] == "/admin" and len(parts) == 1:
        url = admin_app_url()
        lines = [
            "🛠 <b>Admin Control Panel</b>\n",
        ]
        if url.startswith("https://"):
            lines.append("Відкрий <b>Mini App</b> кнопкою нижче — повна панель у Telegram.\n")
        else:
            lines.append(
                "Для Mini App у Telegram задай <code>PUBLIC_APP_URL=https://…/app</code> "
                "(адмін: …/admin) або <code>PUBLIC_ADMIN_APP_URL</code>.\n"
            )
        lines.append(
            "Inline-дії нижче — з підтвердженням.\n"
            "CLI: <code>/admin mode agent</code>, <code>/admin reset</code>, "
            "<code>/admin rl USER_ID</code>"
        )
        await tg.send_message(
            chat_id,
            "\n".join(lines),
            parse_mode="HTML",
            reply_markup=admin_menu_keyboard(),
        )
        return True

    action = None
    if len(parts) >= 2 and parts[1] == "reset":
        action = "mode:reset"
    elif len(parts) >= 3 and parts[1] == "mode" and parts[2] in AGENT_MODES:
        action = f"mode:{parts[2]}"
    elif len(parts) >= 2 and parts[1] == "mode" and len(parts) == 2:
        await tg.send_message(
            chat_id,
            "Вкажи режим: <code>/admin mode chat|agent|hybrid|computer</code> або <code>/admin reset</code>",
            parse_mode="HTML",
        )
        return True
    elif len(parts) >= 3 and parts[1] == "rl":
        target = parts[2]
        action = f"rl:{user_id if target == 'self' else target}"

    if action is None:
        await tg.send_message(
            chat_id,
            "Невідома admin-команда. <code>/admin</code> — меню.",
            parse_mode="HTML",
        )
        return True

    await request_confirmation(chat_id, user_id, action, tg, redis)
    return True


async def handle_admin_callback(
    data: str,
    chat_id: int,
    user_id: int,
    tg: TelegramClient,
    svc: ServicesClient,
    redis: aioredis.Redis,
) -> bool:
    """Обробляє adm:Y / adm:N. Повертає True якщо спожито."""
    if not data.startswith("adm:"):
        return False
    if await require_admin_or_reply(tg, chat_id, user_id):
        return True

    parts = data.split(":")
    if len(parts) < 2:
        return True
    verb = parts[1]

    if verb == "N":
        await clear_pending(redis, user_id)
        await tg.send_message(chat_id, "❌ Скасовано.")
        return True

    if verb != "Y":
        return True

    # adm:Y:CODE — підтвердження за кодом з Redis
    if len(parts) >= 3 and len(parts[2]) == 6:
        code = parts[2]
        action = await load_pending(redis, user_id, code)
        if not action:
            await tg.send_message(chat_id, "Запит прострочений. Повтори команду.")
            return True
        await clear_pending(redis, user_id)
        result = await execute_action(action, svc, redis)
        await tg.send_message(chat_id, result, parse_mode="HTML")
        return True

    # adm:Y:m:agent | adm:Y:r | adm:Y:rl:42 — запит підтвердження (як CLI /admin)
    if len(parts) >= 4 and parts[2] == "m":
        action = f"mode:{parts[3]}"
    elif len(parts) >= 3 and parts[2] == "r":
        action = "mode:reset"
    elif len(parts) >= 4 and parts[2] == "rl":
        target = parts[3]
        action = f"rl:{user_id if target == 'self' else target}"
    else:
        await tg.send_message(chat_id, "Невідома кнопка.")
        return True

    await request_confirmation(chat_id, user_id, action, tg, redis)
    return True
