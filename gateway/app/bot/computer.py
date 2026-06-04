"""Підтвердження Computer Use дій у Telegram (inline ✅/❌)."""
from __future__ import annotations

import logging
import re
from typing import Any

import redis.asyncio as aioredis

from ..tools_client import ToolsClient
from ..telegram import TelegramClient
from .dashboard import esc
from .keyboards import computer_confirm_keyboard

logger = logging.getLogger("jarvis.gateway.computer")

_CONFIRM_RE = re.compile(r"\[\[COMPUTER_CONFIRM:([a-f0-9]+)\]\]\s*(.*)", re.DOTALL)


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


async def maybe_send_confirm_from_text(
    chat_id: int,
    text: str,
    tg: TelegramClient,
) -> bool:
    """Якщо у тексті є маркер підтвердження — шле inline-кнопки. True якщо знайдено."""
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
) -> bool:
    """Обробляє cmp:Y / cmp:N. Повертає True якщо спожито."""
    if not data.startswith("cmp:"):
        return False

    parts = data.split(":")
    if len(parts) < 2:
        return True

    if parts[1] == "N":
        await tools.cancel_computer(user_id)
        await tg.send_message(chat_id, "❌ Computer Use: скасовано.")
        return True

    if parts[1] != "Y" or len(parts) < 3:
        await tg.send_message(chat_id, "Невідома кнопка.")
        return True

    code = parts[2]
    result = await tools.confirm_computer(user_id, code)
    preview = esc(result[:3500])
    await tg.send_message(
        chat_id,
        f"✅ <b>Виконано</b>\n\n<pre>{preview}</pre>",
        parse_mode="HTML",
    )
    return True
