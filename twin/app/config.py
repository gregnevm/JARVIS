"""Конфігурація Twin SyncServer."""
from __future__ import annotations

from typing import Literal

import httpx
from pydantic import Field
from pydantic_settings import SettingsConfigDict

from jarvis_core.llm import LLMInterface, build_llm_stack
from jarvis_core.settings import OllamaCfg


class Settings(OllamaCfg):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    # Twin-специфічні шляхи читаємо під TWIN_-префіксом (validation_alias), щоб не
    # колізувати зі спільним generic `DATA_DIR` інших сервісів і щоб ключі у
    # .env.example (TWIN_DATA_DIR/...) були ЖИВІ. Спільні поля (OLLAMA_HOST тощо)
    # лишаємо без префіксу — їх twin читає з тих самих env, що й решта.
    data_dir: str = Field(default="/data/twin", validation_alias="TWIN_DATA_DIR")
    registry_db: str = Field(
        default="/data/twin/registry.db", validation_alias="TWIN_REGISTRY_DB"
    )

    # ollama_host — спільний блок OllamaCfg (ті самі env, що й tools/memory).
    llm_backend: Literal["ollama", "kobold"] = "ollama"
    ollama_model: str = "qwen2.5:7b-instruct"
    kobold_host: str = "http://127.0.0.1:5001"
    llm_timeout: float = 180.0
    llm_log_path: str | None = None
    # Мінімальний eval_score для promote (0 = не перевіряти).
    min_eval_promote: float = Field(default=0.0, validation_alias="TWIN_MIN_EVAL_PROMOTE")


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
