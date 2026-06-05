"""Реєстрація BotFather-метаданих при старті gateway."""
from __future__ import annotations

import logging

from ..config import settings
from ..telegram import TelegramClient

logger = logging.getLogger("jarvis.gateway.bot")

BOT_COMMANDS: list[dict[str, str]] = [
    {"command": "start", "description": "Головне меню"},
    {"command": "dashboard", "description": "Панель + inline-кнопки"},
    {"command": "app", "description": "Mini App дашборд (HTTPS)"},
    {"command": "status", "description": "Стан Ollama / Twin"},
    {"command": "brief", "description": "Короткий бриф"},
    {"command": "mode", "description": "Режим chat/agent/hybrid/computer"},
    {"command": "reminders", "description": "Активні нагадування"},
    {"command": "project", "description": "Проєкти: list / new / switch / off"},
    {"command": "sync", "description": "Twin ingest + LoRA"},
    {"command": "help", "description": "Довідка"},
    {"command": "keyboard", "description": "Показати або сховати кнопки"},
    {"command": "admin", "description": "Admin panel (Mini App + керування)"},
    {"command": "pending", "description": "Черга доступу (адмін)"},
    {"command": "allow", "description": "Погодити доступ (адмін)"},
]

BOT_DESCRIPTION = (
    "JARVIS — локальний AI-асистент з памʼяттю, інструментами, Twin/LoRA та Computer Use. "
    "Текст, голос, файли, inline @bot, Mini App дашборд."
)

BOT_SHORT_DESCRIPTION = "Локальний AI-асистент: чат, агент, нагадування, Computer Use."


async def register_bot_ui(tg: TelegramClient) -> None:
    await tg.set_my_commands(BOT_COMMANDS)
    await tg.set_my_description(BOT_DESCRIPTION)
    await tg.set_my_short_description(BOT_SHORT_DESCRIPTION)
    url = settings.mini_app_https_url
    if url:
        await tg.set_chat_menu_button(url, "📊 Dashboard")
        logger.info("Mini App menu button → %s", url)
