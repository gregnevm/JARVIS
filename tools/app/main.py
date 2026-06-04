"""JARVIS Tools service — інструменти агента + Facade JARVIS + pipeline."""
from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from jarvis_core.pipeline.handlers import screen_text

from . import toolkit
from .bootstrap import build_jarvis
from .config import settings
from .memory_client import MemoryClient
from .runtime import clear_agent_mode, get_agent_mode, set_agent_mode

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
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


class ComputerConfirmRequest(BaseModel):
    user_id: int
    code: str = ""


class ComputerUserRequest(BaseModel):
    user_id: int


class ModeRequest(BaseModel):
    mode: str


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


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/status")
async def status_ep() -> dict[str, Any]:
    return await app.state.jarvis.dashboard()


@app.get("/dashboard")
async def dashboard_ep() -> dict[str, Any]:
    return await app.state.jarvis.dashboard()


@app.post("/mode")
async def set_mode_ep(req: ModeRequest) -> dict[str, str]:
    m = req.mode.lower().strip()
    if m == "computer" and not settings.enable_computer_use:
        raise HTTPException(
            status_code=400,
            detail="Computer Use вимкнено (ENABLE_COMPUTER_USE=false).",
        )
    try:
        set_agent_mode(req.mode)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"mode": get_agent_mode(), "status": "ok"}


@app.delete("/mode")
async def reset_mode_ep() -> dict[str, str]:
    return {"mode": clear_agent_mode(), "status": "reset"}


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
    try:
        return await app.state.jarvis.chat(req.user_id, req.text)
    except Exception:  # noqa: BLE001
        logger.exception("agent run failed")
        return {
            "text": "Локальна модель зараз недоступна. Перевір, чи піднятий Ollama на хості.",
            "mode": "error",
            "iters": 0,
        }


def _ndjson(obj: dict[str, Any]) -> bytes:
    return (json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8")


@app.post("/agent/stream")
async def agent_stream_ep(req: AgentRequest) -> StreamingResponse:
    """Стрім інференсу як NDJSON. Використовує runner напряму (повз pipeline),
    тож safety-скрин застосовуємо тут; помилки завершуємо done-подією."""
    safe, block = screen_text(req.text)

    async def gen() -> AsyncIterator[bytes]:
        if block is not None:
            yield _ndjson({"done": True, "mode": block.mode, "iters": 0, "text": block.text})
            return
        try:
            async for ev in app.state.agent.run_stream(req.user_id, safe or req.text):
                yield _ndjson(ev)
        except Exception:  # noqa: BLE001
            logger.exception("agent stream failed")
            yield _ndjson(
                {
                    "done": True,
                    "mode": "error",
                    "iters": 0,
                    "text": "Локальна модель зараз недоступна. Перевір, чи піднятий Ollama на хості.",
                }
            )

    return StreamingResponse(gen(), media_type="application/x-ndjson")


@app.post("/computer/confirm")
async def computer_confirm_ep(req: ComputerConfirmRequest) -> dict[str, str]:
    from .computer_confirm import execute_confirmed

    if not req.code.strip():
        raise HTTPException(status_code=400, detail="code required")
    result, origin = await execute_confirmed(req.user_id, req.code.strip())
    return {"result": result, "origin": origin}


@app.post("/computer/cancel")
async def computer_cancel_ep(req: ComputerConfirmRequest) -> dict[str, str]:
    from .computer_confirm import clear_pending

    await clear_pending(req.user_id)
    return {"status": "cancelled"}


@app.post("/computer/screenshot")
async def computer_screenshot_ep(req: ComputerUserRequest) -> dict[str, str]:
    from . import computer

    text = await computer.capture_screenshot(user_id=req.user_id)
    return {"text": text}
