"""R4 «Тонкий шлюз» — композитні settings-блоки (P7 SSOT).

Спільні env-змінні, що читаються 2–3 сервісами, оголошені ОДИН раз тут; сервісні
`config.py` збирають потрібні блоки успадкуванням mixin-ів (pydantic-settings).
Env-імена й дефолти незмінні — сумісність `.env` 100% (фіксується по-сервісними
снапшот-тестами `test_config_snapshot.py`).

Сервіс з іншим дефолтом/alias-ом (напр. twin: `TWIN_DATA_DIR`) просто
перевизначає поле у себе — блок задає ім'я і канонічний дефолт.
"""
from __future__ import annotations

from pydantic_settings import BaseSettings


class RedisCfg(BaseSettings):
    """Спільна шина/кеш (gateway, tools, memory)."""

    redis_url: str = "redis://redis:6379/0"


class OllamaCfg(BaseSettings):
    """Хостовий inference (tools, memory, twin). S1: Ollama на хості, не в Docker."""

    ollama_host: str = "http://host.docker.internal:11434"


class CoreServiceUrls(BaseSettings):
    """Адреси внутрішніх сервісів, які читають і gateway, і tools."""

    memory_url: str = "http://memory:8100"
    twin_url: str = "http://twin:8765"


class DataDirCfg(BaseSettings):
    """Спільний том даних (Docker: ./data:/data) — gateway, tools."""

    data_dir: str = "/data"


class AuthIdsCfg(BaseSettings):
    """Whitelist/адміни Telegram — gateway і tools мають бачити ті самі значення."""

    allowed_user_ids: str = ""
    admin_user_ids: str = ""


class ComputerCfg(BaseSettings):
    """Computer Use: коло довірених, trust-вікно, drop-zone, ліміт файлів (gateway ↔ tools)."""

    # Telegram ID з доступом до Computer Use. Порожньо → ADMIN_USER_IDS → ALLOWED_USER_IDS.
    computer_owner_user_ids: str = ""
    computer_session_trust_minutes: int = 10
    # Застарілий прапор; краще COMPUTER_OWNER_USER_IDS.
    computer_mode_admins_only: bool = False
    # Drop Zone: дефолтний каталог на хості для файлів з Telegram.
    hostagent_drop_dir: str = ""
    # Макс. розмір файлу для /file pull (байти, Telegram cap ~50MB).
    remote_file_max_bytes: int = 48 * 1024 * 1024
