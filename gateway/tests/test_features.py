"""Нові типи контенту: контекст (reply/forward), альбоми, реакції, inline, кнопки."""
import json
from typing import Any

import pytest

import app.router as router
from app.config import settings
from app.media import album_prompt, message_context
from app.outbound import build_reply_markup, parse_directives


# --- чисті хелпери ---
def test_message_context_reply_and_forward():
    msg = {
        "text": "так",
        "reply_to_message": {"text": "Це питання?"},
        "forward_origin": {"type": "user", "sender_user": {"first_name": "Іван"}},
    }
    ctx = message_context(msg)
    assert "Переслано від: Іван" in ctx
    assert "Це питання?" in ctx


def test_message_context_empty():
    assert message_context({"text": "hi"}) == ""


def test_album_prompt():
    items = [
        {"path": "/data/uploads/a.jpg", "kind": "photo"},
        {"path": "/data/uploads/b.jpg", "kind": "photo"},
    ]
    out = album_prompt(items, "мій альбом")
    assert "2 файлів" in out and "a.jpg" in out and "b.jpg" in out
    assert "мій альбом" in out


def test_new_reaction_emoji():
    r = {"new_reaction": [{"type": "emoji", "emoji": "🔥"}], "old_reaction": []}
    assert router._new_reaction_emoji(r) == "🔥"
    # реакцію зняли → None
    removed = {"new_reaction": [], "old_reaction": [{"type": "emoji", "emoji": "🔥"}]}
    assert router._new_reaction_emoji(removed) is None


def test_buttons_directive_builds_markup():
    clean, directives = parse_directives(
        "ось посилання [[buttons:Google | https://google.com ;; Bing | https://bing.com]]"
    )
    assert clean == "ось посилання"
    markup = build_reply_markup(directives)
    assert markup is not None
    rows = markup["inline_keyboard"]
    assert rows[0][0] == {"text": "Google", "url": "https://google.com"}
    assert rows[1][0] == {"text": "Bing", "url": "https://bing.com"}


def test_reaction_directive_parsed():
    clean, directives = parse_directives("клас [[reaction:👍]]")
    assert clean == "клас"
    assert directives[0].kind == "reaction" and directives[0].src == "👍"


# --- роутерні хендлери ---
class FakeTG:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []
        self.inline_answers: list[tuple[str, list[dict[str, Any]]]] = []
        self.reactions: list[tuple[int, int, str]] = []

    async def send_message(self, chat_id, text, parse_mode=None, reply_markup=None, **kwargs):
        self.sent.append((chat_id, text))

    async def answer_inline_query(self, inline_query_id, results, cache_time=0):
        self.inline_answers.append((inline_query_id, results))

    async def set_message_reaction(self, chat_id, message_id, emoji, is_big=False):
        self.reactions.append((chat_id, message_id, emoji))
        return True


class FakeTools:
    def __init__(self, reply: str = "OK") -> None:
        self.reply = reply
        self.calls: list[dict[str, Any]] = []

    async def process(self, payload):
        self.calls.append(payload)
        return self.reply


class FakeLimiter:
    def __init__(self, ok: bool = True) -> None:
        self._ok = ok

    async def allow(self, user_id, *, limit=None):
        return self._ok


async def test_inline_query_answers(monkeypatch):
    monkeypatch.setattr(settings, "allowed_user_ids", "42")
    tg, tools = FakeTG(), FakeTools("Відповідь")
    inline = {"id": "iq1", "from": {"id": 42}, "query": "котики"}
    await router._handle_inline_query(inline, tg, tools)
    assert tg.inline_answers
    iq_id, results = tg.inline_answers[0]
    assert iq_id == "iq1"
    assert results[0]["input_message_content"]["message_text"] == "Відповідь"


async def test_inline_query_blocks_non_whitelisted(monkeypatch):
    monkeypatch.setattr(settings, "allowed_user_ids", "")
    tg, tools = FakeTG(), FakeTools()
    await router._handle_inline_query({"id": "iq1", "from": {"id": 7}, "query": "x"}, tg, tools)
    assert tg.inline_answers == []


async def test_reaction_triggers_reply(monkeypatch):
    monkeypatch.setattr(settings, "allowed_user_ids", "42")
    monkeypatch.setattr(settings, "enable_reaction_replies", True)
    tg, tools = FakeTG(), FakeTools("ага")
    reaction = {
        "user": {"id": 42},
        "chat": {"id": 5},
        "new_reaction": [{"type": "emoji", "emoji": "🔥"}],
        "old_reaction": [],
    }
    await router._handle_reaction(reaction, tg, tools, FakeLimiter(True))
    assert tools.calls and "🔥" in tools.calls[0]["text"]
    assert any("ага" in t for _, t in tg.sent)


async def test_reaction_disabled(monkeypatch):
    monkeypatch.setattr(settings, "allowed_user_ids", "42")
    monkeypatch.setattr(settings, "enable_reaction_replies", False)
    tg, tools = FakeTG(), FakeTools()
    reaction = {
        "user": {"id": 42}, "chat": {"id": 5},
        "new_reaction": [{"type": "emoji", "emoji": "🔥"}], "old_reaction": [],
    }
    await router._handle_reaction(reaction, tg, tools, FakeLimiter(True))
    assert tools.calls == []


# --- альбом (media_group) через Redis-фейк ---
class FakeRedis:
    def __init__(self) -> None:
        self.lists: dict[str, list[str]] = {}
        self.kv: dict[str, str] = {}

    async def rpush(self, key, value):
        self.lists.setdefault(key, []).append(value)

    async def expire(self, key, seconds):
        pass

    async def set(self, key, value, nx=False, ex=None):
        if nx and key in self.kv:
            return None
        self.kv[key] = value
        return True

    async def get(self, key):
        return self.kv.get(key)

    async def lrange(self, key, start, end):
        return self.lists.get(key, [])

    async def delete(self, *keys):
        for k in keys:
            self.lists.pop(k, None)
            self.kv.pop(k, None)


async def test_album_collected_and_processed(monkeypatch):
    monkeypatch.setattr(settings, "allowed_user_ids", "42")
    monkeypatch.setattr(settings, "album_collect_seconds", 0.0)
    monkeypatch.setattr(settings, "enable_streaming", False)
    monkeypatch.setattr(router, "_save_attachment", _fake_save)

    tg, tools, redis = FakeTG(), FakeTools("готово"), FakeRedis()
    msg = {
        "media_group_id": "G1",
        "message_id": 100,
        "photo": [{"file_id": "p1", "width": 100, "height": 100}],
        "caption": "альбом",
    }
    await router._handle_album(msg, 5, 42, tg, tools, redis)
    assert tools.calls and "альбом" in tools.calls[0]["text"]
    assert any("прийняв альбом" in t for _, t in tg.sent)


async def _fake_save(att, tg):
    return f"/data/uploads/{att.file_id}.jpg"
