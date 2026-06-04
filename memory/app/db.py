"""Доступ до PostgreSQL + pgvector (asyncpg pool)."""
from __future__ import annotations

import logging
from typing import Any

import asyncpg

logger = logging.getLogger("jarvis.memory.db")


def to_vector_literal(embedding: list[float]) -> str:
    """list[float] → pgvector-літерал '[0.1,0.2,...]' (з кастом ::vector у запиті)."""
    return "[" + ",".join(repr(float(x)) for x in embedding) + "]"


class DB:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        self._pool = await asyncpg.create_pool(self._dsn, min_size=1, max_size=5)

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()

    @property
    def pool(self) -> asyncpg.Pool:
        if self._pool is None:
            raise RuntimeError("DB pool not initialised")
        return self._pool

    async def health(self) -> bool:
        try:
            async with self.pool.acquire() as con:
                return bool(await con.fetchval("SELECT 1") == 1)
        except Exception as exc:  # noqa: BLE001 — health не має кидати
            logger.error("db health failed: %s", exc)
            return False

    async def get_or_create_session(self, user_id: int) -> int:
        async with self.pool.acquire() as con:
            row = await con.fetchrow(
                "SELECT id FROM sessions WHERE user_id=$1 ORDER BY updated_at DESC LIMIT 1",
                user_id,
            )
            if row is not None:
                return int(row["id"])
            new_id = await con.fetchval(
                "INSERT INTO sessions (user_id) VALUES ($1) RETURNING id", user_id
            )
            return int(new_id)

    async def add_message(self, session_id: int, user_id: int, role: str, content: str) -> int:
        async with self.pool.acquire() as con:
            msg_id = await con.fetchval(
                "INSERT INTO messages (session_id, user_id, role, content) "
                "VALUES ($1,$2,$3,$4) RETURNING id",
                session_id,
                user_id,
                role,
                content,
            )
            await con.execute("UPDATE sessions SET updated_at=now() WHERE id=$1", session_id)
            return int(msg_id)

    async def add_embedding(
        self, message_id: int, user_id: int, content: str, embedding: list[float]
    ) -> None:
        async with self.pool.acquire() as con:
            await con.execute(
                "INSERT INTO embeddings (message_id, user_id, content, embedding) "
                "VALUES ($1,$2,$3,$4::vector)",
                message_id,
                user_id,
                content,
                to_vector_literal(embedding),
            )

    async def search(
        self, user_id: int, embedding: list[float], top_k: int
    ) -> list[dict[str, Any]]:
        vec = to_vector_literal(embedding)
        async with self.pool.acquire() as con:
            rows = await con.fetch(
                "SELECT content, 1 - (embedding <=> $2::vector) AS score "
                "FROM embeddings WHERE user_id=$1 "
                "ORDER BY embedding <=> $2::vector LIMIT $3",
                user_id,
                vec,
                top_k,
            )
        return [{"content": r["content"], "score": float(r["score"])} for r in rows]

    async def recent_messages(self, user_id: int, limit: int) -> list[dict[str, Any]]:
        async with self.pool.acquire() as con:
            rows = await con.fetch(
                "SELECT role, content FROM messages WHERE user_id=$1 "
                "ORDER BY created_at DESC LIMIT $2",
                user_id,
                limit,
            )
        return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

    async def list_sessions(self, user_id: int, limit: int = 10) -> list[dict[str, Any]]:
        async with self.pool.acquire() as con:
            rows = await con.fetch(
                "SELECT s.id, s.updated_at, "
                "(SELECT LEFT(m.content, 120) FROM messages m "
                " WHERE m.session_id = s.id ORDER BY m.created_at DESC LIMIT 1) AS preview "
                "FROM sessions s WHERE s.user_id=$1 "
                "ORDER BY s.updated_at DESC LIMIT $2",
                user_id,
                limit,
            )
        out: list[dict[str, Any]] = []
        for r in rows:
            out.append(
                {
                    "session_id": int(r["id"]),
                    "updated_at": r["updated_at"].isoformat() if r["updated_at"] else "",
                    "preview": (r["preview"] or "").strip(),
                }
            )
        return out
