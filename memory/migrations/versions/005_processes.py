"""processes — BPO store (Стовп D, TC-6).

Довгоживучі cross-actor бізнес-процеси. Кроки тримаємо як JSONB (домен
`jarvis_core.process` оперує цілим Process), статус + org/squad — колонки для
фільтрів видимості. Audit переходів — у наявний підхід (поки лог; повний audit_log
SAAS §3.1 — окремо).

Revision ID: 005_processes
Revises: 004_team_ecosystem
Create Date: 2026-06-17
"""
from __future__ import annotations

from alembic import op

revision = "005_processes"
down_revision = "004_team_ecosystem"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS processes (
            id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id        TEXT NOT NULL,
            owner_user_id TEXT NOT NULL,
            squad_id      UUID REFERENCES squads(id) ON DELETE SET NULL,
            title         TEXT NOT NULL,
            template      TEXT,
            status        TEXT NOT NULL DEFAULT 'draft',
            steps         JSONB NOT NULL DEFAULT '[]'::jsonb,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_processes_org ON processes (org_id, status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_processes_squad ON processes (squad_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_processes_squad")
    op.execute("DROP INDEX IF EXISTS idx_processes_org")
    op.execute("DROP TABLE IF EXISTS processes")
