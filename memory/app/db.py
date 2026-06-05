"""Доступ до PostgreSQL + pgvector (asyncpg pool)."""
from __future__ import annotations

import logging
from typing import Any

import asyncpg

logger = logging.getLogger("jarvis.memory.db")


def to_vector_literal(embedding: list[float]) -> str:
    """list[float] → pgvector-літерал '[0.1,0.2,...]' (з кастом ::vector у запиті)."""
    return "[" + ",".join(repr(float(x)) for x in embedding) + "]"


# Ідемпотентні міграції (P1 Projects). init.sql покриває fresh install; це — для
# наявних БД (init.sql не перезапускається). Виконуються при кожному connect().
_MIGRATIONS: tuple[str, ...] = (
    """CREATE TABLE IF NOT EXISTS projects (
        id BIGSERIAL PRIMARY KEY, user_id BIGINT NOT NULL, name TEXT NOT NULL,
        system_prompt TEXT NOT NULL DEFAULT '', archived BOOLEAN NOT NULL DEFAULT false,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now())""",
    "CREATE INDEX IF NOT EXISTS idx_projects_user ON projects (user_id, archived)",
    """CREATE TABLE IF NOT EXISTS project_files (
        id BIGSERIAL PRIMARY KEY,
        project_id BIGINT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        name TEXT NOT NULL, content TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now())""",
    "CREATE INDEX IF NOT EXISTS idx_project_files_project ON project_files (project_id)",
    "ALTER TABLE messages ADD COLUMN IF NOT EXISTS project_id BIGINT "
    "REFERENCES projects(id) ON DELETE SET NULL",
    "ALTER TABLE embeddings ADD COLUMN IF NOT EXISTS project_id BIGINT "
    "REFERENCES projects(id) ON DELETE SET NULL",
    "CREATE INDEX IF NOT EXISTS idx_embeddings_user_project ON embeddings (user_id, project_id)",
)


