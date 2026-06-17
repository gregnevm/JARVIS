"""Конфігурація Gateway. Читається з оточення (.env у dev, env_file у Compose)."""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict

from jarvis_core.auth_ids import parse_comma_separated_ids


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
    # перегляду в браузері). Дефолт False — безпечно (AGENTS §5): пускає лише з
    # Telegram. У dev-open запит без initData = uid 0 («анонімний viewer»): GET
    # працює, але мутуючі дії (mode/trust/macro) відхиляються (_require_identified).
    webapp_dev_open: bool = False

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
    # --- Client-API / JWT (CL-1, Стовп C) — усе за прапором (S2: self-hosted не ламається) ---
    # JWT для клієнтів (mobile APK / SPA), що не мають Telegram initData. Порожньо =
    # JWT-логін вимкнено; лишаються initData/Basic. Self-hosted: один admin логіниться
    # PLATFORM_PASSWORD → JWT (synthetic org, owner/studio). Multi-user signup → SAAS PR#6.
    jwt_secret: str = ""
    jwt_access_ttl: int = 3600  # сек — час життя access-токена (1 год)
    jwt_refresh_ttl: int = 604800  # сек — refresh-токен (7 днів)
    # Synthetic org для self-hosted (дзеркало jarvis_core.context.DEFAULT_ORG_ID).
    default_org_id: str = "00000000-0000-0000-0000-000000000001"
    # Мультитенант-режим (cloud). false = self-hosted, один synthetic org.
    saas_mode: bool = False
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

    # --- Mobile APK (Стовп C, CL-3) ---
    # Шлях до зібраного MVP APK. Порожньо → {DATA_DIR}/artifacts/jarvis-mvp.apk
    # (./data:/data змонтовано в gateway). Команда /apk віддає цей файл у Telegram.
    apk_artifact_path: str = ""
    # Версія для підпису/caption APK (синхронізована з mobile/app/version).
    apk_version: str = "0.1.0"
    # Авто-доставка APK у Telegram через бот (БЕЗ GitHub-секретів): gateway періодично
    # перевіряє публічний apk-latest реліз і, якщо там новіша версія за локальну,
    # качає її в data/artifacts і DM-ить адмінам (notify_admins_apk_ready). Опт-ін —
    # використовує TELEGRAM_BOT_TOKEN з .env, що вже є в gateway.
    apk_auto_deliver: bool = False
    apk_auto_deliver_interval: int = 3600  # сек між перевірками (1 год)
    # Публічні URL артефактів rolling-релізу (CI публікує тег apk-latest).
    apk_release_apk_url: str = (
        "https://github.com/gregnevm/JARVIS/releases/download/apk-latest/jarvis-mvp.apk"
    )
    apk_release_meta_url: str = (
        "https://github.com/gregnevm/JARVIS/releases/download/apk-latest/jarvis-mvp.apk.meta.json"
    )

    # P11 OpenAI-compatible API (opt-in)
    enable_openai_api: bool = False
    openai_api_key: str = ""
    openai_default_user_id: int = 0

    # Context ingest API (Стовп C / CL-3) — збір контексту з паспортами (P9/P10).
    # Вхід для APK/скриптів/платформи → memory /context/*. За прапором (S2): дефолт off.
    enable_context_api: bool = False
    # Стеля подій в одному батчі /api/v1/ingest/events (анти-зловживання).
    context_ingest_max_batch: int = 500

    # Claude-міст для coding (dispatch -> remote code via Claude). Cloud, явний opt-in (S1).
    enable_claude_code_bridge: bool = False

    # In-app scheduler context-jobs (опційна автоматизація). Дефолт off (ADR-008:
    # запуск із нагляду) — вмикати свідомо, або юзати зовн. cron на /api/v1/context/jobs/*.
    context_scheduler_enabled: bool = False
    # Кого обслуговувати (CSV Telegram id). Порожньо → ADMIN_USER_IDS.
    context_scheduler_user_ids: str = ""
    # Година (UTC) щоденного прогону daily+retention; між ними — summarize кожні interval.
    context_daily_hour: int = 6
    context_scheduler_interval: float = 1800.0  # сек між тіками (summarize + перевірка daily)

    # Стовп D (TEAM_ECOSYSTEM): обробка Telegram-груп (presence/ambient). Дефолт off —
    # self-hosted solo-user не зачіпає (S2); вмикати свідомо для командного режиму.
    team_mode: bool = False
    # @username бота (без @) — для детекції адресації у групах (mention/reply).
    bot_username: str = ""

    @property
    def allowed_ids(self) -> set[int]:
        """ALLOWED_USER_IDS ('1,2,3') → set[int]. Порожньо = нікого не пускаємо."""
        return parse_comma_separated_ids(self.allowed_user_ids)

    @property
    def health_alert_ids(self) -> set[int]:
        return parse_comma_separated_ids(self.health_alert_user_ids)

    @property
    def admin_ids(self) -> set[int]:
        """ADMIN_USER_IDS. Порожньо → адміни = ALLOWED_USER_IDS."""
        if not self.admin_user_ids.strip():
            return self.allowed_ids
        return parse_comma_separated_ids(self.admin_user_ids)

    @property
    def context_scheduler_ids(self) -> set[int]:
        """CONTEXT_SCHEDULER_USER_IDS. Порожньо → ADMIN_USER_IDS (self-hosted власник)."""
        raw = self.context_scheduler_user_ids.strip()
        if not raw:
            return self.admin_ids
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
