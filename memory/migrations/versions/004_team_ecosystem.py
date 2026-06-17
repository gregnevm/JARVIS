"""team ecosystem — squads / relationships / delegates / tg-groups (Стовп D, TC-0).

Граф зв'язків організації + командна видимість паспортів. Розширює SAAS tenant-ґрунт
(org_id уже в context_events). Усе org-scoped; solo-user (один synthetic org) працює
як раніше — нові таблиці просто порожні (S2).

Revision ID: 004_team_ecosystem
Revises: 003_context_passports
Create Date: 2026-06-17
"""
from __future__ import annotations

from alembic import op

revision = "004_team_ecosystem"
down_revision = "003_context_passports"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Піддерево організації: відділи / проєктні групи (ієрархія через parent_id).
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS squads (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id      TEXT NOT NULL,
            parent_id   UUID REFERENCES squads(id) ON DELETE CASCADE,
            name        TEXT NOT NULL,
            kind        TEXT NOT NULL DEFAULT 'team',
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_squads_org ON squads (org_id)")

    # Членство людини в squad + посада.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS squad_members (
            squad_id    UUID NOT NULL REFERENCES squads(id) ON DELETE CASCADE,
            user_id     TEXT NOT NULL,
            title       TEXT,
            seniority   TEXT,
            PRIMARY KEY (squad_id, user_id)
        )
        """
    )

    # Типізовані ребра графа зв'язків (directed, org-scoped).
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS relationships (
            id          BIGSERIAL PRIMARY KEY,
            org_id      TEXT NOT NULL,
            src_user_id TEXT NOT NULL,
            dst_user_id TEXT NOT NULL,
            kind        TEXT NOT NULL,
            weight      REAL NOT NULL DEFAULT 1.0,
            source      TEXT NOT NULL DEFAULT 'declared',
            meta        JSONB NOT NULL DEFAULT '{}'::jsonb,
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (org_id, src_user_id, dst_user_id, kind)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_rel_org_src ON relationships (org_id, src_user_id, kind)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_rel_org_dst ON relationships (org_id, dst_user_id, kind)")

    # Делегат (AI-асистент особи) — персона + делеговані scopes.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS delegates (
            id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id        TEXT NOT NULL,
            principal_id  TEXT NOT NULL,
            persona       JSONB NOT NULL DEFAULT '{}'::jsonb,
            scopes        TEXT[] NOT NULL DEFAULT ARRAY['read:self'],
            proactive     BOOLEAN NOT NULL DEFAULT false,
            bot_token_enc TEXT,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (org_id, principal_id)
        )
        """
    )

    # Прив'язані Telegram-групи (канали спостереження) + рівень згоди.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS tg_groups (
            chat_id      BIGINT PRIMARY KEY,
            org_id       TEXT NOT NULL,
            squad_id     UUID REFERENCES squads(id) ON DELETE SET NULL,
            title        TEXT,
            ingest       TEXT NOT NULL DEFAULT 'off',
            consented_by TEXT,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )

    # Спостережене членство в групі (tg_id → user) — ідентифікація через Telegram id.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS tg_group_members (
            chat_id     BIGINT NOT NULL REFERENCES tg_groups(chat_id) ON DELETE CASCADE,
            telegram_id BIGINT NOT NULL,
            user_id     TEXT,
            last_seen   TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (chat_id, telegram_id)
        )
        """
    )

    # Командна видимість паспортів (TEAM_ECOSYSTEM §4.1). Дефолти зберігають
    # owner-scoped поведінку — наявні рядки лишаються private.
    op.execute("ALTER TABLE context_events ADD COLUMN IF NOT EXISTS subjects TEXT[] NOT NULL DEFAULT '{}'")
    op.execute("ALTER TABLE context_events ADD COLUMN IF NOT EXISTS visibility TEXT NOT NULL DEFAULT 'private'")
    op.execute("ALTER TABLE context_events ADD COLUMN IF NOT EXISTS audience TEXT[] NOT NULL DEFAULT '{}'")
    op.execute("ALTER TABLE context_events ADD COLUMN IF NOT EXISTS group_ref BIGINT")
    # Швидкий фільтр спільної пам'яті: (org, visibility) + суб'єкти (GIN).
    op.execute("CREATE INDEX IF NOT EXISTS idx_context_events_vis ON context_events (org_id, visibility)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_context_events_subjects ON context_events USING gin (subjects)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_context_events_subjects")
    op.execute("DROP INDEX IF EXISTS idx_context_events_vis")
    op.execute("ALTER TABLE context_events DROP COLUMN IF EXISTS group_ref")
    op.execute("ALTER TABLE context_events DROP COLUMN IF EXISTS audience")
    op.execute("ALTER TABLE context_events DROP COLUMN IF EXISTS visibility")
    op.execute("ALTER TABLE context_events DROP COLUMN IF EXISTS subjects")
    op.execute("DROP TABLE IF EXISTS tg_group_members")
    op.execute("DROP TABLE IF EXISTS tg_groups")
    op.execute("DROP TABLE IF EXISTS delegates")
    op.execute("DROP TABLE IF EXISTS relationships")
    op.execute("DROP TABLE IF EXISTS squad_members")
    op.execute("DROP TABLE IF EXISTS squads")
