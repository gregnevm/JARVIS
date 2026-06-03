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

    @property
    def dsn(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


settings = Settings()
