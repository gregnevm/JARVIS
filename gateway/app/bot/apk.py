"""Bot `/apk` — завжди віддає MVP Android-клієнт у Telegram (Стовп C, CL-3).

Композиція (P4): окремий модуль із власним хендлером, підключений одним рядком у
`commands.py`. Сама логіка пошуку/читання файлу — у `app.apk_artifact` (спільна з
авто-нотифікацією адміна).
"""
from __future__ import annotations

import logging
from typing import Iterable

from ..apk_artifact import apk_info, read_apk_bytes
from ..telegram import TelegramClient

logger = logging.getLogger("jarvis.gateway.bot.apk")

_NOT_READY = (
    "📦 <b>APK ще не зібрано.</b>\n"
    "MVP-клієнт збирається скриптом <code>mobile/build-apk.ps1</code> — "
    "після білду файл з'явиться і ця команда віддасть його. "
    "Адмін отримає apk у Telegram автоматично, щойно білд завершиться."
)


def _caption(version: str, size_mb: float, sha12: str, built_at: str) -> str:
    lines = [
        f"📱 <b>JARVIS MVP APK</b> · v{version}",
        f"{size_mb} MB · sha256 <code>{sha12}</code>",
    ]
    if built_at:
        lines.append(f"зібрано: {built_at}")
    lines.append(
        "Встанови: дозволь «з невідомих джерел» → відкрий → вкажи URL свого "
        "JARVIS-сервера (LAN або tunnel)."
    )
    return "\n".join(lines)


async def send_apk(tg: TelegramClient, chat_id: int) -> bool:
    """Шле APK у чат. True — файл відправлено; False — ще не зібрано/помилка."""
    info = apk_info()
    if info is None:
        return False
    data = read_apk_bytes()
    if not data:
        return False
    caption = _caption(info.version, info.size_mb, info.sha256[:12], info.built_at)
    ok = await tg.send_document(chat_id, data, caption=caption, filename=info.filename)
    if not ok:
        logger.error("send_document(apk) failed for chat %s", chat_id)
    return ok


async def handle_apk_command(
    chat_id: int, user_id: int, tg: TelegramClient, redis: object | None = None
) -> bool:
    """`/apk` — віддає .apk + one-tap login link (вхід без зайвих дій)."""
    sent = await send_apk(tg, chat_id)
    if not sent:
        await tg.send_message(chat_id, _NOT_READY, parse_mode="HTML")
        return True
    await _send_login_link(chat_id, user_id, tg, redis)
    return True


async def _send_login_link(
    chat_id: int, user_id: int, tg: TelegramClient, redis: object | None
) -> None:
    """One-tap вхід: посилання jarvis://pair з токеном, прив'язаним до user_id."""
    if redis is None:
        return
    try:
        from ..applogin import mint_login_link

        link = await mint_login_link(redis, user_id)  # type: ignore[arg-type]
        await tg.send_message(
            chat_id,
            "🔐 Встановив? Тисни — <b>вхід одним тапом</b> (відкриє JARVIS уже "
            f"авторизованим):\n\n<code>{link}</code>",
            parse_mode="HTML",
        )
    except Exception as exc:  # pragma: no cover
        logger.warning("login link failed: %s", exc)


async def notify_admins_apk_ready(tg: TelegramClient, admin_ids: Iterable[int]) -> int:
    """Розсилає свіжозібраний APK усім адмінам. Повертає к-сть успішних доставок."""
    info = apk_info()
    if info is None:
        logger.warning("notify_admins_apk_ready: apk not found, nothing to send")
        return 0
    delivered = 0
    for admin_id in admin_ids:
        try:
            await tg.send_message(
                int(admin_id),
                "✅ <b>MVP APK готовий.</b> Надсилаю файл нижче.",
                parse_mode="HTML",
            )
            if await send_apk(tg, int(admin_id)):
                delivered += 1
        except Exception as exc:  # pragma: no cover - мережеві збої не валять розсилку
            logger.error("apk notify to %s failed: %s", admin_id, exc)
    return delivered
