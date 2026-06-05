"""Конфігурація Tools service (інструменти + агент-луп)."""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    # Ollama (на ХОСТІ) + дві моделі
    ollama_host: str = "http://host.docker.internal:11434"
    ollama_model_chat: str = "qwen3:4b"
    ollama_model_agent: str = "qwen2.5:7b-instruct"
    # Vision-модель для розпізнавання зображень (напр. "llava:7b", "qwen2.5vl:7b").
    # Порожньо = describe_image вимкнено.
    ollama_model_vision: str = ""
    # C6.1: перед describe_image/see_screen вивантажити chat+agent з VRAM; vision keep_alive=0.
    ollama_vision_on_demand: bool = False

    # Генерація зображень (опційно):
    #   pollinations — IMAGE_GEN_URL=pollinations (хмара, без ключа; Windows OK)
    #   ollama — IMAGE_GEN_URL=ollama + IMAGE_GEN_MODEL (лише macOS поки що)
    #   Forge/A1111 — http://host.docker.internal:7860
    #   OpenAI-сумісний — http://.../v1 + IMAGE_GEN_MODEL
    # Порожній URL і модель = generate_image вимкнено.
    image_gen_url: str = ""
    image_gen_model: str = ""  # модель Ollama-image / dall-e-3 тощо
    image_gen_timeout: float = 180.0
    # Stable Horde (IMAGE_GEN_URL=horde). Анонім: 0000000000; краще ключ з aihorde.net
    horde_api_key: str = "0000000000"
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
    # Telegram ID з доступом до Computer Use (скріншот, PS, FS). Порожньо → ADMIN → ALLOWED (.env).
    computer_owner_user_ids: str = ""
    allowed_user_ids: str = ""
    admin_user_ids: str = ""
    # Computer Use — керування Windows-хостом через host-agent (поза Docker).
    enable_computer_use: bool = False
    computer_allow_admin: bool = False
    hostagent_url: str = "http://host.docker.internal:8400"
    hostagent_token: str = ""
    ps_whitelist: str = ""
    cli_whitelist: str = ""
    computer_timeout: float = 30.0
    computer_require_confirm: bool = True
    # Після ✅ додати cmdlet/exe у data/computer_learned.json; повтор — без підтвердження.
    computer_auto_learn_whitelist: bool = True
    computer_auto_trust_learned: bool = True
    enable_browser: bool = False
    # Мутуючі computer-дії на user_id за годину; 0 = без ліміту.
    computer_rate_limit_per_hour: int = 120
    computer_auto_vision: bool = True
    computer_allow_power: bool = False
    hostagent_drop_dir: str = ""
    remote_file_max_bytes: int = 48 * 1024 * 1024
    http_timeout: float = 20.0          # web_fetch / web_search
    ollama_timeout: float = 180.0       # CPU-інференс може бути повільним
    max_agent_iters: int = 5            # стеля ітерацій тул-лупа
    computer_max_iters: int = 8         # окремо для AGENT_MODE=computer (багатокрокові задачі)
    fetch_max_chars: int = 6000         # обрізаємо сторінку, щоб не рознести контекст
    code_exec_timeout: float = 8.0
    # Circuit breaker Ollama: N підряд помилок → пауза cooldown секунд (fail-fast).
    ollama_fail_threshold: int = 3
    ollama_cooldown: float = 60.0
    # D.4: retrain коли +N кураційних turns після останнього export (0 = вимкнено).
    train_retrain_min_curated: int = 200


settings = Settings()
