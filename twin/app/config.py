"""Конфігурація Twin SyncServer."""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    data_dir: str = "/data/twin"                  # ingest-логи з Edge, тощо
    registry_db: str = "/data/twin/registry.db"   # SQLite ModelRegistry


settings = Settings()
