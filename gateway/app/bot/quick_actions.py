"""Швидкі дії з Reply Keyboard — мапінг тексту кнопок на handlers."""
from __future__ import annotations

import logging
from typing import Any

import redis.asyncio as aioredis

from ..auth import computer_mode_denied_message
from ..config import settings
from ..outbound import deliver
from ..services import ServicesClient
from ..telegram import TelegramClient
from ..tools_client import ToolsClient
from .dashboard import esc, format_dashboard
from .keyboards import (
    BTN_BRIEF,
    BTN_COMPUTER,
    BTN_HIDE,
    BTN_MENU,
    BTN_REMINDERS,
    BTN_SCREEN,
    BTN_STATUS,
    main_menu_keyboard,
    mode_keyboard,
    remove_reply_keyboard,
    reply_keyboard,
    reminders_hint_keyboard,
)
from .reminders_view import format_reminders_message, list_user_reminders

logger = logging.getLogger("jarvis.gateway.bot")

_KEYBOARD_OFF = "jarvis:tg:keyboard_off:{user_id}"
_KEYBOARD_SHOWN = "jarvis:tg:keyboard_shown:{user_id}"

QUICK_ACTIONS = frozenset(
    {BTN_STATUS, BTN_BRIEF, BTN_REMINDERS, BTN_COMPUTER, BTN_SCREEN, BTN_MENU, BTN_HIDE}
)

_BRIEF_PROMPT = """Сформуй короткий бриф для користувача (до 12 рядків, українською):
1) поточний стан системи (Ollama, режим, моделі)
2) активні нагадування (якщо є)
3) 1–3 практичні поради на сьогодні

Контекст:
{context}

Пиши стисло, без markdown-заголовків."""


def is_quick_action(text: str) -> bool:
    return (text or "").strip() in QUICK_ACTIONS


async def _run_brief(
    chat_id: int,
    user_id: int,
    tg: TelegramClient,
    svc: ServicesClient,
    tools: ToolsClient,
    redis: aioredis.Redis | None,
) -> None:
    dash = await svc.dashboard()
    twin = await svc.twin_status()
    context = format_dashboard(dash, twin)
    if redis is not None:
        reminders = await list_user_reminders(redis, user_id)
        context = f"{context}\n\nНагадування:\n{reminders}"
    await tg.send_chat_action(chat_id, "typing")
    prompt = _BRIEF_PROMPT.format(context=context)
    answer = await tools.process({"user_id": user_id, "text": prompt})
    await deliver(tg, chat_id, answer, redis=redis, user_id=user_id)


async def handle_quick_action(
    text: str,
    chat_id: int,
    user_id: int,
    tg: TelegramClient,
    svc: ServicesClient,
    tools: ToolsClient,
    redis: aioredis.Redis | None = None,
) -> bool:
    """Обробляє натискання Reply Keyboard. True — далі не викликати агента."""
    action = (text or "").strip()
    if action not in QUICK_ACTIONS:
        return False

    if action == BTN_STATUS:
        dash = await svc.dashboard()
        twin = await svc.twin_status()
        await tg.send_message(
            chat_id,
            format_dashboard(dash, twin),
            parse_mode="HTML",
            reply_markup=main_menu_keyboard(settings.public_app_url),
        )
        return True

    if action == BTN_BRIEF:
        await _run_brief(chat_id, user_id, tg, svc, tools, redis)
        return True

    if action == BTN_REMINDERS:
        if redis is None:
            await tg.send_message(chat_id, "Redis недоступний — нагадування не прочитати.")
            return True
        body = await list_user_reminders(redis, user_id)
        await tg.send_message(
            chat_id,
            format_reminders_message(body),
            parse_mode="HTML",
            reply_markup=reminders_hint_keyboard(),
        )
        return True

    if action == BTN_COMPUTER:
        from ..auth import agent_mode_denied_message

        denied = agent_mode_denied_message(user_id) or computer_mode_denied_message(
            user_id, "computer"
        )
        if denied:
            await tg.send_message(chat_id, denied)
            return True
        res = await svc.set_mode("computer")
        if res.get("error"):
            await tg.send_message(chat_id, f"🔴 {esc(res['error'])}", parse_mode="HTML")
        else:
            await tg.send_message(
                chat_id,
                "💻 <b>Computer mode</b>\n"
                "Мутуючі дії (PowerShell, FS, CLI) потребують підтвердження ✅/❌.\n"
                f"Режим: <code>{esc(res.get('mode', 'computer'))}</code>",
                parse_mode="HTML",
                reply_markup=mode_keyboard(),
            )
        return True

    if action == BTN_SCREEN:
        await tg.send_chat_action(chat_id, "upload_photo")
        reply = await tools.capture_screenshot(user_id)
        await deliver(tg, chat_id, reply, redis=redis, user_id=user_id)
        return True

    if action == BTN_MENU:
        dash = await svc.dashboard()
        twin = await svc.twin_status()
        await tg.send_message(
            chat_id,
            format_dashboard(dash, twin),
            parse_mode="HTML",
            reply_markup=main_menu_keyboard(settings.public_app_url),
        )
        return True

    if action == BTN_HIDE:
        if redis is not None:
            await mark_keyboard_off(redis, user_id)
        await tg.send_message(
            chat_id,
            "⌨️ Клавіатуру приховано. /keyboard on — показати знову.",
            reply_markup=remove_reply_keyboard(),
        )
        return True

    return False


async def mark_keyboard_off(redis: aioredis.Redis, user_id: int) -> None:
    await redis.set(_KEYBOARD_OFF.format(user_id=user_id), "1")
    await redis.delete(_KEYBOARD_SHOWN.format(user_id=user_id))


async def mark_keyboard_on(redis: aioredis.Redis, user_id: int) -> None:
    await redis.delete(_KEYBOARD_OFF.format(user_id=user_id))
    await redis.delete(_KEYBOARD_SHOWN.format(user_id=user_id))


async def ensure_reply_keyboard_auto(
    tg: TelegramClient,
    chat_id: int,
    user_id: int,
    redis: aioredis.Redis | None,
) -> None:
    """Один раз автоматично показує Reply Keyboard (без /start)."""
    if not settings.telegram_reply_keyboard:
        return
    if redis is not None:
        try:
            if await redis.get(_KEYBOARD_OFF.format(user_id=user_id)):
                return
            shown_key = _KEYBOARD_SHOWN.format(user_id=user_id)
            set_fn = getattr(redis, "set", None)
            if set_fn is not None:
                shown = await set_fn(shown_key, "1", nx=True)
                if not shown:
                    return
            elif await redis.get(shown_key):
                return
            else:
                setex = getattr(redis, "setex", None)
                if setex is not None:
                    await setex(shown_key, 86400 * 30, "1")
        except Exception as exc:  # noqa: BLE001 — Redis недоступний / mock без API
            logger.debug("ensure_reply_keyboard_auto redis: %s", exc)
    await tg.send_message(
        chat_id,
        "⌨️ Швидкий доступ — кнопки внизу.",
        reply_markup=reply_keyboard(settings.public_app_url),
    )


async def show_reply_keyboard(
    tg: TelegramClient,
    chat_id: int,
    redis: aioredis.Redis | None = None,
    user_id: int | None = None,
) -> None:
    if not settings.telegram_reply_keyboard:
        return
    if redis is not None and user_id is not None:
        await mark_keyboard_on(redis, user_id)
        await redis.set(_KEYBOARD_SHOWN.format(user_id=user_id), "1")
    await tg.send_message(
        chat_id,
        "⌨️ Швидкі кнопки активні.",
        reply_markup=reply_keyboard(settings.public_app_url),
    )
