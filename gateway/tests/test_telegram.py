"""split_message — розбивка довгих повідомлень Telegram (ліміт 4096) + API-методи."""
import asyncio

import httpx
from app.telegram import TELEGRAM_MAX_LEN, TelegramClient, split_message


def test_short_text_single_chunk():
    assert split_message("привіт") == ["привіт"]


def test_empty_text():
    assert split_message("") == [""]


def test_splits_on_line_boundaries():
    line = "x" * 1000 + "\n"
    text = line * 5
    chunks = split_message(text, limit=1500)
    assert all(len(c) <= 1500 for c in chunks)
    assert "".join(chunks) == text  # нічого не загубили


def test_hard_split_of_overlong_line():
    text = "y" * 5000  # один рядок, довший за ліміт → ріжемо жорстко
    chunks = split_message(text, limit=2000)
    assert all(len(c) <= 2000 for c in chunks)
    assert "".join(chunks) == text
    assert len(chunks) == 3


def test_default_limit_constant():
    assert TELEGRAM_MAX_LEN == 4096


def _tg_with(handler):
    tg = TelegramClient("TOKEN")
    tg._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return tg


def test_send_message_id_returns_message_id():
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path.endswith("/sendMessage")
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 77}})

    async def _run() -> int | None:
        tg = _tg_with(handler)
        try:
            return await tg.send_message_id(5, "hi")
        finally:
            await tg.aclose()

    assert asyncio.run(_run()) == 77


def test_edit_message_text_hits_endpoint():
    seen: dict[str, str] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["path"] = req.url.path
        return httpx.Response(200, json={"ok": True, "result": {}})

    async def _run() -> None:
        tg = _tg_with(handler)
        try:
            await tg.edit_message_text(5, 77, "новий текст")
        finally:
            await tg.aclose()

    asyncio.run(_run())
    assert seen["path"].endswith("/editMessageText")
