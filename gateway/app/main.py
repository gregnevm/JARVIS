"""JARVIS Gateway — точка входу FastAPI."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

import redis.asyncio as aioredis
from fastapi import BackgroundTasks, FastAPI, Request

from . import router
from .config import settings
from .orchestrator import Orchestrator
from .ratelimit import RateLimiter
from .telegram import TelegramClient
from .whisper import WhisperClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("jarvis.gateway")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.tg = TelegramClient(settings.telegram_bot_token, settings.telegram_api_base)
    app.state.orch = Orchestrator(settings.n8n_webhook_url, settings.orchestrator_timeout)
    app.state.stt = WhisperClient(settings.whisper_url, settings.whisper_language)
    app.state.redis = aioredis.from_url(settings.redis_url, encoding="utf-8", decode_responses=True)
    app.state.limiter = RateLimiter(app.state.redis, settings.rate_limit_per_min)
    logger.info(
        "Gateway up. Whitelist: %s | rate_limit=%s/min",
        sorted(settings.allowed_ids) or "ПОРОЖНІЙ (нікого не пускає!)",
        settings.rate_limit_per_min,
    )
    yield
    await app.state.tg.aclose()
    await app.state.orch.aclose()
    await app.state.stt.aclose()
    await app.state.redis.aclose()


app = FastAPI(title="JARVIS Gateway", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


async def _process(update: dict[str, Any], app: FastAPI) -> None:
    try:
        await router.handle_update(
            update, app.state.tg, app.state.orch, app.state.stt, app.state.limiter
        )
    except Exception:
        logger.exception("Failed to handle update")


@app.post("/webhook")
async def webhook(request: Request, background: BackgroundTasks) -> dict[str, bool]:
    update = await request.json()
    # Telegram отримує 200 миттєво; LLM-обробку виконуємо у фоні.
    background.add_task(_process, update, request.app)
    return {"ok": True}
