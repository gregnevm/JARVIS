"""TC-2 — group presence: чиста політика рішення + оркестратор (fake store)."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

from app.bot.group import (
    ACTION_COLLECT,
    ACTION_IGNORE,
    ACTION_RESPOND,
    decide_group_action,
    handle_group_message,
    is_addressed,
)


def test_decide_off_always_ignores() -> None:
    assert decide_group_action(ingest="off", addressed=True) == ACTION_IGNORE
    assert decide_group_action(ingest="off", addressed=False) == ACTION_IGNORE


def test_decide_addressed_level() -> None:
    assert decide_group_action(ingest="addressed", addressed=True) == ACTION_RESPOND
    assert decide_group_action(ingest="addressed", addressed=False) == ACTION_IGNORE


def test_decide_ambient_collects_unaddressed() -> None:
    assert decide_group_action(ingest="ambient", addressed=False) == ACTION_COLLECT
    assert decide_group_action(ingest="ambient", addressed=True) == ACTION_RESPOND


def test_decide_unknown_level_safe() -> None:
    assert decide_group_action(ingest="weird", addressed=True) == ACTION_IGNORE


def test_is_addressed_mention_and_reply() -> None:
    assert is_addressed({"text": "hey @jarvis_bot help"}, "jarvis_bot") is True
    assert is_addressed({"text": "no mention"}, "jarvis_bot") is False
    assert is_addressed({"reply_to_message": {"from": {"id": 42}}}, "jarvis_bot", bot_id=42) is True


class _FakeStore:
    def __init__(self, ingest: str) -> None:
        self._ingest = ingest
        self.collected: list = []
        self.responded: list = []
        self.members: list = []

    async def get_ingest(self, chat_id):
        return self._ingest

    async def upsert_member(self, chat_id, telegram_id, name):
        self.members.append((chat_id, telegram_id))

    async def collect(self, chat_id, message):
        self.collected.append(message)

    async def respond(self, chat_id, message):
        self.responded.append(message)


def _msg(text="hi", uid=7):
    return {"text": text, "from": {"id": uid, "username": "bob"}}


def test_handle_off_does_nothing():
    store = _FakeStore("off")
    action = asyncio.run(handle_group_message(
        _msg(), {"id": -100}, tg=AsyncMock(), group_store=store, bot_username="jarvis_bot"))
    assert action == ACTION_IGNORE
    assert store.collected == [] and store.members == []  # off → нічого не збираємо


def test_handle_ambient_collects_and_identifies():
    store = _FakeStore("ambient")
    action = asyncio.run(handle_group_message(
        _msg("random chatter"), {"id": -100}, tg=AsyncMock(), group_store=store, bot_username="jarvis_bot"))
    assert action == ACTION_COLLECT
    assert len(store.collected) == 1
    assert store.members == [(-100, 7)]  # ідентифікація члена


def test_handle_addressed_responds():
    store = _FakeStore("addressed")
    action = asyncio.run(handle_group_message(
        _msg("@jarvis_bot status?"), {"id": -100}, tg=AsyncMock(),
        group_store=store, bot_username="jarvis_bot"))
    assert action == ACTION_RESPOND
    assert len(store.responded) == 1


def test_handle_ingest_lookup_failure_is_ignore():
    store = _FakeStore("ambient")
    store.get_ingest = AsyncMock(side_effect=RuntimeError("memory down"))
    action = asyncio.run(handle_group_message(
        _msg(), {"id": -100}, tg=AsyncMock(), group_store=store, bot_username="jarvis_bot"))
    assert action == ACTION_IGNORE  # деградує безпечно
