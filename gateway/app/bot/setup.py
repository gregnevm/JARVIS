"""Реєстрація BotFather-метаданих при старті gateway."""
from __future__ import annotations

import logging

from ..config import settings
from ..telegram import TelegramClient

logger = logging.getLogger("jarvis.gateway.bot")

# Команди, що обробляються поза реєстром `commands.registry` (делеговані модулі
# access.py / admin.py) — додаємо їх у BotFather-меню вручну.
_DELEGATED_MENU: list[dict[str, str]] = [
    {"command": "admin", "description": "Admin panel (Mini App + керування)"},
    {"command": "pending", "description": "Черга доступу (адмін)"},
    {"command": "allow", "description": "Погодити доступ (адмін)"},
]


def bot_commands() -> list[dict[str, str]]:
    """BotFather-меню = `menu=True` команди з реєстру + делеговані admin/access.

    Єдине джерело правди — `commands.registry`: список не розходиться з реальними
    хендлерами (раніше BOT_COMMANDS дублював `COMMANDS` і вони дрейфували)."""
    from .commands import registry

    return [*registry.menu_commands(), *_DELEGATED_MENU]

BOT_DESCRIPTION = (
    "JARVIS — локальний AI-асистент з памʼяттю, інструментами, Twin/LoRA та Computer Use. "
    "Текст, голос, файли, inline @bot, Mini App дашборд."
)

BOT_SHORT_DESCRIPTION = "Локальний AI-асистент: чат, агент, нагадування, Computer Use."


async def register_bot_ui(tg: TelegramClient) -> None:
    await tg.set_my_commands(bot_commands())
    await tg.set_my_description(BOT_DESCRIPTION)
    await tg.set_my_short_description(BOT_SHORT_DESCRIPTION)
    url = settings.mini_app_https_url
    if url:
        await tg.set_chat_menu_button(url, "📊 Dashboard")
        logger.info("Mini App menu button → %s", url)
