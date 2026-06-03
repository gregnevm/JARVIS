"""JARVIS Twin — SyncServer: ingest логів з Edge + serve активної LoRA.

Реалізує DESIGN.md §8.1 (Sync Protocol) поверх ModelRegistry + JsonlLog.
Edge пушить delta сесій (`POST /ingest/logs`), тягне активну LoRA (`GET /latest/lora`).
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import FastAPI, Request
from pydantic import BaseModel

from .config import settings
from .registry import ModelRegistry
from .session_log import JsonlLog

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("jarvis.twin.sync")


class IngestRequest(BaseModel):
    edge_id: str
    delta_start_idx: int = 0
    logs: list[dict[str, Any]]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    Path(settings.data_dir).mkdir(parents=True, exist_ok=True)
    app.state.registry = ModelRegistry(settings.registry_db)
    app.state.edge_logs = {}  # edge_id -> JsonlLog
    logger.info("Twin SyncServer up. data_dir=%s", settings.data_dir)
    yield
    app.state.registry.close()


app = FastAPI(title="JARVIS Twin SyncServer", lifespan=lifespan)


def _edge_log(app: FastAPI, edge_id: str) -> JsonlLog:
    # Санітизація edge_id → безпечне імʼя файлу (без path traversal).
    safe = "".join(c for c in edge_id if c.isalnum() or c in "_-")[:64] or "unknown"
    logs = app.state.edge_logs
    if safe not in logs:
        logs[safe] = JsonlLog(Path(settings.data_dir) / "ingest" / f"{safe}.jsonl")
    return logs[safe]


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/ingest/logs")
async def ingest_logs(req: IngestRequest, request: Request) -> dict[str, Any]:
    log = _edge_log(request.app, req.edge_id)
    for entry in req.logs:
        log.append(entry)
    return {"accepted": len(req.logs), "last_idx": log.count()}


@app.get("/latest/lora")
async def latest_lora(request: Request) -> dict[str, Any]:
    active = request.app.state.registry.get_active()
    if active is None:
        return {"version": None}
    return {
        "version": active["version"],
        "eval_score": active["eval_score"],
        "path": active["path"],
    }


@app.get("/status")
async def status(request: Request) -> dict[str, Any]:
    edges = {eid: lg.count() for eid, lg in request.app.state.edge_logs.items()}
    return {"edges": edges, "active_lora": request.app.state.registry.get_active()}
