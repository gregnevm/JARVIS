"""Planning Mode (P3) — inline approve/deny у Telegram."""
from __future__ import annotations

import logging
import re

from ..telegram import TelegramClient
from ..tools_client import ToolsClient
from .dashboard import esc
from .keyboards import plan_confirm_keyboard

logger = logging.getLogger("jarvis.gateway.plans")

_PLAN_RE = re.compile(r"\[\[PLAN_CONFIRM:([a-f0-9]+)\]\]")


def parse_plan_marker(text: str) -> str | None:
    m = _PLAN_RE.search(text or "")
    return m.group(1) if m else None


async def send_plan_confirm(
    chat_id: int,
    plan_id: str,
    summary: str,
    tg: TelegramClient,
) -> None:
    body = esc((summary or "")[:1500])
    await tg.send_message(
        chat_id,
        f"📋 <b>План задачі</b>\n\n{body}\n\n"
        f"ID: <code>{esc(plan_id)}</code>\n"
        "Схвали або відхили:",
        parse_mode="HTML",
        reply_markup=plan_confirm_keyboard(plan_id),
    )


async def maybe_send_plan_from_text(
    chat_id: int,
    text: str,
    tg: TelegramClient,
) -> bool:
    plan_id = parse_plan_marker(text)
    if not plan_id:
        return False
    summary = _PLAN_RE.sub("", text or "").strip() or "План готовий до перегляду."
    await send_plan_confirm(chat_id, plan_id, summary, tg)
    return True


async def handle_plan_callback(
    data: str,
    chat_id: int,
    user_id: int,
    tg: TelegramClient,
    tools: ToolsClient,
) -> bool:
    """Обробляє pln:Y / pln:N. Повертає True якщо спожито."""
    if not data.startswith("pln:"):
        return False
    parts = data.split(":", 2)
    if len(parts) < 3:
        return False
    action, plan_id = parts[1], parts[2]
    if action == "N":
        await tools.deny_plan(plan_id, user_id)
        await tg.send_message(chat_id, f"❌ План <code>{esc(plan_id)}</code> відхилено.", parse_mode="HTML")
        return True
    if action == "Y":
        plan = await tools.approve_plan(plan_id, user_id)
        if plan is None:
            await tg.send_message(chat_id, "План не знайдено або застарів.")
            return True
        await tg.send_message(
            chat_id,
            f"✅ План <code>{esc(plan_id)}</code> схвалено.\n"
            "Виконай у Platform або командою <code>/plan execute "
            f"{esc(plan_id)}</code>",
            parse_mode="HTML",
        )
        return True
    return False
