"""JARVIS Tools service — інструменти агента + Facade JARVIS + pipeline."""
from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from starlette.responses import Response

from .bootstrap import build_jarvis
from .config import settings
from .memory_client import MemoryClient
from .routes import mount_routes
from .runtime import get_agent_mode

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("jarvis.tools.main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    memory = MemoryClient(settings.memory_url)
    jarvis, runner, chat_backend = build_jarvis(memory, settings.twin_url)
    app.state.memory = memory
    app.state.jarvis = jarvis
    app.state.agent = runner
    app.state.chat_backend = chat_backend
    logger.info(
        "Tools up. mode=%s chat=%s agent=%s code_exec=%s",
        get_agent_mode(),
        settings.ollama_model_chat,
        settings.ollama_model_agent,
        settings.enable_code_exec,
    )
    yield
    await chat_backend.aclose()
    await memory.aclose()


app = FastAPI(title="JARVIS Tools", lifespan=lifespan)


@app.middleware("http")
async def _log_request_id(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    rid = request.headers.get("X-Request-ID", "")
    if rid:
        logger.info("request_id=%s %s %s", rid, request.method, request.url.path)
    return await call_next(request)


mount_routes(app)
