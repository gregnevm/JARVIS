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

from pathlib import Path

from . import router
from .access_store import AccessStore
from .auth import allowed_ids_snapshot, bind_access_store
from .config import settings
from .bot.setup import register_bot_ui
from .reminders import reminder_loop
from .health_watch import health_watch_loop
from .job_runner import job_runner_loop
from .services import ServicesClient
from .admin_panel import router as admin_panel_router
from .platform import router as platform_router
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
    "chosen_inline_result",
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
    # TTS-клієнт завжди (увімкнення — runtime flag або ENABLE_VOICE_REPLY).
    app.state.tts = TtsClient(settings.tts_url)

    access_store = AccessStore(Path(settings.access_store_path))
    await access_store.load()
    bind_access_store(access_store)
    app.state.access_store = access_store

    mode = settings.telegram_ingest_mode.strip().lower()
    poll_task: asyncio.Task[None] | None = None
    if mode == "polling":
        poll_task = asyncio.create_task(_poll_loop(app))
    elif mode == "webhook":
        webhook_url = settings.telegram_webhook_url.strip()
        if webhook_url:
            secret = settings.telegram_webhook_secret.strip() or None
            await app.state.tg.set_webhook(
                webhook_url, secret_token=secret, allowed_updates=ALLOWED_UPDATES
            )
            logger.info("Webhook registered → %s", webhook_url)
        else:
            logger.warning("TELEGRAM_INGEST_MODE=webhook but TELEGRAM_WEBHOOK_URL is empty")

    reminder_task = asyncio.create_task(
        reminder_loop(
            app.state.redis,
            app.state.tg,
            interval=settings.reminder_poll_seconds,
        )
    )
    health_task: asyncio.Task[None] | None = None
    if settings.health_watch_interval > 0:
        alert_ids = settings.health_alert_ids
        health_task = asyncio.create_task(
            health_watch_loop(
                app.state.redis,
                app.state.tg,
                app.state.svc,
                settings.health_watch_interval,
                alert_ids=alert_ids or None,
            )
        )
    job_task = asyncio.create_task(
        job_runner_loop(app.state.tools, app.state.tg, interval=30.0)
    )

    # BotFather UI: команди, опис, Mini App menu button.
    await register_bot_ui(app.state.tg)

    wl = sorted(allowed_ids_snapshot())
    pending_n = len(access_store.pending_ids)
    logger.info(
        "Gateway up. ingest=%s | Whitelist: %s | pending=%s | rate=%s/min guest=%s | voice=%s",
        mode,
        wl or "ПОРОЖНІЙ (нікого не пускає!)",
        pending_n,
        settings.rate_limit_per_min,
        settings.guest_rate_limit_per_min or "same",
        settings.enable_voice_reply,
    )
    yield

    for task in (poll_task, reminder_task, health_task, job_task):
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
app.include_router(admin_panel_router)
app.include_router(platform_router)


@app.middleware("http")
async def _request_id_middleware(request: Request, call_next):
    from .request_id import new_request_id, set_request_id

    rid = request.headers.get("X-Request-ID") or new_request_id()
    set_request_id(rid)
    request.state.request_id = rid
    response = await call_next(request)
    response.headers["X-Request-ID"] = rid
    return response


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
