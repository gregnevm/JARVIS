"""Конфігурація Gateway. Читається з оточення (.env у dev, env_file у Compose)."""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    # Telegram
    telegram_bot_token: str = ""
    allowed_user_ids: str = ""
    telegram_api_base: str = "https://api.telegram.org"

    # Внутрішні сервіси
    n8n_webhook_url: str = "http://n8n:5678/webhook/agent"
    whisper_url: str = "http://whisper:9000"
    whisper_language: str = ""  # порожньо = автовизначення мови
    redis_url: str = "redis://redis:6379/0"
    # Агент-луп на CPU повільний (кілька викликів Ollama) — тримаємо запас.
    orchestrator_timeout: float = 300.0

    # Ліміти / шляхи
    rate_limit_per_min: int = 20
    upload_dir: str = "/data/uploads"

    @property
    def allowed_ids(self) -> set[int]:
        """ALLOWED_USER_IDS ('1,2,3') → set[int]. Порожньо = нікого не пускаємо."""
        ids: set[int] = set()
        for part in self.allowed_user_ids.split(","):
            part = part.strip()
            if not part:
                continue
            try:
                ids.add(int(part))
            except ValueError:
                continue
        return ids


settings = Settings()
