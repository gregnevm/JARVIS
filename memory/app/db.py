"""Доступ до PostgreSQL + pgvector (asyncpg pool)."""
from __future__ import annotations

import logging
from typing import Any

import asyncpg

from .budget import fit_token_budget

logger = logging.getLogger("jarvis.memory.db")


def to_vector_literal(embedding: list[float]) -> str:
    """list[float] → pgvector-літерал '[0.1,0.2,...]' (з кастом ::vector у запиті)."""
    return "[" + ",".join(repr(float(x)) for x in embedding) + "]"


class DB:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        from . import migrate as alembic_migrate

        alembic_migrate.upgrade_head()
        self._pool = await asyncpg.create_pool(self._dsn, min_size=1, max_size=5)
        meta = await alembic_migrate.get_schema_meta(self)
        warn = alembic_migrate.embed_dim_mismatch(meta)
        if warn:
            logger.warning(warn)

    async def migrate(self) -> None:
        """Alembic upgrade head (idempotent). Викликати окремо без connect()."""
        from . import migrate as alembic_migrate

        alembic_migrate.upgrade_head()

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

    async def add_project_file_embedding(
        self, user_id: int, content: str, embedding: list[float], project_id: int
    ) -> None:
        """Embedding чанка project-файлу (scoped RAG, CA-2.4). `message_id=NULL` —
        ці рядки належать файлу, не повідомленню; саме за `message_id IS NULL`
        їх відрізняємо у `clear_project_file_embeddings` при reindex."""
        async with self.pool.acquire() as con:
            await con.execute(
                "INSERT INTO embeddings (message_id, user_id, content, embedding, project_id) "
                "VALUES (NULL,$1,$2,$3::vector,$4)",
                user_id,
                content,
                to_vector_literal(embedding),
                project_id,
            )

    async def clear_project_file_embeddings(self, project_id: int) -> int:
        """Видаляє лише file-embeddings проєкту (message_id IS NULL) — message-RAG
        лишається. Повертає к-сть видалених (для reindex idempotent)."""
        async with self.pool.acquire() as con:
            res = await con.execute(
                "DELETE FROM embeddings WHERE project_id=$1 AND message_id IS NULL",
                project_id,
            )
        return int(res.split()[-1]) if res and res.split()[-1].isdigit() else 0

    async def all_project_file_contents(self, project_id: int) -> list[str]:
        """Повний (необрізаний) вміст усіх файлів проєкту — для reindex."""
        async with self.pool.acquire() as con:
            rows = await con.fetch(
                "SELECT content FROM project_files WHERE project_id=$1 ORDER BY created_at ASC",
                project_id,
            )
        return [str(r["content"] or "") for r in rows]

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

    async def read_project_files_content(
        self,
        project_id: int,
        *,
        max_total_tokens: int = 3000,
        max_per_file_tokens: int = 1200,
    ) -> list[dict[str, str]]:
        """Вміст файлів проєкту для інжекту в system prompt під ТОКЕН-бюджет (CA-2.5).

        Релевантність дають RAG-чанки (CA-2.4); тут — лише сукупна стеля обсягу."""
        async with self.pool.acquire() as con:
            rows = await con.fetch(
                "SELECT name, content FROM project_files "
                "WHERE project_id=$1 ORDER BY created_at ASC",
                project_id,
            )
        items = [
            {"name": str(r["name"] or "file"), "content": str(r["content"] or "")}
            for r in rows
        ]
        return fit_token_budget(
            items,
            max_total_tokens=max_total_tokens,
            max_per_item_tokens=max_per_file_tokens,
            key="content",
        )

    # ----------------------- Context Passports (P9/P10, C1) -----------------------
    @staticmethod
    def _context_json(r: asyncpg.Record) -> dict[str, Any]:
        return {
            "id": int(r["id"]),
            "kind": r["kind"],
            "source": r["source"],
            "summary": r["summary"],
            "tags": list(r["tags"] or []),
            "sensitivity": r["sensitivity"],
            "ref": r["ref"],
            "event_ts": r["event_ts"].isoformat() if r["event_ts"] else None,
            "created_at": r["created_at"].isoformat() if r["created_at"] else "",
        }

    async def add_context_event(
        self,
        *,
        user_id: int,
        kind: str,
        summary: str,
        tags: list[str],
        embedding: list[float] | None,
        org_id: str,
        source: str | None = None,
        sensitivity: str = "personal",
        ref: str | None = None,
        event_id: str | None = None,
        event_ts: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Записує паспорт контексту. Ідемпотентно по (user_id, event_id), якщо
        event_id заданий: дубль повертає {"inserted": False} і існуючий id."""
        import json as _json

        vec = to_vector_literal(embedding) if embedding is not None else None
        async with self.pool.acquire() as con:
            row = await con.fetchrow(
                "INSERT INTO context_events "
                "(user_id, org_id, event_id, kind, source, summary, tags, "
                " sensitivity, ref, payload, embedding, event_ts) "
                "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10::jsonb,$11::vector,$12) "
                "ON CONFLICT (user_id, event_id) WHERE event_id IS NOT NULL "
                "DO NOTHING RETURNING id",
                user_id,
                org_id,
                event_id,
                kind,
                source,
                summary,
                tags,
                sensitivity,
                ref,
                _json.dumps(payload or {}),
                vec,
                event_ts,
            )
            if row is not None:
                return {"id": int(row["id"]), "inserted": True}
            # Дубль (ідемпотентний повтор) — повертаємо існуючий id.
            existing = await con.fetchval(
                "SELECT id FROM context_events WHERE user_id=$1 AND event_id=$2",
                user_id,
                event_id,
            )
            return {"id": int(existing) if existing is not None else None, "inserted": False}

    async def search_context(
        self,
        user_id: int,
        embedding: list[float],
        top_k: int,
        *,
        tags: list[str] | None = None,
        since: str | None = None,
    ) -> list[dict[str, Any]]:
        """Семантичний ретрив по паспортах + опц. фільтр тегів (containment) і часу."""
        vec = to_vector_literal(embedding)
        async with self.pool.acquire() as con:
            rows = await con.fetch(
                "SELECT id, kind, source, summary, tags, sensitivity, ref, "
                "       event_ts, created_at, 1 - (embedding <=> $2::vector) AS score "
                "FROM context_events "
                "WHERE user_id=$1 AND embedding IS NOT NULL "
                "  AND ($4::text[] IS NULL OR tags @> $4) "
                "  AND ($5::timestamptz IS NULL OR created_at >= $5) "
                "ORDER BY embedding <=> $2::vector LIMIT $3",
                user_id,
                vec,
                top_k,
                tags,
                since,
            )
        out: list[dict[str, Any]] = []
        for r in rows:
            item = self._context_json(r)
            item["score"] = float(r["score"])
            out.append(item)
        return out

    async def recent_context(
        self,
        user_id: int,
        limit: int,
        *,
        kind: str | None = None,
        tags: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        async with self.pool.acquire() as con:
            rows = await con.fetch(
                "SELECT id, kind, source, summary, tags, sensitivity, ref, "
                "       event_ts, created_at "
                "FROM context_events "
                "WHERE user_id=$1 "
                "  AND ($3::text IS NULL OR kind=$3) "
                "  AND ($4::text[] IS NULL OR tags @> $4) "
                "ORDER BY created_at DESC LIMIT $2",
                user_id,
                limit,
                kind,
                tags,
            )
        return [self._context_json(r) for r in rows]

    async def purge_context(
        self,
        user_id: int,
        *,
        before: str | None = None,
        kind: str | None = None,
    ) -> int:
        """Видаляє паспорти користувача (фільтри before/kind). Повертає к-сть."""
        async with self.pool.acquire() as con:
            res = await con.execute(
                "DELETE FROM context_events "
                "WHERE user_id=$1 "
                "  AND ($2::timestamptz IS NULL OR created_at < $2) "
                "  AND ($3::text IS NULL OR kind=$3)",
                user_id,
                before,
                kind,
            )
        return int(res.split()[-1]) if res and res.split()[-1].isdigit() else 0

    async def context_ledger(self, user_id: int, *, recent_limit: int = 20) -> dict[str, Any]:
        """Журнал прозорості (E3): скільки/яких паспортів зібрано + останні. Лише власні (anti-IDOR)."""
        async with self.pool.acquire() as con:
            total = await con.fetchval(
                "SELECT count(*) FROM context_events WHERE user_id=$1", user_id
            )
            by_kind = await con.fetch(
                "SELECT kind, count(*) AS c FROM context_events WHERE user_id=$1 "
                "GROUP BY kind ORDER BY c DESC",
                user_id,
            )
            by_source = await con.fetch(
                "SELECT COALESCE(source,'—') AS source, count(*) AS c FROM context_events "
                "WHERE user_id=$1 GROUP BY source ORDER BY c DESC",
                user_id,
            )
            recent = await con.fetch(
                "SELECT id, kind, source, summary, tags, created_at FROM context_events "
                "WHERE user_id=$1 ORDER BY created_at DESC LIMIT $2",
                user_id,
                recent_limit,
            )
        return {
            "total": int(total or 0),
            "by_kind": {str(r["kind"]): int(r["c"]) for r in by_kind},
            "by_source": {str(r["source"]): int(r["c"]) for r in by_source},
            "recent": [self._context_json(r) for r in recent],
        }

    async def pending_context(self, user_id: int, limit: int) -> list[dict[str, Any]]:
        """Паспорти, що чекають дозведення (`pending:summary`) — з payload (raw) для job."""
        import json as _json

        async with self.pool.acquire() as con:
            rows = await con.fetch(
                "SELECT id, summary, tags, payload FROM context_events "
                "WHERE user_id=$1 AND tags @> ARRAY['pending:summary'] "
                "ORDER BY created_at ASC LIMIT $2",
                user_id,
                limit,
            )
        out: list[dict[str, Any]] = []
        for r in rows:
            payload = r["payload"]
            if isinstance(payload, str):
                payload = _json.loads(payload)
            out.append(
                {
                    "id": int(r["id"]),
                    "summary": r["summary"],
                    "tags": list(r["tags"] or []),
                    "payload": payload or {},
                }
            )
        return out

    async def update_context_event(
        self,
        event_db_id: int,
        user_id: int,
        *,
        summary: str,
        tags: list[str],
        embedding: list[float] | None,
    ) -> bool:
        """Оновлює summary+tags+embedding паспорта (для context_summarize). Ownership-guard."""
        vec = to_vector_literal(embedding) if embedding is not None else None
        async with self.pool.acquire() as con:
            res = await con.execute(
                "UPDATE context_events SET summary=$3, tags=$4, embedding=$5::vector "
                "WHERE id=$1 AND user_id=$2",
                event_db_id,
                user_id,
                summary,
                tags,
                vec,
            )
        return res.endswith("1")