class DB:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        self._pool = await asyncpg.create_pool(self._dsn, min_size=1, max_size=5)
        await self.migrate()

    async def migrate(self) -> None:
        """Прокочує ідемпотентні DDL (P1). Безпечно на наявних і чистих БД."""
        async with self.pool.acquire() as con:
            for stmt in _MIGRATIONS:
                await con.execute(stmt)

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

    async def add_message(
        self,
        session_id: int,
        user_id: int,
        role: str,
        content: str,
        project_id: int | None = None,
    ) -> int:
        async with self.pool.acquire() as con:
            msg_id = await con.fetchval(
                "INSERT INTO messages (session_id, user_id, role, content, project_id) "
                "VALUES ($1,$2,$3,$4,$5) RETURNING id",
                session_id,
                user_id,
                role,
                content,
                project_id,
            )
            await con.execute("UPDATE sessions SET updated_at=now() WHERE id=$1", session_id)
            return int(msg_id)

    async def add_embedding(
        self,
        message_id: int,
        user_id: int,
        content: str,
        embedding: list[float],
        project_id: int | None = None,
    ) -> None:
        async with self.pool.acquire() as con:
            await con.execute(
                "INSERT INTO embeddings (message_id, user_id, content, embedding, project_id) "
                "VALUES ($1,$2,$3,$4::vector,$5)",
                message_id,
                user_id,
                content,
                to_vector_literal(embedding),
                project_id,
            )

    async def search(
        self,
        user_id: int,
        embedding: list[float],
        top_k: int,
        project_id: int | None = None,
    ) -> list[dict[str, Any]]:
        """Scoped RAG: project_id фільтрує точно (None=загальний). `IS NOT DISTINCT
        FROM` коректно матчить NULL=NULL → 0 cross-project leak (KPI §7)."""
        vec = to_vector_literal(embedding)
        async with self.pool.acquire() as con:
            rows = await con.fetch(
                "SELECT content, 1 - (embedding <=> $2::vector) AS score "
                "FROM embeddings WHERE user_id=$1 AND project_id IS NOT DISTINCT FROM $4 "
                "ORDER BY embedding <=> $2::vector LIMIT $3",
                user_id,
                vec,
                top_k,
                project_id,
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

    # ----------------------- Projects (P1) -----------------------
    @staticmethod
    def _project_json(r: asyncpg.Record) -> dict[str, Any]:
        return {
            "id": int(r["id"]),
            "user_id": int(r["user_id"]),
            "name": r["name"],
            "system_prompt": r["system_prompt"],
            "archived": bool(r["archived"]),
            "updated_at": r["updated_at"].isoformat() if r["updated_at"] else "",
        }

    async def create_project(
        self, user_id: int, name: str, system_prompt: str = ""
    ) -> dict[str, Any]:
        async with self.pool.acquire() as con:
            row = await con.fetchrow(
                "INSERT INTO projects (user_id, name, system_prompt) VALUES ($1,$2,$3) "
                "RETURNING *",
                user_id,
                name,
                system_prompt,
            )
        return self._project_json(row)

    async def list_projects(
        self, user_id: int, include_archived: bool = False
    ) -> list[dict[str, Any]]:
        sql = "SELECT * FROM projects WHERE user_id=$1"
        if not include_archived:
            sql += " AND archived=false"
        sql += " ORDER BY updated_at DESC"
        async with self.pool.acquire() as con:
            rows = await con.fetch(sql, user_id)
        return [self._project_json(r) for r in rows]

    async def get_project(self, project_id: int, user_id: int) -> dict[str, Any] | None:
        async with self.pool.acquire() as con:
            row = await con.fetchrow(
                "SELECT * FROM projects WHERE id=$1 AND user_id=$2", project_id, user_id
            )
        return self._project_json(row) if row else None

    async def update_project(
        self,
        project_id: int,
        user_id: int,
        *,
        name: str | None = None,
        system_prompt: str | None = None,
        archived: bool | None = None,
    ) -> dict[str, Any] | None:
        async with self.pool.acquire() as con:
            row = await con.fetchrow(
                "UPDATE projects SET "
                "name=COALESCE($3,name), system_prompt=COALESCE($4,system_prompt), "
                "archived=COALESCE($5,archived), updated_at=now() "
                "WHERE id=$1 AND user_id=$2 RETURNING *",
                project_id,
                user_id,
                name,
                system_prompt,
                archived,
            )
        return self._project_json(row) if row else None

    async def delete_project(self, project_id: int, user_id: int) -> bool:
        async with self.pool.acquire() as con:
            res = await con.execute(
                "DELETE FROM projects WHERE id=$1 AND user_id=$2", project_id, user_id
            )
        return res.endswith("1")

    async def add_project_file(self, project_id: int, name: str, content: str) -> int:
        async with self.pool.acquire() as con:
            file_id = await con.fetchval(
                "INSERT INTO project_files (project_id, name, content) VALUES ($1,$2,$3) "
                "RETURNING id",
                project_id,
                name,
                content,
            )
            await con.execute("UPDATE projects SET updated_at=now() WHERE id=$1", project_id)
        return int(file_id)

    async def list_project_files(self, project_id: int) -> list[dict[str, Any]]:
        async with self.pool.acquire() as con:
            rows = await con.fetch(
                "SELECT id, name, LENGTH(content) AS size, created_at FROM project_files "
                "WHERE project_id=$1 ORDER BY created_at DESC",
                project_id,
            )
        return [
            {
                "id": int(r["id"]),
                "name": r["name"],
                "size": int(r["size"]),
                "created_at": r["created_at"].isoformat() if r["created_at"] else "",
            }
            for r in rows
        ]

    async def delete_project_file(self, file_id: int, project_id: int) -> bool:
        async with self.pool.acquire() as con:
            res = await con.execute(
                "DELETE FROM project_files WHERE id=$1 AND project_id=$2", file_id, project_id
            )
        return res.endswith("1")
