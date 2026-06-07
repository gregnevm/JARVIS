"""Alembic revisions + embed_dim guard."""
from __future__ import annotations

from pathlib import Path

from app.config import Settings
from app.migrate import embed_dim_mismatch


def test_sync_dsn_uses_psycopg2_driver():
    s = Settings()
    s.postgres_user = "u"
    s.postgres_password = "p"
    s.postgres_host = "h"
    s.postgres_port = 5432
    s.postgres_db = "d"
    assert s.sync_dsn == "postgresql+psycopg2://u:p@h:5432/d"


def test_embed_dim_mismatch_detected():
    s = Settings()
    s.embed_dim = 768
    assert embed_dim_mismatch({"embed_dim": "768"}) is None
    assert embed_dim_mismatch({"embed_dim": "1024"}) is not None


def test_embed_dim_missing_ok():
    assert embed_dim_mismatch({}) is None


def test_alembic_revisions_chain():
    versions = Path(__file__).resolve().parents[1] / "migrations" / "versions"
    files = sorted(versions.glob("*.py"))
    assert len(files) >= 2
    text = files[0].read_text(encoding="utf-8")
    assert "001_schema_meta" in text
    assert "schema_meta" in text
