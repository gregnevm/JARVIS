"""Конфігурація host-agent (FastAPI на Windows-хості, поза Docker)."""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        case_sensitive=False,
        env_prefix="HOSTAGENT_",
    )

    token: str = ""
    allow_admin: bool = False
    bind_host: str = "127.0.0.1"
    port: int = 8400
    exec_timeout: float = 30.0
    max_bytes: int = 6000
    # Comma-separated absolute paths; FS API only allows paths under these roots.
    fs_roots: str = ""


settings = Settings()
