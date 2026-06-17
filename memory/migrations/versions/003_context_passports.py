"""context_events — Context Passport store (P9 summarize-all + P10 tag-everything).

Наскрізна культура зі статуту (AGENTS.md C1, DESIGN.md §1.2.1): кожен значущий
артефакт входить із паспортом — kind + summary + namespaced tags + embedding(768D).
Ця таблиця — перший конкретний носій культури (ambient-контекст, нотатки, daily).

Revision ID: 003_context_passports
Revises: 002_projects
Create Date: 2026-06-16
"""
from __future__ import annotations

from alembic import op

revision = "003_context_passports"
down_revision = "002_projects"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS context_events (
            id          BIGSERIAL    PRIMARY KEY,
            user_id     BIGINT       NOT NULL,
            org_id      TEXT         NOT NULL DEFAULT '00000000-0000-0000-0000-000000000001',
            event_id    TEXT,
            kind        TEXT         NOT NULL,
            source      TEXT,
            summary     TEXT         NOT NULL,
            tags        TEXT[]       NOT NULL DEFAULT '{}',
            sensitivity TEXT         NOT NULL DEFAULT 'personal',
            ref         TEXT,
            payload     JSONB        NOT NULL DEFAULT '{}'::jsonb,
            embedding   vector(768),
            event_ts    TIMESTAMPTZ,
            created_at  TIMESTAMPTZ  NOT NULL DEFAULT now()
        )
        """
    )
    # Ідемпотентність: клієнтський event_id унікальний у межах user (партіальний —
    # лише коли event_id заданий; ручні нотатки без event_id завжди вставляються).
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_context_events_idem "
        "ON context_events (user_id, event_id) WHERE event_id IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_context_events_user_time "
        "ON context_events (user_id, created_at DESC)"
    )
    # GIN по тегах — швидкий containment-фільтр (tags @> '{person:mom}') (P10 індексація).
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_context_events_tags "
        "ON context_events USING gin (tags)"
    )
    # HNSW по summary-embedding — семантичний ретрив (NULL-вектори індекс пропускає).
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_context_events_vec "
        "ON context_events USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_context_events_vec")
    op.execute("DROP INDEX IF EXISTS idx_context_events_tags")
    op.execute("DROP INDEX IF EXISTS idx_context_events_user_time")
    op.execute("DROP INDEX IF EXISTS idx_context_events_idem")
    op.execute("DROP TABLE IF EXISTS context_events")
