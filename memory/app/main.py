"""JARVIS Memory service — RAG: embeddings + retrieval (pgvector)."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

import redis.asyncio as aioredis
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .config import settings
from .db import DB
from .rag import Embedder, chunk_text

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
# httpx за замовчуванням пише повний URL у INFO. Memory кличе Ollama embeddings
# без секретів у URL, але уніфікуємо рівень логування з gateway/tools — менше шуму.
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("jarvis.memory")


class EmbedRequest(BaseModel):
    text: str


class StoreRequest(BaseModel):
    user_id: int
    content: str
    role: str = "user"
    session_id: int | None = None
    project_id: int | None = None


class SearchRequest(BaseModel):
    user_id: int
    query: str
    top_k: int = 5
    project_id: int | None = None


class HistoryRequest(BaseModel):
    user_id: int
    limit: int | None = None


class SessionsRequest(BaseModel):
    user_id: int
    limit: int = 10


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.db = DB(settings.dsn)
    await app.state.db.connect()
    app.state.redis = aioredis.from_url(
        settings.redis_url, encoding="utf-8", decode_responses=True
    )
    app.state.embedder = Embedder(
        settings.ollama_host,
        settings.embed_model,
        redis=app.state.redis,
        cache_ttl=settings.embed_cache_ttl,
    )
    logger.info("Memory up. embed_model=%s (redis cache on)", settings.embed_model)
    yield
    await app.state.embedder.aclose()
    await app.state.redis.aclose()
    await app.state.db.close()


app = FastAPI(title="JARVIS Memory", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, Any]:
    from .migrate import embed_dim_mismatch, get_schema_meta

    ok = await app.state.db.health()
    meta = await get_schema_meta(app.state.db)
    warn = embed_dim_mismatch(meta)
    out: dict[str, Any] = {
        "status": "ok" if ok else "degraded",
        "db": ok,
        "embed_dim": settings.embed_dim,
        "embed_model": settings.embed_model,
    }
    if meta:
        out["schema_meta"] = meta
    if warn:
        out["schema_warn"] = warn
    return out


async def _embed_or_502(text: str) -> list[float]:
    """`await app.state.embedder.embed(text)`, або 502 `HTTPException("embed failed: …")`.

    Узагальнює try/except, побайтово повторений у `embed`/`search` (2 рази) —
    обидва ендпоінти ембедять текст напряму (на відміну від `store`, де помилка
    ембедингу окремого chunk'а нефатальна — там лишається `continue`+log)."""
    try:
        return await app.state.embedder.embed(text)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"embed failed: {exc}") from exc


@app.post("/embed")
async def embed(req: EmbedRequest) -> dict[str, Any]:
    vec = await _embed_or_502(req.text)
    return {"dim": len(vec), "embedding": vec}


@app.post("/store")
async def store(req: StoreRequest) -> dict[str, Any]:
    db: DB = app.state.db
    session_id = req.session_id or await db.get_or_create_session(req.user_id)
    msg_id = await db.add_message(
        session_id, req.user_id, req.role, req.content, project_id=req.project_id
    )
    stored = 0
    for chunk in chunk_text(req.content):
        try:
            vec = await app.state.embedder.embed(chunk)
        except Exception as exc:  # noqa: BLE001
            logger.error("embed failed for chunk: %s", exc)
            continue
        await db.add_embedding(msg_id, req.user_id, chunk, vec, project_id=req.project_id)
        stored += 1
    return {"message_id": msg_id, "session_id": session_id, "chunks_stored": stored}


@app.post("/search")
async def search(req: SearchRequest) -> dict[str, Any]:
    vec = await _embed_or_502(req.query)
    results = await app.state.db.search(req.user_id, vec, req.top_k, project_id=req.project_id)
    return {"results": results}


@app.post("/history")
async def history(req: HistoryRequest) -> dict[str, Any]:
    limit = req.limit or settings.short_term_limit
    msgs = await app.state.db.recent_messages(req.user_id, limit)
    return {"messages": msgs}


