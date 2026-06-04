from __future__ import annotations

import logging
from typing import Any

from ..config import settings
from ..services import ServicesClient
from ..telegram import TelegramClient
from .dashboard import esc, format_dashboard, format_help
from .admin import handle_admin_command, is_admin_command
from .keyboards import main_menu_keyboard, mode_keyboard

logger = logging.getLogger("jarvis.gateway.bot")

COMMANDS = frozenset(
    {
        "/start",
        "/help",
        "/status",
        "/dashboard",
        "/mode",
        "/sync",
    }
)


def is_command(text: str) -> bool:
    if is_admin_command(text):
        return True
    t = (text or "").strip().lower()
    if not t.startswith("/"):
        return False
    cmd = t.split()[0].split("@")[0]
    return cmd in COMMANDS or cmd.startswith("/mode")


async def handle_command(
    text: str,
    chat_id: int,
    user_id: int,
    tg: TelegramClient,
    svc: ServicesClient,
    redis: Any = None,
) -> bool:
    """Обробляє команду. True — далі не викликати агента."""
    if is_admin_command(text) and redis is not None:
        return await handle_admin_command(text, chat_id, user_id, tg, svc, redis)

    raw = (text or "").strip()
    lower = raw.lower()
    parts = lower.split()
    cmd = parts[0].split("@")[0] if parts else ""

    if cmd in ("/start", "/dashboard"):
        dash = await svc.dashboard()
        twin = await svc.twin_status()
        body = format_dashboard(dash, twin)
        await tg.send_message(chat_id, body, parse_mode="HTML", reply_markup=main_menu_keyboard(settings.public_app_url))
        return True

    if cmd == "/help":
        await tg.send_message(
            chat_id, format_help(), parse_mode="HTML", reply_markup=main_menu_keyboard(settings.public_app_url)
        )
        return True

    if cmd == "/status":
        dash = await svc.dashboard()
        twin = await svc.twin_status()
        await tg.send_message(chat_id, format_dashboard(dash, twin), parse_mode="HTML")
        return True

    if cmd == "/sync":
        twin = await svc.twin_status()
        if not twin:
            await tg.send_message(chat_id, "🔴 Twin недоступний (перевір сервіс twin:8765).")
            return True
        await tg.send_message(chat_id, format_dashboard({}, twin), parse_mode="HTML")
        return True

    if cmd == "/mode":
        if len(parts) >= 2:
            mode = parts[1]
            res = await svc.set_mode(mode)
            if res.get("error"):
                await tg.send_message(chat_id, f"🔴 Не вдалося змінити режим: {esc(res['error'])}")
            else:
                await tg.send_message(
                    chat_id,
                    f"✅ Режим: <code>{esc(res.get('mode', mode))}</code>",
                    parse_mode="HTML",
                    reply_markup=mode_keyboard(),
                )
            return True
        dash = await svc.dashboard()
        cur = dash.get("agent_mode", "?")
        await tg.send_message(
            chat_id,
            f"🧠 Поточний режим: <code>{esc(cur)}</code>\n"
            "Обери кнопкою або: <code>/mode chat|agent|hybrid</code>",
            parse_mode="HTML",
            reply_markup=mode_keyboard(),
        )
        return True

    return False


async def handle_callback(
    callback: dict[str, Any],
    tg: TelegramClient,
    svc: ServicesClient,
    redis: Any = None,
) -> None:
    cq_id = callback.get("id")
    data = str(callback.get("data") or "")
    msg = callback.get("message") or {}
    chat_id = msg.get("chat", {}).get("id")
    user_id = (callback.get("from") or {}).get("id")
    if chat_id is None:
        return

    if cq_id:
        await tg.answer_callback_query(str(cq_id))

    if data.startswith("adm:") and redis is not None and user_id is not None:
        from .admin import handle_admin_callback

        if await handle_admin_callback(data, int(chat_id), int(user_id), tg, svc, redis):
            return

    if data.startswith("mode:"):
        mode = data.split(":", 1)[1]
        res = await svc.set_mode(mode)
        text = (
            f"✅ Режим: <code>{esc(res.get('mode', mode))}</code>"
            if not res.get("error")
            else f"🔴 {esc(res['error'])}"
        )
        await tg.send_message(int(chat_id), text, parse_mode="HTML", reply_markup=mode_keyboard())
        return

    if data == "dash:menu":
        dash = await svc.dashboard()
        twin = await svc.twin_status()
        await tg.send_message(
            int(chat_id),
            format_dashboard(dash, twin),
            parse_mode="HTML",
            reply_markup=main_menu_keyboard(settings.public_app_url),
        )
        return

    if data == "dash:help":
        await tg.send_message(
            int(chat_id), format_help(), parse_mode="HTML", reply_markup=main_menu_keyboard(settings.public_app_url)
        )
        return

    if data in ("dash:status", "dash:sync", "dash:mode"):
        dash = await svc.dashboard()
        twin = await svc.twin_status()
        if data == "dash:mode":
            await tg.send_message(
                int(chat_id),
                f"🧠 Режим: <code>{esc(dash.get('agent_mode', '?'))}</code>",
                parse_mode="HTML",
                reply_markup=mode_keyboard(),
            )
        else:
            await tg.send_message(
                int(chat_id),
                format_dashboard(dash, twin),
                parse_mode="HTML",
                reply_markup=main_menu_keyboard(settings.public_app_url),
            )
