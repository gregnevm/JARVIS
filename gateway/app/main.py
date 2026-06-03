"""JARVIS Gateway — точка входу FastAPI."""
from __future__ import annotations

import hmac
import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

import redis.asyncio as aioredis
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request

from . import router
from .config import settings
from .services import ServicesClient
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


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.tg = TelegramClient(settings.telegram_bot_token, settings.telegram_api_base)
    app.state.tools = ToolsClient(settings.tools_url, settings.agent_timeout)
    app.state.svc = ServicesClient(settings.tools_url, settings.twin_url)
    app.state.stt = WhisperClient(settings.whisper_url, settings.whisper_language)
    app.state.redis = aioredis.from_url(settings.redis_url, encoding="utf-8", decode_responses=True)
    app.state.limiter = RateLimiter(app.state.redis, settings.rate_limit_per_min)
    app.state.tts = TtsClient(settings.tts_url) if settings.enable_voice_reply else None
    logger.info(
        "Gateway up. Whitelist: %s | rate_limit=%s/min | voice_reply=%s",
        sorted(settings.allowed_ids) or "ПОРОЖНІЙ (нікого не пускає!)",
        settings.rate_limit_per_min,
        settings.enable_voice_reply,
    )
    yield
    await app.state.tg.aclose()
    await app.state.tools.aclose()
    await app.state.svc.aclose()
    await app.state.stt.aclose()
    await app.state.redis.aclose()
    if app.state.tts is not None:
        await app.state.tts.aclose()


app = FastAPI(title="JARVIS Gateway", lifespan=lifespan)


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
