"""Конфігурація Twin SyncServer."""
from __future__ import annotations

from typing import Literal

import httpx
from pydantic_settings import BaseSettings, SettingsConfigDict

from jarvis_core.llm import LLMInterface, build_llm_stack


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    data_dir: str = "/data/twin"
    registry_db: str = "/data/twin/registry.db"

    llm_backend: Literal["ollama", "kobold"] = "ollama"
    ollama_host: str = "http://host.docker.internal:11434"
    ollama_model: str = "qwen2.5:7b-instruct"
    kobold_host: str = "http://127.0.0.1:5001"
    llm_timeout: float = 180.0
    llm_log_path: str | None = None
    # Мінімальний eval_score для promote (0 = не перевіряти).
    min_eval_promote: float = 0.0


def create_llm(cfg: Settings, client: httpx.Client | None = None) -> LLMInterface:
    log = cfg.llm_log_path or f"{cfg.data_dir.rstrip('/')}/logs/llm.jsonl"
    return build_llm_stack(
        backend=cfg.llm_backend,
        ollama_host=cfg.ollama_host,
        ollama_model=cfg.ollama_model,
        kobold_host=cfg.kobold_host,
        timeout=cfg.llm_timeout,
        log_path=log,
        client=client,
    )


settings = Settings()
