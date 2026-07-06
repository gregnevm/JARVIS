"""Погодження доступу друзів через бота (черга + /allow, inline-кнопки)."""
from __future__ import annotations

import logging
import re
from typing import Any

from ..access_store import AccessStore, UserRecord, format_user_label, record_from_telegram
from ..auth import is_admin
from ..config import settings
from ..telegram import TelegramClient
from ._helpers import require_admin_or_reply
from .keyboards import access_decision_keyboard

logger = logging.getLogger("jarvis.gateway.access")

_ACCESS_COMMANDS = frozenset({"/allow", "/deny", "/pending", "/users", "/revoke"})


def is_access_command(text: str) -> bool:
    t = (text or "").strip().lower()
    if not t.startswith("/"):
        return False
    cmd = t.split()[0].split("@")[0]
    return cmd in _ACCESS_COMMANDS


def _parse_target_id(text: str, message: dict[str, Any] | None) -> int | None:
    parts = (text or "").strip().split()
    if len(parts) >= 2 and parts[1].isdigit():
        return int(parts[1])
    if message is None:
        return None
    reply = message.get("reply_to_message")
    if not isinstance(reply, dict):
        return None
    frm = reply.get("from") or {}
    uid = frm.get("id")
    return int(uid) if uid is not None else None


async def notify_admins_new_request(
    tg: TelegramClient,
    rec: UserRecord,
) -> None:
    admins = settings.admin_ids
    if not admins:
        return
    label = format_user_label(rec)
    body = (
        "🔔 <b>Запит на доступ до JARVIS</b>\n\n"
        f"{label}\n\n"
        f"<code>/allow {rec.user_id}</code> · <code>/deny {rec.user_id}</code>\n"
        "або кнопки нижче."
    )
    markup = access_decision_keyboard(rec.user_id)
    for admin_id in sorted(admins):
        try:
            await tg.send_message(admin_id, body, parse_mode="HTML", reply_markup=markup)
        except Exception as exc:  # noqa: BLE001 — один адмін не блокує інших
            logger.warning("notify admin %s failed: %s", admin_id, exc)


async def handle_guest_access(
    message: dict[str, Any],
    chat_id: int,
    user_id: int,
    tg: TelegramClient,
    store: AccessStore,
) -> None:
    """Невідомий користувач: черга + повідомлення (без агента)."""
    frm = message.get("from") or {}
    try:
        rec = record_from_telegram(frm)
    except (KeyError, TypeError, ValueError):
        await tg.send_message(chat_id, "Не вдалося прочитати профіль. Спробуй ще раз.")
        return

    if rec.user_id in store.approved_ids:
        await tg.send_message(
            chat_id,
            "✅ Доступ уже відкрито — напиши /start.",
        )
        return

    if rec.user_id in store.pending_ids:
        await tg.send_message(
            chat_id,
            "⏳ Запит уже в черзі. Очікуй, поки власник погодить доступ.",
        )
        return

    created = await store.add_pending(rec)
    if created:
        await notify_admins_new_request(tg, rec)
        await tg.send_message(
            chat_id,
            "📩 <b>Запит надіслано.</b>\n\n"
            "Власник бота погодить доступ у Telegram. "
            "Коли відкриють — напиши /start.",
            parse_mode="HTML",
        )
    else:
        await tg.send_message(chat_id, "⏳ Запит уже в черзі.")


