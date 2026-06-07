"""projects + project_files (P1) — для БД без свіжого init.sql.

Revision ID: 002_projects
Revises: 001_schema_meta
Create Date: 2026-06-05
"""
from __future__ import annotations

from alembic import op

revision = "002_projects"
down_revision = "001_schema_meta"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS projects (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            name TEXT NOT NULL,
            system_prompt TEXT NOT NULL DEFAULT '',
            archived BOOLEAN NOT NULL DEFAULT false,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_projects_user ON projects (user_id, archived)"
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS project_files (
            id BIGSERIAL PRIMARY KEY,
            project_id BIGINT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_project_files_project ON project_files (project_id)"
    )
    op.execute(
        """
        ALTER TABLE messages ADD COLUMN IF NOT EXISTS project_id BIGINT
        REFERENCES projects(id) ON DELETE SET NULL
        """
    )
    op.execute(
        """
        ALTER TABLE embeddings ADD COLUMN IF NOT EXISTS project_id BIGINT
        REFERENCES projects(id) ON DELETE SET NULL
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_embeddings_user_project "
        "ON embeddings (user_id, project_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_embeddings_user_project")
    op.execute("ALTER TABLE embeddings DROP COLUMN IF EXISTS project_id")
    op.execute("ALTER TABLE messages DROP COLUMN IF EXISTS project_id")
    op.execute("DROP INDEX IF EXISTS idx_project_files_project")
    op.execute("DROP TABLE IF EXISTS project_files")
    op.execute("DROP INDEX IF EXISTS idx_projects_user")
    op.execute("DROP TABLE IF EXISTS projects")
