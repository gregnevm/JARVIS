"""JARVIS Tools service — інструменти агента + Facade JARVIS + pipeline."""
from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from fastapi import FastAPI, HTTPException, Request
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
    mode: str | None = None


class ComputerConfirmRequest(BaseModel):
    user_id: int
    code: str = ""


class ComputerUserRequest(BaseModel):
    user_id: int


class ModeRequest(BaseModel):
    mode: str


class ToolDispatchRequest(BaseModel):
    name: str
    arguments: dict[str, Any] = {}
    user_id: int = 0
    allow_computer: bool = True


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
async def _log_request_id(request: Request, call_next):
    rid = request.headers.get("X-Request-ID", "")
    if rid:
        logger.info("request_id=%s %s %s", rid, request.method, request.url.path)
    return await call_next(request)


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


@app.post("/tool/dispatch")
async def tool_dispatch_ep(req: ToolDispatchRequest) -> dict[str, str]:
    """Прямий виклик toolkit (smoke / CI). Не для публічного інтернету."""
    text = await toolkit.dispatch(
        req.name.strip(),
        req.arguments,
        req.user_id,
        allow_computer=req.allow_computer,
    )
    return {"text": text}


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
        return await app.state.jarvis.chat(req.user_id, req.text, mode=req.mode)
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
            hint = req.mode if req.mode and req.mode != "auto" else None
            async for ev in app.state.agent.run_stream(
                req.user_id, safe or req.text, mode=hint, mode_hint=hint
            ):
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
    from .computer_access import computer_denied_message
    from .computer_confirm import execute_confirmed

    denied = computer_denied_message(req.user_id)
    if denied:
        return {"result": denied, "origin": ""}
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
    from .computer_access import computer_denied_message

    denied = computer_denied_message(req.user_id)
    if denied:
        return {"text": denied}
    text = await computer.capture_screenshot(user_id=req.user_id)
    return {"text": text}


class FilePathRequest(BaseModel):
    user_id: int
    path: str


class FileUploadRequest(BaseModel):
    user_id: int
    path: str
    data_b64: str


class MacroRunRequest(BaseModel):
    user_id: int
    name: str


class SeeRequest(BaseModel):
    user_id: int
    question: str = ""


class TrustRequest(BaseModel):
    user_id: int


@app.post("/computer/file/pull")
async def computer_file_pull(req: FilePathRequest) -> dict[str, Any]:
    from . import computer
    from .computer_access import computer_denied_message

    denied = computer_denied_message(req.user_id)
    if denied:
        return {"error": denied}
    data, name, err = await computer.download_file(req.path, user_id=req.user_id)
    if err:
        return {"error": err}
    if len(data) > settings.remote_file_max_bytes:
        return {"error": "file too large for Telegram"}
    return {"filename": name, "data_b64": __import__("base64").b64encode(data).decode("ascii")}


@app.post("/computer/file/push")
async def computer_file_push(req: FileUploadRequest) -> dict[str, str]:
    from . import computer
    from .computer_access import computer_denied_message

    denied = computer_denied_message(req.user_id)
    if denied:
        return {"error": denied}
    import base64

    try:
        raw = base64.b64decode(req.data_b64, validate=True)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="invalid base64") from None
    text = await computer.upload_file_bytes(req.path, raw, user_id=req.user_id)
    return {"text": text}


@app.post("/computer/clipboard/read")
async def computer_clipboard_read(req: ComputerUserRequest) -> dict[str, str]:
    from . import computer
    from .computer_access import computer_denied_message

    denied = computer_denied_message(req.user_id)
    if denied:
        return {"text": denied}
    return {"text": await computer.clipboard_read(user_id=req.user_id)}


@app.post("/computer/see")
async def computer_see_ep(req: SeeRequest) -> dict[str, str]:
    from . import computer
    from .computer_access import computer_denied_message

    denied = computer_denied_message(req.user_id)
    if denied:
        return {"text": denied}
    return {"text": await computer.see_screen(req.question, user_id=req.user_id)}


@app.get("/computer/macros")
async def computer_macros_list() -> dict[str, Any]:
    from .macros import list_macros

    return {"macros": list_macros()}


@app.post("/computer/macro/run")
async def computer_macro_run(req: MacroRunRequest) -> dict[str, str]:
    from .computer_access import computer_denied_message
    from .macros import run_macro

    denied = computer_denied_message(req.user_id)
    if denied:
        return {"text": denied}
    return {"text": await run_macro(req.name, req.user_id)}


@app.post("/computer/trust")
async def computer_trust_ep(req: TrustRequest) -> dict[str, str]:
    from .computer_trust import grant_trust

    await grant_trust(req.user_id)
    return {"status": "trusted", "ttl_seconds": "1800"}


@app.delete("/computer/trust")
async def computer_revoke_trust_ep(req: TrustRequest) -> dict[str, str]:
    from .computer_trust import revoke_trust

    await revoke_trust(req.user_id)
    return {"status": "revoked"}


@app.get("/computer/pending")
async def computer_pending_ep(user_id: int) -> dict[str, Any]:
    from .computer_confirm import load_pending_raw

    return await load_pending_raw(user_id)


@app.get("/computer/audit")
async def computer_audit_ep(limit: int = 20) -> dict[str, Any]:
    from .computer_audit import tail_actions

    return {"entries": tail_actions(limit=limit)}


@app.get("/computer/learned")
async def computer_learned_ep() -> dict[str, Any]:
    from .computer_learned import learned_summary

    return learned_summary()


@app.get("/reminders/ics")
async def reminders_ics_ep(user_id: int) -> Any:
    from fastapi.responses import Response

    from .reminders import export_ics

    body = await export_ics(user_id)
    if not body.strip():
        raise HTTPException(status_code=404, detail="no reminders")
    return Response(
        content=body,
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="jarvis-reminders.ics"'},
    )


@app.get("/dataset/stats")
async def dataset_stats_ep(user_id: int | None = None) -> dict[str, Any]:
    from .train_scheduler import retrain_status

    return retrain_status(user_id)


@app.post("/dataset/export/mark")
async def dataset_export_mark_ep(user_id: int | None = None) -> dict[str, Any]:
    from .train_scheduler import mark_exported

    return mark_exported(user_id)


@app.post("/dataset/export/sharegpt")
async def dataset_export_ep(
    user_id: int | None = None,
    limit: int = 0,
) -> dict[str, Any]:
    from pathlib import Path

    from .dataset_export import write_sharegpt_jsonl

    from .train_scheduler import mark_exported

    dest = Path(settings.data_dir) / "twin" / "export" / "sharegpt.jsonl"
    info = write_sharegpt_jsonl(dest, user_id=user_id, limit=limit)
    info["scheduler"] = mark_exported(user_id)
    return info


@app.get("/tasks")
async def tasks_list_ep(user_id: int) -> dict[str, str]:
    from .tasks import list_tasks

    return {"text": await list_tasks(user_id)}


@app.delete("/tasks")
async def tasks_cancel_ep(user_id: int) -> dict[str, str]:
    from .tasks import cancel

    await cancel(user_id)
    return {"status": "cancelled"}


@app.get("/jobs")
async def jobs_list_ep(user_id: int) -> dict[str, str]:
    from .jobs import list_jobs

    return {"text": await list_jobs(user_id)}


@app.get("/jobs/due")
async def jobs_due_ep() -> dict[str, Any]:
    from .jobs import due_jobs

    return {"jobs": await due_jobs()}
