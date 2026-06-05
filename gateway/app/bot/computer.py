"""Підтвердження Computer Use дій у Telegram (inline ✅/❌)."""
from __future__ import annotations

import logging
import re
from typing import Any

from ..agent_turn import resume_after_computer
from ..outbound import deliver
from ..tools_client import ToolsClient
from ..telegram import TelegramClient
from .dashboard import esc
from .keyboards import admin_ps_confirm_keyboard, computer_confirm_keyboard

logger = logging.getLogger("jarvis.gateway.computer")

_CONFIRM_RE = re.compile(r"\[\[COMPUTER_CONFIRM:([a-f0-9]+)\]\]\s*(.*)", re.DOTALL)
_ADMIN_CONFIRM_RE = re.compile(
    r"\[\[COMPUTER_ADMIN_CONFIRM:([a-f0-9]+)\]\]\s*(.*)", re.DOTALL
)


def parse_confirm(text: str) -> dict[str, str] | None:
    m = _CONFIRM_RE.search(text or "")
    if not m:
        return None
    return {"code": m.group(1), "desc": m.group(2).strip()}


async def send_computer_confirm(
    chat_id: int,
    confirm: dict[str, str],
    tg: TelegramClient,
) -> None:
    code = confirm.get("code", "")
    desc = esc(confirm.get("desc", ""))
    await tg.send_message(
        chat_id,
        f"⚠️ <b>Computer Use</b>\n\n{desc}\n\n"
        f"Код: <code>{esc(code)}</code> (діє 5 хв)\n"
        "Підтверди дію на хості:",
        parse_mode="HTML",
        reply_markup=computer_confirm_keyboard(code),
    )


def parse_admin_confirm(text: str) -> dict[str, str] | None:
    m = _ADMIN_CONFIRM_RE.search(text or "")
    if not m:
        return None
    return {"code": m.group(1), "desc": m.group(2).strip()}


async def send_admin_confirm(
    chat_id: int,
    confirm: dict[str, str],
    tg: TelegramClient,
) -> None:
    code = confirm.get("code", "")
    desc = esc(confirm.get("desc", ""))
    await tg.send_message(
        chat_id,
        f"🔴 <b>Admin PowerShell</b> — друге підтвердження\n\n{desc}\n\n"
        f"Код: <code>{esc(code)}</code>",
        parse_mode="HTML",
        reply_markup=admin_ps_confirm_keyboard(code),
    )


async def maybe_send_confirm_from_text(
    chat_id: int,
    text: str,
    tg: TelegramClient,
) -> bool:
    """Якщо у тексті є маркер підтвердження — шле inline-кнопки. True якщо знайдено."""
    admin_c = parse_admin_confirm(text)
    if admin_c:
        await send_admin_confirm(chat_id, admin_c, tg)
        return True
    confirm = parse_confirm(text)
    if not confirm:
        return False
    await send_computer_confirm(chat_id, confirm, tg)
    return True


async def handle_computer_callback(
    data: str,
    chat_id: int,
    user_id: int,
    tg: TelegramClient,
    tools: ToolsClient,
    redis: Any = None,
) -> bool:
    """Обробляє cmp:Y / cmp:N. Повертає True якщо спожито."""
    from ..auth import computer_denied_message

    denied = computer_denied_message(user_id)
    if denied:
        await tg.send_message(chat_id, denied)
        return True
    if data.startswith("cmpA:"):
        parts = data.split(":")
        if len(parts) < 3 or parts[1] != "Y":
            await tg.send_message(chat_id, "Невідома кнопка.")
            return True
        code = parts[2]
        result, origin = await tools.confirm_computer(user_id, code)
        await deliver(
            tg,
            chat_id,
            f"✅ <b>Admin PS виконано</b>\n\n<pre>{esc(result[:3500])}</pre>",
        )
        await resume_after_computer(
            tg, tools, chat_id, user_id, result, redis, origin_text=origin
        )
        return True

    if not data.startswith("cmp:"):
        return False

    parts = data.split(":")
    if len(parts) < 2:
        return True

    if parts[1] == "N":
        await tools.cancel_computer(user_id)
        await tg.send_message(chat_id, "❌ Computer Use: скасовано.")
        return True

    grant_trust = parts[1] == "YT"
    if parts[1] not in ("Y", "YT") or len(parts) < 3:
        await tg.send_message(chat_id, "Невідома кнопка.")
        return True

    code = parts[2]
    result, origin = await tools.confirm_computer(user_id, code)
    if grant_trust:
        await tools.grant_trust(user_id)
        await tg.send_message(chat_id, "🔓 Trusted session: 30 хв без повторного ✅.")
    admin_c = parse_admin_confirm(result)
    if admin_c:
        await send_admin_confirm(chat_id, admin_c, tg)
        return True
    await deliver(tg, chat_id, f"✅ <b>Виконано</b>\n\n<pre>{esc(result[:3500])}</pre>")
    await resume_after_computer(
        tg,
        tools,
        chat_id,
        user_id,
        result,
        redis,
        origin_text=origin,
    )
    return True

