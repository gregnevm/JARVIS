from __future__ import annotations

import logging
from typing import Any

import redis.asyncio as aioredis

from ..auth import (
    agent_mode_denied_message,
    can_use_computer,
    computer_mode_denied_message,
    get_access_store,
    is_admin,
)
from ..config import settings
from ..services import ServicesClient
from ..telegram import TelegramClient
from ..tools_client import ToolsClient
from .dashboard import esc, format_dashboard, format_help
from .access import handle_access_command, is_access_command
from .admin import handle_admin_command, is_admin_command
from .keyboards import (
    main_menu_keyboard,
    mode_keyboard,
    remove_reply_keyboard,
    reply_keyboard,
    reminders_hint_keyboard,
)
from .quick_actions import _run_brief, mark_keyboard_off, mark_keyboard_on, show_reply_keyboard
from .reminders_view import format_reminders_message, list_user_reminders

logger = logging.getLogger("jarvis.gateway.bot")

COMMANDS = frozenset(
    {
        "/start",
        "/help",
        "/status",
        "/dashboard",
        "/app",
        "/mode",
        "/sync",
        "/brief",
        "/reminders",
        "/dataset",
        "/keyboard",
    }
)


def is_command(text: str) -> bool:
    if is_admin_command(text) or is_access_command(text):
        return True
    t = (text or "").strip().lower()
    if not t.startswith("/"):
        return False
    cmd = t.split()[0].split("@")[0]
    return cmd in COMMANDS or cmd.startswith("/mode")


async def _present(
    tg: TelegramClient,
    chat_id: int,
    text: str,
    *,
    message_id: int | None = None,
    reply_markup: dict[str, Any] | None = None,
    edit: bool = True,
) -> None:
    """Редагує inline-повідомлення або шле нове, якщо edit=False / немає message_id."""
    if edit and message_id is not None:
        await tg.edit_message_text(
            chat_id, message_id, text, parse_mode="HTML", reply_markup=reply_markup
        )
    else:
        await tg.send_message(chat_id, text, parse_mode="HTML", reply_markup=reply_markup)


async def _send_dashboard(
    chat_id: int,
    tg: TelegramClient,
    svc: ServicesClient,
    *,
    user_id: int | None = None,
    message_id: int | None = None,
    edit: bool = True,
) -> None:
    dash = await svc.dashboard()
    twin = await svc.twin_status()
    body = format_dashboard(dash, twin)
    await _present(
        tg,
        chat_id,
        body,
        message_id=message_id,
        reply_markup=main_menu_keyboard(
            settings.mini_app_https_url, show_computer=can_use_computer(user_id)
        ),
        edit=edit,
    )


def _mini_app_url(*, canvas: bool = False) -> str:
    url = settings.mini_app_https_url
    if not url:
        return ""
    if canvas:
        sep = "&" if "?" in url else "?"
        return f"{url}{sep}canvas=1"
    return url


async def _send_mini_app(
    chat_id: int,
    tg: TelegramClient,
    svc: ServicesClient,
    *,
    user_id: int | None = None,
    canvas: bool = False,
) -> None:
    """Відкриває Telegram Mini App — не передаємо /app агенту як шлях FS."""
    url = _mini_app_url(canvas=canvas)
    if url.startswith("https://"):
        title = "📊 <b>Mini App — Канвас</b>" if canvas else "📊 <b>Mini App — JARVIS Dashboard</b>"
        await tg.send_message(
            chat_id,
            f"{title}\nНатисни кнопку нижче.",
            parse_mode="HTML",
            reply_markup={
                "inline_keyboard": [[{"text": "📊 Відкрити дашборд", "web_app": {"url": url}}]]
            },
        )
        return
    await _send_dashboard(chat_id, tg, svc, user_id=user_id, edit=False)
    lines = [
        "",
        "📱 <b>Mini App у Telegram</b> потребує <code>PUBLIC_APP_URL=https://…/app</code> "
        "(named Cloudflare tunnel — див. README).",
    ]
    if settings.webapp_dev_open:
        from ..webapp_urls import local_app_url

        local = local_app_url(settings.gateway_browser_url, canvas=canvas)
        lines.append(f"🖥 Браузер на цій машині: <code>{esc(local)}</code>")
    await tg.send_message(chat_id, "\n".join(lines), parse_mode="HTML")


