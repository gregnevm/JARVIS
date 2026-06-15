"""Конфігурація TTS service (Coqui XTTS v2 → OGG/Opus)."""
from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    model_name: str = Field(
        default="tts_models/multilingual/multi-dataset/xtts_v2",
        validation_alias="TTS_MODEL",
    )
    speaker_wav: str = Field(default="/app/voices/reference.wav", validation_alias="TTS_SPEAKER_WAV")
    # XTTS v2 не має офіційного uk; клонований uk reference + ru дає найкращу славянську фонетику.
    language: str = Field(default="ru", validation_alias="TTS_LANGUAGE")
    device: str = Field(default="cuda", validation_alias="TTS_DEVICE")  # cuda | cpu | auto
    max_chars: int = Field(default=800, validation_alias="TTS_MAX_CHARS")
    synth_timeout: float = Field(default=120.0, validation_alias="TTS_SYNTH_TIMEOUT")


settings = Settings()
