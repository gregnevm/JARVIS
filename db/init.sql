-- ============================================================
--  JARVIS — ініціалізація схеми БД (PostgreSQL + pgvector)
--  Виконується автоматично при ПЕРШОМУ старті контейнера postgres
--  (монтується у /docker-entrypoint-initdb.d/).
--  Щоб перезапустити з нуля: docker compose down -v && docker compose up
-- ============================================================

CREATE EXTENSION IF NOT EXISTS vector;

-- ------------------------------------------------------------
-- Сесії діалогів
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sessions (
    id          BIGSERIAL PRIMARY KEY,
    user_id     BIGINT      NOT NULL,
    title       TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions (user_id);

-- ------------------------------------------------------------
-- Повідомлення (історія діалогу — short-term + джерело для RAG)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS messages (
    id          BIGSERIAL PRIMARY KEY,
    session_id  BIGINT      NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    user_id     BIGINT      NOT NULL,
    role        TEXT        NOT NULL CHECK (role IN ('system','user','assistant','tool')),
    content     TEXT        NOT NULL,
    meta        JSONB       NOT NULL DEFAULT '{}'::jsonb,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_messages_session ON messages (session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_messages_user    ON messages (user_id, created_at);

-- ------------------------------------------------------------
-- Ембединги (довготривала RAG-пам'ять)
--
--  УВАГА: vector(768) розрахований під nomic-embed-text (768 вимірів).
--  Якщо зміниш EMBED_MODEL на модель з іншою розмірністю — зміни число
--  тут і перестворі таблицю. Це міграція, а не рантайм-конфіг:
--  pgvector впаде на upsert при невідповідності розмірності.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS embeddings (
    id          BIGSERIAL    PRIMARY KEY,
    message_id  BIGINT       REFERENCES messages(id) ON DELETE CASCADE,
    user_id     BIGINT       NOT NULL,
    content     TEXT         NOT NULL,
    embedding   vector(768)  NOT NULL,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- HNSW-індекс для cosine similarity (не потребує тренування, на відміну від ivfflat).
CREATE INDEX IF NOT EXISTS idx_embeddings_vector
    ON embeddings USING hnsw (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS idx_embeddings_user ON embeddings (user_id);

-- ------------------------------------------------------------
-- Проєкти (P1) — ізольовані workspace (як Claude Projects / Cursor folders).
--  RAG скоупиться по project_id: chunks одного проєкту не течуть в інший.
--  NULL project_id = «загальний» контекст (поведінка як до P1, без регресії).
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS projects (
    id            BIGSERIAL    PRIMARY KEY,
    user_id       BIGINT       NOT NULL,
    name          TEXT         NOT NULL,
    system_prompt TEXT         NOT NULL DEFAULT '',
    archived      BOOLEAN      NOT NULL DEFAULT false,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_projects_user ON projects (user_id, archived);

CREATE TABLE IF NOT EXISTS project_files (
    id          BIGSERIAL    PRIMARY KEY,
    project_id  BIGINT       NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name        TEXT         NOT NULL,
    content     TEXT         NOT NULL,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_project_files_project ON project_files (project_id);

-- Scoped RAG: messages/embeddings можуть належати проєкту (NULL = загальний).
ALTER TABLE messages   ADD COLUMN IF NOT EXISTS project_id BIGINT REFERENCES projects(id) ON DELETE SET NULL;
ALTER TABLE embeddings ADD COLUMN IF NOT EXISTS project_id BIGINT REFERENCES projects(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_embeddings_user_project ON embeddings (user_id, project_id);
