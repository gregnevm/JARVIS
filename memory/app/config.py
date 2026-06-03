"""Конфігурація Memory service."""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    ollama_host: str = "http://host.docker.internal:11434"
    embed_model: str = "nomic-embed-text"

    postgres_user: str = "jarvis"
    postgres_password: str = "changeme"
    postgres_db: str = "jarvis"
    postgres_host: str = "postgres"
    postgres_port: int = 5432

    short_term_limit: int = 10

    # Redis — кеш ембедингів (необов'язковий; fail-open якщо недоступний).
    redis_url: str = "redis://redis:6379/0"
    embed_cache_ttl: int = 86400  # 24 год

    @property
    def dsn(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


settings = Settings()
