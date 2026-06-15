"""Конфігурація Memory service."""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    ollama_host: str = "http://host.docker.internal:11434"
    embed_model: str = "nomic-embed-text"
    embed_dim: int = 768

    postgres_user: str = "jarvis"
    postgres_password: str = "changeme"
    postgres_db: str = "jarvis"
    postgres_host: str = "postgres"
    postgres_port: int = 5432

    short_term_limit: int = 10

    # Redis — кеш ембедингів (необов'язковий; fail-open якщо недоступний).
    redis_url: str = "redis://redis:6379/0"
    embed_cache_ttl: int = 86400  # 24 год

    # Ліміти контексту project files для агента (GET ?include_content=true).
    # CA-2.5: токен-бюджет (≈4 симв/токен) замість char-ліміту — передбачувано
    # під вікно контексту. ~3000 токенів сукупно, ~1200 на файл.
    project_files_max_total_tokens: int = 3000
    project_files_max_per_file_tokens: int = 1200
    # CA-2.4: індексувати project-файли у scoped RAG (embed чанків при add/reindex).
    index_project_files: bool = True

    @property
    def dsn(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def sync_dsn(self) -> str:
        """Sync DSN для Alembic (psycopg2)."""
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


settings = Settings()
