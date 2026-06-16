"""Конфігурація Gateway. Читається з оточення (.env у dev, env_file у Compose)."""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    # Telegram
    telegram_bot_token: str = ""
    allowed_user_ids: str = ""
    # Файл погоджених через бота (/allow). Монтується з ./data у Docker.
    access_store_path: str = "/data/access/users.json"
    # Адміни: /admin, /allow та небезпечні дії. Порожньо = усі з whitelist (.env + бот).
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
    memory_url: str = "http://memory:8100"
    twin_url: str = "http://twin:8765"
    whisper_url: str = "http://whisper:9000"
    whisper_language: str = ""  # порожньо = автовизначення мови
    tts_url: str = "http://tts:8300"
    # Постійна Reply Keyboard під полем вводу (швидкі кнопки: Статус, Бриф, …).
    telegram_reply_keyboard: bool = True
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
    # Жорсткіший ліміт для не-адмінів (погоджені друзі). 0 = той самий, що RATE_LIMIT_PER_MIN.
    guest_rate_limit_per_min: int = 12
    upload_dir: str = "/data/uploads"

    # --- Telegram Mini App (веб-дашборд) ---
    # Публічний HTTPS-URL, за яким Telegram-клієнт відкриває Mini App (вимога Telegram —
    # лише https). Напр. named cloudflare tunnel: https://jarvis.example.com/app
    # Порожньо = кнопку-меню не реєструємо (апп лишається доступним у браузері на :8000/app).
    public_app_url: str = ""
    # HTTPS Mini App адмін-панелі (/admin). Порожньо → з PUBLIC_APP_URL (/app → /admin).
    public_admin_app_url: str = ""
    # Локальний URL gateway для підказок /app у браузері (без тунелю).
    gateway_browser_url: str = "http://127.0.0.1:8000"
    # Дозволити відкривати /app та /app/* без Telegram initData (для локального
    # перегляду в браузері). У проді (named tunnel) лиши False — пускає лише з Telegram.
    webapp_dev_open: bool = True

    @property
    def mini_app_https_url(self) -> str:
        """PUBLIC_APP_URL → завжди https://…/app (суфікс /app додається автоматично)."""
        from .webapp_urls import normalize_mini_app_url

        return normalize_mini_app_url(self.public_app_url)

    @property
    def local_app_url(self) -> str:
        from .webapp_urls import local_app_url

        return local_app_url(self.gateway_browser_url)

    # Веб-панель адміна на /admin (HTTP Basic Auth). Порожній пароль = панель вимкнена.
    admin_panel_user: str = "admin"
    admin_panel_password: str = ""
    # Веб-консоль /platform (HTTP Basic Auth у браузері). Порожньо → fallback на
    # ADMIN_PANEL_PASSWORD. Telegram-адміни заходять через initData без пароля.
    platform_password: str = ""
    # Спільний з tools каталог даних (Docker: ./data:/data). Звідки Platform читає
    # session-логи (logs/sessions/*.jsonl) і профілі (profiles/*.json).
    data_dir: str = "/data"
    # Публічний URL для webhook (лише TELEGRAM_INGEST_MODE=webhook).
    telegram_webhook_url: str = ""
    # Telegram ID з доступом до Computer Use. Порожньо → ADMIN_USER_IDS → ALLOWED_USER_IDS (.env).
    # Друзі з /allow сюди НЕ потрапляють — лише явний whitelist.
    computer_owner_user_ids: str = ""
    computer_session_trust_minutes: int = 10
    # Режим computer лише для ADMIN_USER_IDS (застарілий прапор; краще COMPUTER_OWNER_USER_IDS).
    computer_mode_admins_only: bool = False
    # Інтервал поллера нагадувань (секунди).
    reminder_poll_seconds: float = 20.0
    # Ігнорувати edited_message (не перезапускати агента).
    ignore_edited_messages: bool = True
    # Proactive health alerts (host-agent, Ollama, Docker). 0 = вимкнено.
    health_watch_interval: float = 300.0
    health_alert_user_ids: str = ""
    # Drop Zone: дефолтний каталог на хості для файлів з Telegram (caption «на диск»).
    hostagent_drop_dir: str = ""
    # Макс. розмір файлу для /file pull (байти, Telegram cap ~50MB).
    remote_file_max_bytes: int = 48 * 1024 * 1024

    # P11 OpenAI-compatible API (opt-in)
    enable_openai_api: bool = False
    openai_api_key: str = ""
    openai_default_user_id: int = 0
    # AP-4: per-key rate limit (запитів/хв на керований ключ). 0 = без обмеження.
    openai_key_rate_limit_per_min: int = 0

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
    def health_alert_ids(self) -> set[int]:
        raw = self.health_alert_user_ids.strip()
        if not raw:
            return set()
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