async def handle_command(
    text: str,
    chat_id: int,
    user_id: int,
    tg: TelegramClient,
    svc: ServicesClient,
    redis: aioredis.Redis | None = None,
    tools: ToolsClient | None = None,
    *,
    message: dict[str, Any] | None = None,
) -> bool:
    """Обробляє команду. True — далі не викликати агента."""
    store = get_access_store()
    if is_access_command(text) and store is not None:
        return await handle_access_command(
            text, chat_id, user_id, tg, store, message=message
        )

    if is_admin_command(text) and redis is not None:
        return await handle_admin_command(text, chat_id, user_id, tg, svc, redis)

    raw = (text or "").strip()
    lower = raw.lower()
    parts = lower.split()
    cmd = parts[0].split("@")[0] if parts else ""

    if cmd == "/start":
        start_args = raw.split(maxsplit=1)
        payload = (start_args[1] if len(start_args) > 1 else "").strip().lower()
        if payload == "app":
            await _send_mini_app(chat_id, tg, svc, user_id=user_id)
            return True
        if payload.startswith("mode_"):
            mode = payload[5:]
            denied = agent_mode_denied_message(user_id) or computer_mode_denied_message(
                user_id, mode
            )
            if denied:
                await tg.send_message(chat_id, denied)
                return True
            res = await svc.set_mode(mode)
            if res.get("error"):
                await tg.send_message(chat_id, f"🔴 {esc(res['error'])}")
            else:
                await tg.send_message(
                    chat_id,
                    f"✅ Режим: <code>{esc(res.get('mode', mode))}</code>",
                    parse_mode="HTML",
                    reply_markup=mode_keyboard(show_computer=can_use_computer(user_id)),
                )
            return True
        if payload in ("remind", "reminders"):
            await tg.send_message(
                chat_id,
                "⏰ Нагадування: напиши «нагадай через 30 хв …» або /reminders",
            )
            return True
        if payload == "canvas":
            await _send_mini_app(chat_id, tg, svc, user_id=user_id, canvas=True)
            return True
        await _send_dashboard(chat_id, tg, svc, user_id=user_id, edit=False)
        return True

    if cmd == "/dashboard":
        await _send_dashboard(chat_id, tg, svc, user_id=user_id, edit=False)
        return True

    if cmd == "/app":
        await _send_mini_app(chat_id, tg, svc, user_id=user_id)
        return True

    if cmd == "/help":
        await tg.send_message(
            chat_id,
            format_help(),
            parse_mode="HTML",
            reply_markup=main_menu_keyboard(
                settings.mini_app_https_url, show_computer=can_use_computer(user_id)
            ),
        )
        return True

    if cmd == "/status":
        await _send_dashboard(chat_id, tg, svc, user_id=user_id, edit=False)
        return True

    if cmd == "/sync":
        twin = await svc.twin_status()
        if not twin:
            await tg.send_message(chat_id, "🔴 Twin недоступний (перевір сервіс twin:8765).")
            return True
        await tg.send_message(
            chat_id,
            format_dashboard({}, twin),
            parse_mode="HTML",
            reply_markup=main_menu_keyboard(
                settings.mini_app_https_url, show_computer=can_use_computer(user_id)
            ),
        )
        return True

    if cmd == "/brief":
        if tools is None:
            await tg.send_message(chat_id, "Агент недоступний.")
            return True
        await _run_brief(chat_id, user_id, tg, svc, tools, redis)
        return True

    if cmd == "/dataset":
        if not is_admin(user_id):
            await tg.send_message(chat_id, "⛔ Лише для адмінів (ADMIN_USER_IDS).")
            return True
        if tools is None:
            await tg.send_message(chat_id, "Tools недоступний.")
            return True
        stats = await tools.dataset_stats(int(user_id))
        info = await tools.export_dataset(int(user_id))
        if info.get("error"):
            await tg.send_message(chat_id, f"Експорт не вдався: {info['error']}")
            return True
        sched = info.get("scheduler") or stats
        ready = "✅" if sched.get("retrain_ready") else "—"
        await tg.send_message(
            chat_id,
            "📦 Dataset export\n"
            f"curated: {stats.get('curated_turns', '?')} · files: {stats.get('files', '?')}\n"
            f"train: {info.get('train', 0)} · holdout: {info.get('holdout', 0)}\n"
            f"retrain +{sched.get('curated_since_export', '?')}/{sched.get('retrain_threshold', '?')} {ready}\n"
            f"<code>{info.get('train_path', '')}</code>",
            parse_mode="HTML",
        )
        return True

    if cmd == "/reminders":
        if redis is None:
            await tg.send_message(chat_id, "Redis недоступний.")
            return True
        sub = (parts[1] if len(parts) >= 2 else "").lower()
        if sub == "ics":
            if tools is None:
                await tg.send_message(chat_id, "Tools недоступний.")
                return True
            ics = await tools.reminders_ics(user_id)
            if not ics:
                await tg.send_message(
                    chat_id,
                    "Немає активних нагадувань для експорту. /reminders ics — після set_reminder.",
                )
                return True
            await tg.send_document(
                chat_id, ics, filename="jarvis-reminders.ics", caption="📅 Експорт нагадувань"
            )
            return True
        body = await list_user_reminders(redis, user_id)
        await tg.send_message(
            chat_id,
            format_reminders_message(body) + "\n\n📅 Експорт: <code>/reminders ics</code>",
            parse_mode="HTML",
            reply_markup=reminders_hint_keyboard(),
        )
        return True

    if cmd == "/keyboard":
        sub = parts[1] if len(parts) >= 2 else "on"
        if sub in ("off", "hide", "сховати"):
            if redis is not None:
                await mark_keyboard_off(redis, user_id)
            await tg.send_message(
                chat_id,
                "⌨️ Клавіатуру приховано. /keyboard on — показати знову.",
                reply_markup=remove_reply_keyboard(),
            )
        elif settings.telegram_reply_keyboard:
            await show_reply_keyboard(tg, chat_id, redis, user_id)
        else:
            await tg.send_message(
                chat_id,
                "Reply Keyboard вимкнено (TELEGRAM_REPLY_KEYBOARD=false).",
            )
        return True

    if cmd == "/mode":
        denied = agent_mode_denied_message(user_id)
        if denied and len(parts) >= 2:
            await tg.send_message(chat_id, denied)
            return True
        if len(parts) >= 2:
            mode = parts[1]
            denied = computer_mode_denied_message(user_id, mode)
            if denied:
                await tg.send_message(chat_id, denied)
                return True
            res = await svc.set_mode(mode)
            if res.get("error"):
                await tg.send_message(chat_id, f"🔴 Не вдалося змінити режим: {esc(res['error'])}")
            else:
                await tg.send_message(
                    chat_id,
                    f"✅ Режим: <code>{esc(res.get('mode', mode))}</code>",
                    parse_mode="HTML",
                    reply_markup=mode_keyboard(show_computer=can_use_computer(user_id)),
                )
            return True
        dash = await svc.dashboard()
        cur = dash.get("agent_mode", "?")
        await tg.send_message(
            chat_id,
            f"🧠 Поточний режим: <code>{esc(cur)}</code>\n"
            "Обери кнопкою або: <code>/mode chat|agent|hybrid|computer</code>",
            parse_mode="HTML",
            reply_markup=mode_keyboard(show_computer=can_use_computer(user_id)),
        )
        return True

    return False


