"""handle_update: whitelist, rate-limit, текст, голос, невідомий контент."""
from typing import Any

import app.router as router
from app.config import settings


class FakeTG:
    def __init__(self, file_path: str = "", content: bytes = b"") -> None:
        self.sent: list[tuple[int, str]] = []
        self._file_path = file_path
        self._content = content

    async def send_message(self, chat_id, text, parse_mode=None):
        self.sent.append((chat_id, text))

    async def get_file_path(self, file_id):
        return self._file_path

    async def download_file(self, file_path):
        return self._content


class FakeOrch:
    def __init__(self, reply: str = "ok") -> None:
        self.reply = reply
        self.calls: list[dict[str, Any]] = []

    async def process(self, payload):
        self.calls.append(payload)
        return self.reply


class FakeSTT:
    def __init__(self, text: str = "") -> None:
        self._text = text

    async def transcribe(self, audio, filename="voice.ogg"):
        return self._text


class FakeLimiter:
    def __init__(self, ok: bool = True) -> None:
        self._ok = ok

    async def allow(self, user_id):
        return self._ok


def _msg(**kw: Any) -> dict[str, Any]:
    return {"message": {"from": {"id": 42}, "chat": {"id": 5}, **kw}}


# --- чисті екстрактори ---
def test_extract_message_variants():
    assert router._extract_message({"message": {"a": 1}}) == {"a": 1}
    assert router._extract_message({"edited_message": {"b": 2}}) == {"b": 2}
    assert router._extract_message({}) is None


def test_extract_audio_file_id():
    assert router._extract_audio_file_id({"voice": {"file_id": "v1"}}) == "v1"
    assert router._extract_audio_file_id({"audio": {"file_id": "a1"}}) == "a1"
    assert router._extract_audio_file_id({"text": "hi"}) is None


# --- handle_update ---
async def test_ignores_non_whitelisted(monkeypatch):
    monkeypatch.setattr(settings, "allowed_user_ids", "")  # нікого не пускаємо
    tg, orch = FakeTG(), FakeOrch()
    await router.handle_update(_msg(text="hi"), tg, orch, FakeSTT(), FakeLimiter(True))
    assert tg.sent == []
    assert orch.calls == []


async def test_rate_limited(monkeypatch):
    monkeypatch.setattr(settings, "allowed_user_ids", "42")
    tg, orch = FakeTG(), FakeOrch()
    await router.handle_update(_msg(text="hi"), tg, orch, FakeSTT(), FakeLimiter(False))
    assert any("Забагато" in t for _, t in tg.sent)
    assert orch.calls == []


async def test_unknown_content_type(monkeypatch):
    monkeypatch.setattr(settings, "allowed_user_ids", "42")
    tg, orch = FakeTG(), FakeOrch()
    await router.handle_update(_msg(), tg, orch, FakeSTT(), FakeLimiter(True))
    assert any("розумію текст і голос" in t for _, t in tg.sent)
    assert orch.calls == []


async def test_text_flow(monkeypatch):
    monkeypatch.setattr(settings, "allowed_user_ids", "42")
    tg, orch = FakeTG(), FakeOrch("ВІДПОВІДЬ")
    await router.handle_update(_msg(text="привіт"), tg, orch, FakeSTT(), FakeLimiter(True))
    assert orch.calls[0]["text"] == "привіт"
    assert orch.calls[0]["type"] == "text"
    assert tg.sent[-1] == (5, "ВІДПОВІДЬ")


async def test_voice_flow(monkeypatch):
    monkeypatch.setattr(settings, "allowed_user_ids", "42")
    tg = FakeTG(file_path="voice/f.ogg", content=b"audio")
    orch = FakeOrch("ГОЛОС-ВІДПОВІДЬ")
    await router.handle_update(
        _msg(voice={"file_id": "abc"}), tg, orch, FakeSTT("розпізнаний текст"), FakeLimiter(True)
    )
    assert any(t.startswith("🎤") for _, t in tg.sent)  # ехо розпізнаного
    assert orch.calls[0]["text"] == "розпізнаний текст"
    assert orch.calls[0]["type"] == "voice"
    assert tg.sent[-1] == (5, "ГОЛОС-ВІДПОВІДЬ")


async def test_voice_unrecognized(monkeypatch):
    monkeypatch.setattr(settings, "allowed_user_ids", "42")
    tg = FakeTG(file_path="voice/f.ogg", content=b"audio")
    orch = FakeOrch()
    await router.handle_update(
        _msg(voice={"file_id": "abc"}), tg, orch, FakeSTT(""), FakeLimiter(True)
    )
    assert any("розпізнати" in t.lower() for _, t in tg.sent)
    assert orch.calls == []
