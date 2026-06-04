"""Конфігурація Gateway. Читається з оточення (.env у dev, env_file у Compose)."""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    # Telegram
    telegram_bot_token: str = ""
    allowed_user_ids: str = ""
    # Адміни: /admin та небезпечні дії лише з підтвердженням. Порожньо = усі з whitelist.
    admin_user_ids: str = ""
    telegram_api_base: str = "https://api.telegram.org"
    # Спосіб отримання апдейтів:
    #   polling — gateway сам опитує Telegram (getUpdates). Нуль інфраструктури,
    #             переживає рестарти, не треба публічний URL/тунель. Дефолт.
    #   webhook — Telegram шле POST /webhook (потрібен стабільний публічний HTTPS,
    #             напр. named tunnel / домен). Вмикати лише в проді з фіксованим URL.
    telegram_ingest_mode: str = "polling"
    # Секрет вебхука (лише для webhook-режиму): Telegram шле його у заголовку
    # X-Telegram-Bot-Api-Secret-Token. Порожньо = перевірка вимкнена.
    telegram_webhook_secret: str = ""

    # Tools — агент-луп (DESIGN: без n8n-проксі)
    tools_url: str = "http://tools:8200"
    twin_url: str = "http://twin:8765"
    whisper_url: str = "http://whisper:9000"
    whisper_language: str = ""  # порожньо = автовизначення мови
    tts_url: str = "http://tts:8300"
    # Голосова відповідь (TTS) на голосові повідомлення. Вимкнено за замовчуванням.
    enable_voice_reply: bool = False
    # Реагувати на реакції користувача (emoji) до повідомлень бота короткою відповіддю.
    enable_reaction_replies: bool = True
    # Скільки секунд збирати альбом (media_group), перш ніж обробити його як один запит.
    album_collect_seconds: float = 2.0
    # Стрім відповіді в Telegram (editMessageText «друкує» текст наживо). Вимкнеш —
    # бот шле одне фінальне повідомлення (старий шлях). Фолбек на класику авто.
    enable_streaming: bool = True
    redis_url: str = "redis://redis:6379/0"
    # Агент-луп на CPU повільний (кілька викликів Ollama) — тримаємо запас.
    agent_timeout: float = 300.0

    # Ліміти / шляхи
    rate_limit_per_min: int = 20
    upload_dir: str = "/data/uploads"

    # --- Telegram Mini App (веб-дашборд) ---
    # Публічний HTTPS-URL, за яким Telegram-клієнт відкриває Mini App (вимога Telegram —
    # лише https). Напр. named cloudflare tunnel: https://jarvis.example.com/app
    # Порожньо = кнопку-меню не реєструємо (апп лишається доступним у браузері на :8000/app).
    public_app_url: str = ""
    # Дозволити відкривати /app та /app/* без Telegram initData (для локального
    # перегляду в браузері). У проді (named tunnel) лиши False — пускає лише з Telegram.
    webapp_dev_open: bool = True

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

    @property
    def admin_ids(self) -> set[int]:
        """ADMIN_USER_IDS. Порожньо → адміни = ALLOWED_USER_IDS."""
        raw = self.admin_user_ids.strip()
        if not raw:
            return self.allowed_ids
        ids: set[int] = set()
        for part in raw.split(","):
            part = part.strip()
            if not part:
                continue
            try:
                ids.add(int(part))
            except ValueError:
                continue
        return ids


settings = Settings()