async def _notify_user_granted(tg: TelegramClient, user_id: int) -> None:
    try:
        await tg.send_message(
            user_id,
            "✅ <b>Доступ відкрито!</b>\n\nНапиши /start — можна користуватись JARVIS.",
            parse_mode="HTML",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("grant notify user %s failed: %s", user_id, exc)


async def _do_approve(
    target_id: int,
    admin_id: int,
    chat_id: int,
    tg: TelegramClient,
    store: AccessStore,
) -> None:
    if target_id in settings.allowed_ids:
        await tg.send_message(chat_id, "Цей ID уже в базовому whitelist (.env).")
        return
    ok, msg, rec = await store.approve(target_id, by_admin=admin_id)
    if not ok:
        await tg.send_message(chat_id, msg)
        return
    label = format_user_label(rec) if rec else f"id <code>{target_id}</code>"
    await tg.send_message(
        chat_id,
        f"✅ Доступ відкрито: {label}",
        parse_mode="HTML",
    )
    await _notify_user_granted(tg, target_id)


async def handle_access_command(
    text: str,
    chat_id: int,
    user_id: int,
    tg: TelegramClient,
    store: AccessStore,
    *,
    message: dict[str, Any] | None = None,
) -> bool:
    if not is_admin(user_id):
        await tg.send_message(
            chat_id,
            "⛔ Ці команди лише для адмінів (ADMIN_USER_IDS).",
        )
        return True

    raw = (text or "").strip()
    lower = raw.lower()
    parts = lower.split()
    cmd = parts[0].split("@")[0] if parts else ""

    if cmd == "/pending":
        await _send_pending_list(chat_id, tg, store)
        return True

    if cmd == "/users":
        env_ids = sorted(settings.allowed_ids)
        approved = store.list_approved()
        lines = ["👥 <b>Користувачі з доступом</b>\n"]
        if env_ids:
            lines.append("\n<b>Базовий whitelist (.env):</b>")
            for uid in env_ids:
                lines.append(f"• <code>{uid}</code>")
        if approved:
            lines.append("\n<b>Погоджені через бота:</b>")
            for rec in approved:
                lines.append(f"• {format_user_label(rec)}")
        if not env_ids and not approved:
            lines.append("Нікого.")
        await tg.send_message(chat_id, "\n".join(lines), parse_mode="HTML")
        return True

    target_id = _parse_target_id(raw, message)

    if cmd == "/allow":
        if target_id is None:
            await tg.send_message(
                chat_id,
                "Вкажи ID: <code>/allow 123456789</code>\n"
                "або відповідай (reply) на повідомлення користувача.",
                parse_mode="HTML",
            )
            return True
        await _do_approve(target_id, user_id, chat_id, tg, store)
        return True

    if cmd == "/deny":
        if target_id is None:
            await tg.send_message(
                chat_id,
                "Вкажи ID: <code>/deny 123456789</code>",
                parse_mode="HTML",
            )
            return True
        ok, _ = await store.deny(target_id)
        if ok:
            await tg.send_message(chat_id, f"❌ Запит відхилено: <code>{target_id}</code>", parse_mode="HTML")
            try:
                await tg.send_message(
                    target_id,
                    "Доступ до бота не надано. Якщо це помилка — напиши власнику окремо.",
                )
            except Exception as exc:  # noqa: BLE001 — користувач міг заблокувати бота, не зривати адмін-флоу
                logger.warning("notify denied user %s failed: %s", target_id, exc)
        else:
            await tg.send_message(chat_id, "Немає такого запиту в черзі.")
        return True

    if cmd == "/revoke":
        if target_id is None:
            await tg.send_message(
                chat_id,
                "Вкажи ID: <code>/revoke 123456789</code>",
                parse_mode="HTML",
            )
            return True
        if target_id in settings.allowed_ids:
            await tg.send_message(
                chat_id,
                "ID з .env не можна забрати через бота — прибери з ALLOWED_USER_IDS.",
            )
            return True
        ok, _ = await store.revoke(target_id)
        if ok:
            await tg.send_message(
                chat_id,
                f"🚫 Доступ забрано: <code>{target_id}</code>",
                parse_mode="HTML",
            )
            try:
                await tg.send_message(target_id, "Доступ до JARVIS закрито.")
            except Exception as exc:  # noqa: BLE001 — користувач міг заблокувати бота, не зривати адмін-флоу
                logger.warning("notify revoked user %s failed: %s", target_id, exc)
        else:
            await tg.send_message(chat_id, "Користувач не був погоджений через бота.")
        return True

    return False


_ACC_RE = re.compile(r"^acc:([yn]):(\d+)$", re.IGNORECASE)


async def _send_pending_list(chat_id: int, tg: TelegramClient, store: AccessStore) -> None:
    pending = store.list_pending()
    if not pending:
        await tg.send_message(chat_id, "📭 Черга порожня — немає запитів.")
        return
    lines = ["📋 <b>Запити на доступ</b>\n"]
    for rec in pending:
        lines.append(f"• {format_user_label(rec)}")
        lines.append(f"  <code>/allow {rec.user_id}</code> · <code>/deny {rec.user_id}</code>")
    await tg.send_message(chat_id, "\n".join(lines), parse_mode="HTML")


async def handle_access_callback(
    data: str,
    chat_id: int,
    user_id: int,
    tg: TelegramClient,
    store: AccessStore,
) -> bool:
    if data.strip() == "acc:list":
        if await require_admin_or_reply(tg, chat_id, user_id):
            return True
        await _send_pending_list(chat_id, tg, store)
        return True

    m = _ACC_RE.match(data.strip())
    if not m:
        return False
    if await require_admin_or_reply(tg, chat_id, user_id):
        return True

    verb, uid_s = m.group(1).lower(), m.group(2)
    target_id = int(uid_s)

    if verb == "n":
        ok, _ = await store.deny(target_id)
        await tg.send_message(
            chat_id,
            f"❌ Відхилено: <code>{target_id}</code>" if ok else "Запит уже оброблено.",
            parse_mode="HTML",
        )
        return True

    await _do_approve(target_id, user_id, chat_id, tg, store)
    return True
