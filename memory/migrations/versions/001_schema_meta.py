"""schema_meta — версіонування embed dim та інших schema knobs.

Revision ID: 001_schema_meta
Revises:
Create Date: 2026-06-05
"""
from __future__ import annotations

from alembic import op

revision = "001_schema_meta"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        INSERT INTO schema_meta (key, value)
        VALUES ('embed_dim', '768')
        ON CONFLICT (key) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO schema_meta (key, value)
        VALUES ('embed_model', 'nomic-embed-text')
        ON CONFLICT (key) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS schema_meta")