async def handle_callback(
    callback: dict[str, Any],
    tg: TelegramClient,
    svc: ServicesClient,
    redis: Any = None,
    tools: Any = None,
) -> None:
    cq_id = callback.get("id")
    data = str(callback.get("data") or "")
    msg = callback.get("message") or {}
    chat_id = msg.get("chat", {}).get("id")
    message_id = msg.get("message_id")
    user_id = (callback.get("from") or {}).get("id")
    if chat_id is None:
        return

    toast: str | None = None

    if data.startswith("acc:") and user_id is not None:
        store = get_access_store()
        if store is not None:
            from .access import handle_access_callback

            if cq_id:
                await tg.answer_callback_query(str(cq_id))
            if await handle_access_callback(data, int(chat_id), int(user_id), tg, store):
                return

    if data.startswith("adm:") and redis is not None and user_id is not None:
        from .admin import handle_admin_callback

        if cq_id:
            await tg.answer_callback_query(str(cq_id))
        if await handle_admin_callback(data, int(chat_id), int(user_id), tg, svc, redis):
            return

    if data.startswith("cmp:") and tools is not None and user_id is not None:
        from .computer import handle_computer_callback

        if cq_id:
            await tg.answer_callback_query(str(cq_id))
        if await handle_computer_callback(
            data, int(chat_id), int(user_id), tg, tools, redis=redis
        ):
            return

    if data.startswith("agt:") and tools is not None and user_id is not None:
        from ..agent_turn import run_agent_turn

        if cq_id:
            await tg.answer_callback_query(str(cq_id), text="Обробляю…")
        await run_agent_turn(
            tg,
            tools,
            int(chat_id),
            {
                "user_id": int(user_id),
                "chat_id": int(chat_id),
                "text": f"Користувач натиснув кнопку ({data}). Відреагуй коротко.",
                "type": "callback",
                "mode": "auto",
            },
            redis=redis,
            user_id=int(user_id),
        )
        return True

    if data.startswith("mode:"):
        mode = data.split(":", 1)[1]
        denied = agent_mode_denied_message(user_id) or computer_mode_denied_message(
            user_id, mode
        )
        if denied:
            if cq_id:
                await tg.answer_callback_query(str(cq_id), text=denied[:200])
            await tg.send_message(chat_id, denied)
            return True
        res = await svc.set_mode(mode)
        if res.get("error"):
            toast = f"Помилка: {res['error'][:180]}"
            text = f"🔴 {esc(res['error'])}"
        else:
            mode_name = str(res.get("mode", mode))
            toast = f"Режим: {mode_name}"
            text = f"🧠 Режим: <code>{esc(mode_name)}</code>"
        await _present(
            tg,
            int(chat_id),
            text,
            message_id=int(message_id) if message_id is not None else None,
            reply_markup=mode_keyboard(show_computer=can_use_computer(user_id)),
        )
        if cq_id:
            await tg.answer_callback_query(str(cq_id), text=toast)
        return

    if data == "dash:menu":
        dash = await svc.dashboard()
        twin = await svc.twin_status()
        await _present(
            tg,
            int(chat_id),
            format_dashboard(dash, twin),
            message_id=int(message_id) if message_id is not None else None,
            reply_markup=main_menu_keyboard(
                settings.mini_app_https_url, show_computer=can_use_computer(user_id)
            ),
        )
        if cq_id:
            await tg.answer_callback_query(str(cq_id))
        return

    if data == "dash:help":
        await _present(
            tg,
            int(chat_id),
            format_help(),
            message_id=int(message_id) if message_id is not None else None,
            reply_markup=main_menu_keyboard(
                settings.mini_app_https_url, show_computer=can_use_computer(user_id)
            ),
        )
        if cq_id:
            await tg.answer_callback_query(str(cq_id))
        return

    if data == "dash:brief":
        if tools is not None and user_id is not None:
            if cq_id:
                await tg.answer_callback_query(str(cq_id), text="Готую бриф…")
            await _run_brief(int(chat_id), int(user_id), tg, svc, tools, redis)
        elif cq_id:
            await tg.answer_callback_query(str(cq_id))
        return

    if data == "dash:reminders":
        if redis is not None:
            body = await list_user_reminders(redis, int(user_id or 0))
            await _present(
                tg,
                int(chat_id),
                format_reminders_message(body),
                message_id=int(message_id) if message_id is not None else None,
                reply_markup=reminders_hint_keyboard(),
            )
        if cq_id:
            await tg.answer_callback_query(str(cq_id))
        return

    if data in ("dash:status", "dash:sync", "dash:mode"):
        dash = await svc.dashboard()
        twin = await svc.twin_status()
        if data == "dash:mode":
            text = f"🧠 Режим: <code>{esc(dash.get('agent_mode', '?'))}</code>"
            markup = mode_keyboard(show_computer=can_use_computer(user_id))
        elif data == "dash:sync":
            text = format_dashboard({}, twin) if twin else "🔴 Twin недоступний."
            markup = main_menu_keyboard(
                settings.mini_app_https_url, show_computer=can_use_computer(user_id)
            )
        else:
            text = format_dashboard(dash, twin)
            markup = main_menu_keyboard(
                settings.mini_app_https_url, show_computer=can_use_computer(user_id)
            )
        await _present(
            tg,
            int(chat_id),
            text,
            message_id=int(message_id) if message_id is not None else None,
            reply_markup=markup,
        )
        if cq_id:
            await tg.answer_callback_query(str(cq_id))
        return

    if cq_id:
        await tg.answer_callback_query(str(cq_id))
