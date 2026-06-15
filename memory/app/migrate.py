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
