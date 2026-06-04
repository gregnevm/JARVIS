"""Конфігурація Tools service (інструменти + агент-луп)."""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    # Ollama (на ХОСТІ) + дві моделі
    ollama_host: str = "http://host.docker.internal:11434"
    ollama_model_chat: str = "qwen3:4b"
    ollama_model_agent: str = "qwen2.5:7b-instruct"
    # Режим: hybrid (евристика) | chat (завжди CHAT без тулів) | agent (завжди тул-луп)
    agent_mode: str = "hybrid"

    # Сусідні сервіси
    memory_url: str = "http://memory:8100"
    twin_url: str = "http://twin:8765"
    # Redis — спільний із gateway: tool set_reminder пише у ZSET, gateway-поллер шле.
    redis_url: str = "redis://redis:6379/0"

    # Шлях до даних (персональні нотатки тощо) — том ./data:/data у compose.
    data_dir: str = "/data"

    # Безпека / ліміти
    enable_code_exec: bool = False
    http_timeout: float = 20.0          # web_fetch / web_search
    ollama_timeout: float = 180.0       # CPU-інференс може бути повільним
    max_agent_iters: int = 5            # стеля ітерацій тул-лупа
    fetch_max_chars: int = 6000         # обрізаємо сторінку, щоб не рознести контекст
    code_exec_timeout: float = 8.0
    # Circuit breaker Ollama: N підряд помилок → пауза cooldown секунд (fail-fast).
    ollama_fail_threshold: int = 3
    ollama_cooldown: float = 60.0


settings = Settings()
