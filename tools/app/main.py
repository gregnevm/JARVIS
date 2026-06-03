"""JARVIS Tools service — інструменти агента + агент-луп (дві моделі)."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from fastapi import FastAPI
from pydantic import BaseModel

from . import toolkit
from .agent import AgentRunner
from .config import settings
from .memory_client import MemoryClient
from .ollama import OllamaClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
# httpx за замовчуванням пише повний URL у INFO. Tools кличе memory/Ollama
# без секретів, але уніфікуємо з gateway (де через httpx тік Telegram-токен).
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("jarvis.tools.main")


class CalcRequest(BaseModel):
    expression: str


class FetchRequest(BaseModel):
    url: str


class SearchRequest(BaseModel):
    query: str
    max_results: int = 5


class ParseRequest(BaseModel):
    path: str


class CodeRequest(BaseModel):
    code: str


class AgentRequest(BaseModel):
    user_id: int
    text: str


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.ollama = OllamaClient(
        settings.ollama_host,
        settings.ollama_timeout,
        settings.ollama_fail_threshold,
        settings.ollama_cooldown,
    )
    app.state.memory = MemoryClient(settings.memory_url)
    app.state.agent = AgentRunner(app.state.ollama, app.state.memory)
    logger.info(
        "Tools up. mode=%s chat=%s agent=%s code_exec=%s",
        settings.agent_mode,
        settings.ollama_model_chat,
        settings.ollama_model_agent,
        settings.enable_code_exec,
    )
    yield
    await app.state.ollama.aclose()
    await app.state.memory.aclose()


app = FastAPI(title="JARVIS Tools", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/calc")
async def calc_ep(req: CalcRequest) -> dict[str, str]:
    return {"result": toolkit.calc(req.expression)}


@app.post("/web_fetch")
async def web_fetch_ep(req: FetchRequest) -> dict[str, str]:
    return {"text": await toolkit.web_fetch(req.url)}


@app.post("/search")
async def search_ep(req: SearchRequest) -> dict[str, str]:
    return {"text": await toolkit.web_search(req.query, req.max_results)}


@app.post("/parse_file")
async def parse_file_ep(req: ParseRequest) -> dict[str, str]:
    return {"text": toolkit.parse_file(req.path)}


@app.post("/code_exec")
async def code_exec_ep(req: CodeRequest) -> dict[str, str]:
    return {"result": toolkit.code_exec(req.code)}


@app.post("/agent")
async def agent_ep(req: AgentRequest) -> dict[str, Any]:
    runner: AgentRunner = app.state.agent
    try:
        return await runner.run(req.user_id, req.text)
    except Exception:  # noqa: BLE001 — користувач має отримати відповідь навіть як Ollama лежить
        logger.exception("agent run failed")
        return {"text": "Локальна модель зараз недоступна. Перевір, чи піднятий Ollama на хості.",
                "mode": "error", "iters": 0}
