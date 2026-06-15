"""JARVIS Twin — SyncServer: ingest логів з Edge + serve активної LoRA.

Реалізує DESIGN.md §8.1 (Sync Protocol) поверх ModelRegistry + JsonlLog.
Edge пушить delta сесій (`POST /ingest/logs`), тягне активну LoRA (`GET /latest/lora`).
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .config import settings
from .lora_paths import resolve_lora_path
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


class RegisterLoraRequest(BaseModel):
    version: str
    path: str
    eval_score: float | None = None
    dataset_size: int | None = None
    train_epochs: int | None = None
    notes: str | None = None


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


@app.get("/registry/lora/active/download")
async def download_active_lora(request: Request) -> FileResponse:
    """Edge pull: завантажити GGUF активної LoRA."""
    active = request.app.state.registry.get_active()
    if active is None:
        raise HTTPException(status_code=404, detail="no active lora")
    try:
        path = resolve_lora_path(str(active["path"]), Path(settings.data_dir))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(path, filename=path.name, media_type="application/octet-stream")


@app.get("/status")
async def status(request: Request) -> dict[str, Any]:
    edges = {eid: lg.count() for eid, lg in request.app.state.edge_logs.items()}
    return {"edges": edges, "active_lora": request.app.state.registry.get_active()}


# --- ModelRegistry HTTP (DESIGN §7.4) ---


@app.get("/registry/versions")
async def list_lora_versions(request: Request) -> dict[str, Any]:
    return {"versions": request.app.state.registry.list_versions()}


@app.post("/registry/lora")
async def register_lora(req: RegisterLoraRequest, request: Request) -> dict[str, Any]:
    reg: ModelRegistry = request.app.state.registry
    try:
        rid = reg.register_lora(
            req.version,
            req.path,
            eval_score=req.eval_score,
            dataset_size=req.dataset_size,
            train_epochs=req.train_epochs,
            notes=req.notes,
        )
    except Exception as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"id": rid, "version": req.version, "status": "candidate"}


@app.post("/registry/lora/{version}/promote")
async def promote_lora(version: str, request: Request) -> dict[str, Any]:
    reg: ModelRegistry = request.app.state.registry
    from .promote_gate import eval_promote_denied

    row = reg.get_version(version)
    if row is None:
        raise HTTPException(status_code=404, detail=f"unknown version: {version}")
    denied = eval_promote_denied(row, settings.min_eval_promote)
    if denied:
        raise HTTPException(status_code=400, detail=denied)
    try:
        reg.promote(version)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    active = reg.get_active()
    assert active is not None
    return {"version": active["version"], "status": active["status"]}


@app.post("/registry/lora/rollback")
async def rollback_lora(
    request: Request,
    n: int = Query(1, ge=1),
) -> dict[str, Any]:
    restored = request.app.state.registry.rollback(n)
    if restored is None:
        raise HTTPException(status_code=404, detail="no archived version to restore")
    return restored
