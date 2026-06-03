"""Конфігурація TTS service (piper → OGG/Opus)."""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    voice_path: str = "/app/voices/uk.onnx"   # .onnx.json мусить лежати поруч
    max_chars: int = 800                       # обрізаємо довгий текст (голосове не має бути 10хв)
    synth_timeout: float = 60.0                # таймаут piper-синтезу


settings = Settings()
