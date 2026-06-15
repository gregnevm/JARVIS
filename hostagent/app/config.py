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
    # Окремий, більший ліміт для code_edit (CA-1.x): 6 KB замало навіть для одного
    # модуля. Читання/запис правки використовують цей ліміт, не max_bytes.
    edit_max_bytes: int = 2 * 1024 * 1024
    # Стеля файлів у транзакційному /fs/edit_batch (CA-4.3) — захист від мега-батчів.
    edit_batch_max_files: int = 30
    max_download_bytes: int = 48 * 1024 * 1024
    # Comma-separated absolute paths; FS API only allows paths under these roots.
    fs_roots: str = ""
    allow_power: bool = False
    drop_dir: str = ""


settings = Settings()
