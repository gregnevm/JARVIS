"""Callback-реєстр (`bot/commands.handle_callback` через CallbackRegistry)."""
from __future__ import annotations

import asyncio

from app.bot.commands import callbacks, handle_callback
from app.config import settings


class FakeTg:
    def __init__(self) -> None:
        self.sent: list[str] = []
        self.edited: list[str] = []
        self.acks: list[str | None] = []

    async def send_message(self, chat_id, text, parse_mode=None, reply_markup=None, **kw):
        self.sent.append(text)

    async def edit_message_text(self, chat_id, message_id, text, parse_mode=None, reply_markup=None, **kw):
        self.edited.append(text)

    async def answer_callback_query(self, cq_id, text=None, **kw):
        self.acks.append(text)


class FakeSvc:
    def __init__(self) -> None:
        self.set_calls: list[str] = []

    async def dashboard(self):
        return {"agent_mode": "hybrid", "ollama_up": True}

    async def twin_status(self):
        return {}

    async def set_mode(self, mode):
        self.set_calls.append(mode)
        return {"mode": mode}


def _cb(data: str) -> dict:
    return {"id": "cq1", "data": data, "from": {"id": 42}, "message": {"chat": {"id": 5}, "message_id": 9}}


def _run(coro):
    return asyncio.run(coro)


def test_registry_has_all_prefixes():
    for p in ("conn:", "acc:", "adm:", "pln:", "cmp:", "agt:", "mode:", "dash:"):
        assert callbacks.match(p) is not None, p
    # довший префікс виграє (cmpA не перехоплюється cmp)
    assert callbacks.match("dash:menu").prefix == "dash:"


def test_mode_callback_sets_mode_and_acks(monkeypatch):
    monkeypatch.setattr(settings, "admin_user_ids", "42")  # дозволено міняти режим
    tg, svc = FakeTg(), FakeSvc()
    _run(handle_callback(_cb("mode:agent"), tg, svc, redis=None, tools=None))
    assert svc.set_calls == ["agent"]
    # відредаговано повідомлення + toast "Режим: agent"
    assert any("agent" in e for e in tg.edited)
    assert any(a and "agent" in a for a in tg.acks)


def test_dash_menu_renders_panel(monkeypatch):
    monkeypatch.setattr(settings, "admin_user_ids", "42")
    tg, svc = FakeTg(), FakeSvc()
    _run(handle_callback(_cb("dash:menu"), tg, svc, redis=None, tools=None))
    assert any("JARVIS" in e for e in tg.edited)
    assert tg.acks  # фінальний ack


def test_unknown_callback_just_acks():
    tg, svc = FakeTg(), FakeSvc()
    _run(handle_callback(_cb("zzz:nope"), tg, svc, redis=None, tools=None))
    assert tg.acks == [None]
    assert not tg.sent and not tg.edited


def test_tools_guard_falls_back_to_ack():
    # pln: потребує tools; без них — не падаємо, лише ack (поведінка збережена)
    tg, svc = FakeTg(), FakeSvc()
    _run(handle_callback(_cb("pln:Y:abc"), tg, svc, redis=None, tools=None))
    assert tg.acks == [None]


def test_missing_chat_id_noop():
    tg, svc = FakeTg(), FakeSvc()
    _run(handle_callback({"id": "c", "data": "dash:menu", "from": {"id": 1}}, tg, svc))
    assert not tg.acks and not tg.edited
