"""JARVIS Gateway — точка входу FastAPI."""
from __future__ import annotations

import asyncio
import contextlib
import hmac
import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

import redis.asyncio as aioredis
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request

from . import router
from .config import settings
from .reminders import reminder_loop
from .services import ServicesClient
from .webapp import router as webapp_router
from .tools_client import ToolsClient
from .ratelimit import RateLimiter
from .telegram import TelegramClient
from .tts_client import TtsClient
from .whisper import WhisperClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
# httpx за замовчуванням пише повний URL у INFO — а в нас у URL Telegram-токен.
# Глушимо до WARNING на всіх 3 сервісах (gateway/memory/tools), щоб токен не тік у логи.
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("jarvis.gateway")

# Апдейти, які нас цікавлять (інші Telegram навіть не присилає → менше шуму/трафіку).
# message_reaction треба явно запросити (Telegram не шле його за замовчуванням).
ALLOWED_UPDATES = [
    "message",
    "edited_message",
    "callback_query",
    "inline_query",
    "message_reaction",
]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.tg = TelegramClient(settings.telegram_bot_token, settings.telegram_api_base)
    app.state.tools = ToolsClient(settings.tools_url, settings.agent_timeout)
    app.state.svc = ServicesClient(settings.tools_url, settings.twin_url)
    app.state.stt = WhisperClient(settings.whisper_url, settings.whisper_language)
    app.state.redis = aioredis.from_url(settings.redis_url, encoding="utf-8", decode_responses=True)
    app.state.limiter = RateLimiter(app.state.redis, settings.rate_limit_per_min)
    app.state.tts = TtsClient(settings.tts_url) if settings.enable_voice_reply else None

    mode = settings.telegram_ingest_mode.strip().lower()
    poll_task: asyncio.Task[None] | None = None
    if mode == "polling":
        poll_task = asyncio.create_task(_poll_loop(app))

    # Поллер нагадувань — незалежний від ingest-режиму (шле прострочене з Redis ZSET).
    reminder_task = asyncio.create_task(reminder_loop(app.state.redis, app.state.tg))

    # Mini App: якщо є публічний https-URL — реєструємо кнопку-меню (вхід у дашборд).
    if settings.public_app_url.startswith("https://"):
        await app.state.tg.set_chat_menu_button(settings.public_app_url, "📊 Dashboard")
        logger.info("Mini App menu button set → %s", settings.public_app_url)

    logger.info(
        "Gateway up. ingest=%s | Whitelist: %s | rate_limit=%s/min | voice_reply=%s",
        mode,
        sorted(settings.allowed_ids) or "ПОРОЖНІЙ (нікого не пускає!)",
        settings.rate_limit_per_min,
        settings.enable_voice_reply,
    )
    yield

    for task in (poll_task, reminder_task):
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
    await app.state.tg.aclose()
    await app.state.tools.aclose()
    await app.state.svc.aclose()
    await app.state.stt.aclose()
    await app.state.redis.aclose()
    if app.state.tts is not None:
        await app.state.tts.aclose()


async def _poll_loop(app: FastAPI) -> None:
    """Long polling: gateway сам тягне апдейти. Без публічного URL/вебхука/тунелю.

    Telegram віддає апдейти лише одному споживачу на токен, тож webhook і getUpdates
    взаємовиключні — на старті знімаємо webhook. Кожен апдейт обробляється конкурентно
    (asyncio task); масштаб «вшир» — це винесення обробки в чергу+воркери (ROADMAP).
    """
    tg = app.state.tg
    await tg.delete_webhook(drop_pending=False)
    offset: int | None = None
    backoff = 1.0
    logger.info("Long polling started (getUpdates)")
    while True:
        try:
            updates = await tg.get_updates(
                offset=offset, timeout=30, allowed_updates=ALLOWED_UPDATES
            )
            backoff = 1.0
            for update in updates:
                offset = int(update["update_id"]) + 1
                asyncio.create_task(_process(update, app))
        except asyncio.CancelledError:
            logger.info("Long polling stopped")
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("getUpdates failed: %s — retry in %.0fs", exc, backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30.0)


app = FastAPI(title="JARVIS Gateway", lifespan=lifespan)
app.include_router(webapp_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


async def _process(update: dict[str, Any], app: FastAPI) -> None:
    try:
        await router.handle_update(
            update,
            app.state.tg,
            app.state.tools,
            app.state.svc,
            app.state.stt,
            app.state.limiter,
            app.state.redis,
            app.state.tts,
        )
    except Exception:
        logger.exception("Failed to handle update")


@app.post("/webhook")
async def webhook(request: Request, background: BackgroundTasks) -> dict[str, bool]:
    """Прийом апдейтів у webhook-режимі (потрібен публічний HTTPS-URL).

    У дефолтному polling-режимі не використовується, але лишається готовим для прода
    зі стабільним доменом (TELEGRAM_INGEST_MODE=webhook).
    """
    # Перевірка секрету вебхука (якщо налаштований) — захист від підроблених апдейтів.
    secret = settings.telegram_webhook_secret
    if secret:
        got = request.headers.get("x-telegram-bot-api-secret-token", "")
        if not hmac.compare_digest(got, secret):
            logger.warning("webhook rejected: bad/missing secret token")
            raise HTTPException(status_code=403, detail="forbidden")
    update = await request.json()
    # Telegram отримує 200 миттєво; LLM-обробку виконуємо у фоні.
    background.add_task(_process, update, request.app)
    return {"ok": True}