@app.get("/sessions")
async def sessions(user_id: int, limit: int = 10) -> dict[str, Any]:
    lim = max(1, min(limit, 30))
    items = await app.state.db.list_sessions(user_id, lim)
    return {"sessions": items}


# ----------------------- Projects (P1) -----------------------
class ProjectCreate(BaseModel):
    user_id: int
    name: str
    system_prompt: str = ""


class ProjectUpdate(BaseModel):
    user_id: int
    name: str | None = None
    system_prompt: str | None = None
    archived: bool | None = None


class ProjectFileCreate(BaseModel):
    user_id: int
    name: str
    content: str


@app.post("/projects")
async def projects_create(req: ProjectCreate) -> dict[str, Any]:
    name = req.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="name required")
    return await app.state.db.create_project(req.user_id, name[:200], req.system_prompt[:8000])


@app.get("/projects")
async def projects_list(user_id: int, include_archived: bool = False) -> dict[str, Any]:
    items = await app.state.db.list_projects(user_id, include_archived)
    return {"projects": items}


@app.get("/projects/{project_id}")
async def projects_get(
    project_id: int, user_id: int, include_content: bool = False
) -> dict[str, Any]:
    proj = await app.state.db.get_project(project_id, user_id)
    if proj is None:
        raise HTTPException(status_code=404, detail="project not found")
    proj["files"] = await app.state.db.list_project_files(project_id)
    if include_content:
        proj["files_content"] = await app.state.db.read_project_files_content(
            project_id,
            max_total_chars=settings.project_files_max_total_chars,
            max_per_file=settings.project_files_max_per_file,
        )
    return proj


@app.patch("/projects/{project_id}")
async def projects_update(project_id: int, req: ProjectUpdate) -> dict[str, Any]:
    name = req.name.strip()[:200] if req.name is not None else None
    sp = req.system_prompt[:8000] if req.system_prompt is not None else None
    proj = await app.state.db.update_project(
        project_id, req.user_id, name=name, system_prompt=sp, archived=req.archived
    )
    if proj is None:
        raise HTTPException(status_code=404, detail="project not found")
    return proj


@app.delete("/projects/{project_id}")
async def projects_delete(project_id: int, user_id: int) -> dict[str, Any]:
    ok = await app.state.db.delete_project(project_id, user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="project not found")
    return {"ok": True}


async def _require_project(db: DB, project_id: int, user_id: int) -> None:
    """404 "project not found", якщо проєкт відсутній або не належить user_id.

    Узагальнює guard `if await db.get_project(...) is None: raise ...`, що
    повторювався тричі (побайтово, лише ім'я user_id-аргументу різнилось)
    у `project_file_{add,list,delete}`."""
    if await db.get_project(project_id, user_id) is None:
        raise HTTPException(status_code=404, detail="project not found")


@app.post("/projects/{project_id}/files")
async def project_file_add(project_id: int, req: ProjectFileCreate) -> dict[str, Any]:
    await _require_project(app.state.db, project_id, req.user_id)
    name = req.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="name required")
    file_id = await app.state.db.add_project_file(project_id, name[:200], req.content)
    return {"id": file_id, "name": name}


@app.get("/projects/{project_id}/files")
async def project_files_list(project_id: int, user_id: int) -> dict[str, Any]:
    await _require_project(app.state.db, project_id, user_id)
    return {"files": await app.state.db.list_project_files(project_id)}


@app.delete("/projects/{project_id}/files/{file_id}")
async def project_file_delete(project_id: int, file_id: int, user_id: int) -> dict[str, Any]:
    await _require_project(app.state.db, project_id, user_id)
    ok = await app.state.db.delete_project_file(file_id, project_id)
    if not ok:
        raise HTTPException(status_code=404, detail="file not found")
    return {"ok": True}
