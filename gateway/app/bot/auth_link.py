"""Bot-сторона Telegram-авторизації інших ендпоінтів (Стовп C, UX-фокус).

Одна команда `/connect` → інлайн-вибір каналу → один тап:
  * 🖥 **Веб-консоль** — посилання `…/connect/<token>`: браузер відкривається вже
    залогіненим (JWT-cookie). Без пароля, без копіювання.
  * 📱 **Застосунок**  — `jarvis://pair` deeplink (обмін на JWT у застосунку).
  * 🧩 **Розширення**  — server URL + JWT для вставки в popup розширення.

`/login` лишається коротким аліасом «дай мені вхід у застосунок» (історична назва).
Логіка мінту токенів — у `app.auth_links` (спільний модуль для всіх каналів)."""
from __future__ import annotations

import logging

import redis.asyncio as aioredis

from .. import auth_links
from ..applogin import mint_login_link, server_origin
from ..config import settings
from ..saas import auth as jwt_auth
from ..telegram import TelegramClient
from .dashboard import esc

logger = logging.getLogger("jarvis.gateway.bot.auth")


def connect_keyboard() -> dict[str, object]:
    """Інлайн-вибір каналу авторизації."""
    return {
        "inline_keyboard": [
            [{"text": "🖥 Веб-консоль", "callback_data": "conn:web"}],
            [{"text": "📱 Застосунок", "callback_data": "conn:app"}],
            [{"text": "🧩 Розширення браузера", "callback_data": "conn:ext"}],
        ]
    }


async def send_connect_menu(chat_id: int, tg: TelegramClient) -> None:
    await tg.send_message(
        chat_id,
        "🔐 <b>Підключити пристрій до JARVIS</b>\n\n"
        "Обери, що авторизувати — згенерую <b>одноразове</b> посилання, "
        "прив'язане до твого Telegram-акаунта (діє 10 хв):",
        parse_mode="HTML",
        reply_markup=connect_keyboard(),
    )


async def _web_link(redis: aioredis.Redis, user_id: int) -> str:
    """`…/connect/<token>` — публічний origin, інакше локальний gateway."""
    token = await auth_links.mint(redis, user_id, target="web")
    base = server_origin() or ""
    return f"{base}/connect/{token}"


async def send_web_login(chat_id: int, user_id: int, tg: TelegramClient, redis: aioredis.Redis) -> None:
    if not jwt_auth.jwt_enabled():
        await tg.send_message(
            chat_id,
            "🖥 Веб-вхід через Telegram потребує <code>JWT_SECRET</code> на сервері.\n"
            "Задай його у <code>.env</code> і перезапусти gateway — тоді консоль "
            "відкриватиметься одним тапом. Поки що відкрий <b>Mini App</b>: /app",
            parse_mode="HTML",
        )
        return
    url = await _web_link(redis, user_id)
    if url.startswith("https://"):
        markup = {"inline_keyboard": [[{"text": "🖥 Відкрити консоль", "url": url}]]}
        await tg.send_message(
            chat_id,
            "🖥 <b>Веб-консоль</b> — тисни кнопку: браузер відкриється вже "
            "залогіненим (дійсне 10 хв, одноразове).",
            parse_mode="HTML",
            reply_markup=markup,
        )
    else:
        # Локальний http:// — Telegram не робить url-кнопку на http, даємо текст.
        await tg.send_message(
            chat_id,
            "🖥 <b>Веб-консоль</b> — відкрий це посилання у браузері на цій машині "
            "(вхід без пароля, дійсне 10 хв):\n\n"
            f"<code>{esc(url)}</code>",
            parse_mode="HTML",
        )


async def send_app_login(chat_id: int, user_id: int, tg: TelegramClient, redis: aioredis.Redis) -> None:
    link = await mint_login_link(redis, user_id)
    await tg.send_message(
        chat_id,
        "📱 <b>Застосунок</b> — встанови APK (/apk), потім тисни посилання нижче: "
        "JARVIS відкриється вже авторизованим (дійсне 10 хв).\n\n"
        f"<code>{esc(link)}</code>",
        parse_mode="HTML",
    )


async def send_ext_login(chat_id: int, user_id: int, tg: TelegramClient) -> None:
    if not jwt_auth.jwt_enabled():
        await tg.send_message(
            chat_id,
            "🧩 Розширення потребує <code>JWT_SECRET</code> на сервері — задай його "
            "у <code>.env</code> і перезапусти gateway.",
            parse_mode="HTML",
        )
        return
    tokens = jwt_auth.issue_tokens(user_id)
    base = server_origin() or ""
    await tg.send_message(
        chat_id,
        "🧩 <b>Розширення браузера</b> — відкрий popup і встав:\n\n"
        f"<b>Server</b>: <code>{esc(base)}</code>\n"
        f"<b>Token</b>: <code>{esc(tokens['access_token'])}</code>\n\n"
        f"Дійсний {settings.jwt_access_ttl // 3600} год. "
        "Тримай у таємниці — це ключ доступу до твого JARVIS.",
        parse_mode="HTML",
    )


async def handle_connect_callback(
    data: str, chat_id: int, user_id: int, tg: TelegramClient, redis: aioredis.Redis | None
) -> bool:
    """`conn:web|app|ext` — генерує лінк відповідного каналу. True — спожито."""
    if not data.startswith("conn:"):
        return False
    target = data.split(":", 1)[1]
    if target == "menu":
        await send_connect_menu(chat_id, tg)
        return True
    if redis is None and target in ("web", "app"):
        await tg.send_message(chat_id, "Логін недоступний (Redis off).")
        return True
    if target == "web":
        await send_web_login(chat_id, user_id, tg, redis)  # type: ignore[arg-type]
    elif target == "app":
        await send_app_login(chat_id, user_id, tg, redis)  # type: ignore[arg-type]
    elif target == "ext":
        await send_ext_login(chat_id, user_id, tg)
    else:
        return False
    return True
