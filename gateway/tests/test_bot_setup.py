import asyncio

import httpx

from app.bot.setup import BOT_COMMANDS, register_bot_ui
from app.telegram import TelegramClient


def test_bot_commands_include_brief_and_keyboard():
    names = {c["command"] for c in BOT_COMMANDS}
    assert "brief" in names
    assert "keyboard" in names
    assert "reminders" in names


def test_register_bot_ui_calls_telegram():
    seen: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req.url.path.rsplit("/", 1)[-1])
        return httpx.Response(200, json={"ok": True, "result": True})

    async def _run() -> None:
        tg = TelegramClient("TOKEN")
        tg._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        try:
            await register_bot_ui(tg)
        finally:
            await tg.aclose()

    asyncio.run(_run())
    assert "setMyCommands" in seen
    assert "setMyDescription" in seen
    assert "setMyShortDescription" in seen
