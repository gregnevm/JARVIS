"""Alembic upgrade helper (Phase 3.3 / 5)."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from alembic import command
from alembic.config import Config

from .config import settings

if TYPE_CHECKING:
    from .db import DB

logger = logging.getLogger("jarvis.memory.migrate")

_ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"


def upgrade_head() -> None:
    cfg = Config(str(_ALEMBIC_INI))
    cfg.set_main_option("sqlalchemy.url", settings.sync_dsn)
    logger.info("alembic upgrade head (embed_dim=%s)", settings.embed_dim)
    command.upgrade(cfg, "head")


async def get_schema_meta(db: "DB") -> dict[str, str]:
    """Поточні schema_meta key/value (порожньо якщо таблиці ще немає)."""
    try:
        async with db.pool.acquire() as con:
            rows = await con.fetch("SELECT key, value FROM schema_meta")
        return {str(r["key"]): str(r["value"]) for r in rows}
    except Exception as exc:  # noqa: BLE001
        logger.debug("schema_meta read failed: %s", exc)
        return {}


def embed_dim_mismatch(meta: dict[str, str]) -> str | None:
    stored = meta.get("embed_dim")
    if not stored:
        return None
    try:
        if int(stored) != int(settings.embed_dim):
            return f"embed_dim mismatch: db={stored} env={settings.embed_dim} — потрібна міграція/re-embed"
    except ValueError:
        return f"invalid embed_dim in schema_meta: {stored!r}"
    return None


async def column_embed_dim(db: "DB") -> int | None:
    """РЕАЛЬНА розмірність pgvector-колонки `embeddings.embedding` з каталогу pg.

    Для типу `vector` atttypmod == розмірність (напр. 768); -1 = без фіксованої.
    Це джерело істини, якого schema_meta-перевірка не торкається.
    """
    try:
        async with db.pool.acquire() as con:
            val = await con.fetchval(
                """
                SELECT a.atttypmod
                FROM pg_attribute a
                JOIN pg_class c ON c.oid = a.attrelid
                WHERE c.relname = 'embeddings' AND a.attname = 'embedding'
                  AND NOT a.attisdropped
                """
            )
        if val is None or int(val) < 0:
            return None
        return int(val)
    except Exception as exc:  # noqa: BLE001 — діагностика, не має кидати на старті
        logger.debug("column embed_dim read failed: %s", exc)
        return None


def column_dim_mismatch(col_dim: int | None) -> str | None:
    """Звіряє РЕАЛЬНУ розмірність pgvector-колонки з env EMBED_DIM.

    Ловить дрейф моделі/env, який schema_meta-перевірка пропускає (обидві сторони
    там — hardcoded 768): напр. колонка `vector(768)` проти env `EMBED_DIM=1024`
    після зміни EMBED_MODEL → pgvector кинув би помилку аж на INSERT.
    """
    if col_dim is None:
        return None
    if col_dim != int(settings.embed_dim):
        return (
            f"embed_dim mismatch: column=vector({col_dim}) env={settings.embed_dim} "
            "— pgvector кине помилку на INSERT; потрібна міграція/re-embed"
        )
    return None
