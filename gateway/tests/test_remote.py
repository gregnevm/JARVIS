"""Remote commands: /file, /macro, /tasks, /see."""
import asyncio
from unittest.mock import AsyncMock, patch

from app.bot.remote import handle_remote_command, is_remote_command


class FakeTG:
    def __init__(self) -> None:
        self.messages: list[tuple] = []
        self.documents: list[tuple] = []
        self.actions: list[tuple] = []

    async def send_message(self, chat_id, text, parse_mode=None, message_thread_id=None):
        self.messages.append((chat_id, text, parse_mode))

    async def send_document(self, chat_id, raw, filename=None):
        self.documents.append((chat_id, raw, filename))

    async def send_chat_action(self, chat_id, action):
        self.actions.append((chat_id, action))


class FakeTools:
    async def pull_file(self, user_id, path):
        return {"error": "not found"}

    async def list_macros(self):
        return {"macros": [{"name": "deploy", "description": "compose up"}]}

    async def run_macro(self, user_id, name):
        return f"ran {name}"

    async def list_tasks(self, user_id):
        return "no tasks"

    async def cancel_tasks(self, user_id):
        pass

    async def see_screen(self, user_id, q):
        return "screen ok"

    async def clipboard_read(self, user_id):
        return "clip text"


def _run(coro):
    return asyncio.run(coro)


def test_is_remote_command():
    assert is_remote_command("/macro list")
    assert is_remote_command("/file C:\\x")
    assert not is_remote_command("hello")


def test_remote_denied():
    tg = FakeTG()
    with patch("app.bot.remote.computer_denied_message", return_value="denied"):
        ok = _run(handle_remote_command("/macro list", 1, 2, tg, FakeTools()))
    assert ok is True
    assert tg.messages[-1][1] == "denied"


def test_macro_list():
    tg = FakeTG()
    with patch("app.bot.remote.computer_denied_message", return_value=None):
        ok = _run(handle_remote_command("/macro list", 100, 7, tg, FakeTools()))
    assert ok is True
    assert "deploy" in tg.messages[-1][1]


def test_macro_run():
    tg = FakeTG()
    with (
        patch("app.bot.remote.computer_denied_message", return_value=None),
        patch("app.bot.remote.deliver", new=AsyncMock()) as deliver,
    ):
        ok = _run(handle_remote_command("/macro run deploy", 100, 7, tg, FakeTools()))
    assert ok is True
    deliver.assert_awaited_once()


def test_file_usage_hint():
    tg = FakeTG()
    with patch("app.bot.remote.computer_denied_message", return_value=None):
        ok = _run(handle_remote_command("/file", 100, 7, tg, FakeTools()))
    assert ok is True
    assert "Використання" in tg.messages[-1][1]
