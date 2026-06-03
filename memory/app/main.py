"""JARVIS Memory service — RAG: embeddings + retrieval (pgvector)."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .config import settings
from .db import DB
from .rag import Embedder, chunk_text

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("jarvis.memory")


class EmbedRequest(BaseModel):
    text: str


class StoreRequest(BaseModel):
    user_id: int
    content: str
    role: str = "user"
    session_id: int | None = None


class SearchRequest(BaseModel):
    user_id: int
    query: str
    top_k: int = 5


class HistoryRequest(BaseModel):
    user_id: int
    limit: int | None = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.db = DB(settings.dsn)
    await app.state.db.connect()
    app.state.embedder = Embedder(settings.ollama_host, settings.embed_model)
    logger.info("Memory up. embed_model=%s", settings.embed_model)
    yield
    await app.state.embedder.aclose()
    await app.state.db.close()


app = FastAPI(title="JARVIS Memory", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, Any]:
    ok = await app.state.db.health()
    return {"status": "ok" if ok else "degraded", "db": ok}


@app.post("/embed")
async def embed(req: EmbedRequest) -> dict[str, Any]:
    try:
        vec = await app.state.embedder.embed(req.text)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"embed failed: {exc}") from exc
    return {"dim": len(vec), "embedding": vec}


@app.post("/store")
async def store(req: StoreRequest) -> dict[str, Any]:
    db: DB = app.state.db
    session_id = req.session_id or await db.get_or_create_session(req.user_id)
    msg_id = await db.add_message(session_id, req.user_id, req.role, req.content)
    stored = 0
    for chunk in chunk_text(req.content):
        try:
            vec = await app.state.embedder.embed(chunk)
        except Exception as exc:  # noqa: BLE001
            logger.error("embed failed for chunk: %s", exc)
            continue
        await db.add_embedding(msg_id, req.user_id, chunk, vec)
        stored += 1
    return {"message_id": msg_id, "session_id": session_id, "chunks_stored": stored}


@app.post("/search")
async def search(req: SearchRequest) -> dict[str, Any]:
    try:
        vec = await app.state.embedder.embed(req.query)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"embed failed: {exc}") from exc
    results = await app.state.db.search(req.user_id, vec, req.top_k)
    return {"results": results}


@app.post("/history")
async def history(req: HistoryRequest) -> dict[str, Any]:
    limit = req.limit or settings.short_term_limit
    msgs = await app.state.db.recent_messages(req.user_id, limit)
    return {"messages": msgs}
