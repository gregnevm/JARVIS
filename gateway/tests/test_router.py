"""handle_update: whitelist, rate-limit, текст, голос, невідомий контент."""
from typing import Any

import pytest

import app.router as router
from app.config import settings
from app.streaming import _PLACEHOLDER


@pytest.fixture(autouse=True)
def _streaming_off(monkeypatch):
    """Наявні тести перевіряють роутинг, не доставку → класичний (нестрімовий) шлях.
    Стрімовий шлях має власний тест нижче + test_streaming.py."""
    monkeypatch.setattr(settings, "enable_streaming", False)


class FakeTG:
    def __init__(self, file_path: str = "", content: bytes = b"") -> None:
        self.sent: list[tuple[int, str]] = []
        self.edits: list[tuple[int, str]] = []
        self.voices: list[tuple[int, bytes]] = []
        self.media: list[tuple[str, int, object]] = []
        self._file_path = file_path
        self._content = content

    async def send_message(self, chat_id, text, parse_mode=None, reply_markup=None):
        self.sent.append((chat_id, text))

    async def send_message_id(self, chat_id, text, parse_mode=None):
        self.sent.append((chat_id, text))
        return 99

    async def edit_message_text(
        self, chat_id, message_id, text, parse_mode=None, reply_markup=None
    ):
        self.edits.append((chat_id, text))

    async def send_chat_action(self, chat_id, action="typing"):
        pass

    async def send_voice(self, chat_id, audio, caption=None):
        self.voices.append((chat_id, audio))

    async def send_photo(self, chat_id, src, caption=None):
        self.media.append(("photo", chat_id, src))
        return True

    async def send_document(self, chat_id, src, caption=None):
        self.media.append(("document", chat_id, src))
        return True

    async def send_video(self, chat_id, src, caption=None):
        self.media.append(("video", chat_id, src))
        return True

    async def send_audio(self, chat_id, src, caption=None):
        self.media.append(("audio", chat_id, src))
        return True

    async def send_animation(self, chat_id, src, caption=None):
        self.media.append(("animation", chat_id, src))
        return True

    async def send_sticker(self, chat_id, src):
        self.media.append(("sticker", chat_id, src))
        return True

    async def send_location(self, chat_id, latitude, longitude):
        self.media.append(("location", chat_id, (latitude, longitude)))
        return True

    async def get_file_path(self, file_id):
        return self._file_path

    async def download_file(self, file_path):
        return self._content


class FakeTts:
    def __init__(self, audio: bytes = b"OGG") -> None:
        self._audio = audio

    async def synthesize(self, text):
        return self._audio


class FakeTools:
    def __init__(self, reply: str = "ok") -> None:
        self.reply = reply
        self.calls: list[dict[str, Any]] = []

    async def process(self, payload):
        self.calls.append(payload)
        return self.reply

    async def stream(self, payload):
        self.calls.append(payload)
        yield {"delta": self.reply}
        yield {"done": True, "text": self.reply, "mode": "chat", "iters": 0}


class FakeSvc:
    async def dashboard(self) -> dict[str, Any]:
        return {"agent_mode": "hybrid", "ollama_up": True}

    async def set_mode(self, mode: str) -> dict[str, Any]:
        return {"mode": mode}

    async def twin_status(self) -> dict[str, Any]:
        return {}


class FakeRedis:
    async def get(self, key):
        return None

    async def setex(self, key, ttl, value):
        pass

    async def delete(self, *keys):
        pass


async def _route(tg, tools, stt, limiter, msg, tts=None):
    await router.handle_update(msg, tg, tools, FakeSvc(), stt, limiter, FakeRedis(), tts)


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


def test_extract_audio_via_media():
    from app.media import extract_audio_media

    assert extract_audio_media({"voice": {"file_id": "v1"}}) is not None
    assert extract_audio_media({"audio": {"file_id": "a1"}}) is not None
    assert extract_audio_media({"text": "hi"}) is None


# --- handle_update ---
async def test_ignores_non_whitelisted(monkeypatch):
    monkeypatch.setattr(settings, "allowed_user_ids", "")  # нікого не пускаємо
    tg, tools = FakeTG(), FakeTools()
    await _route(tg, tools, FakeSTT(), FakeLimiter(True), _msg(text="hi"))
    assert tg.sent == []
    assert tools.calls == []


async def test_rate_limited(monkeypatch):
    monkeypatch.setattr(settings, "allowed_user_ids", "42")
    tg, tools = FakeTG(), FakeTools()
    await _route(tg, tools, FakeSTT(), FakeLimiter(False), _msg(text="hi"))
    assert any("Забагато" in t for _, t in tg.sent)
    assert tools.calls == []


async def test_unknown_content_type(monkeypatch):
    monkeypatch.setattr(settings, "allowed_user_ids", "42")
    tg, tools = FakeTG(), FakeTools()
    await _route(tg, tools, FakeSTT(), FakeLimiter(True), _msg())
    assert any("аудіо" in t.lower() or "текст" in t.lower() for _, t in tg.sent)
    assert tools.calls == []


async def test_text_flow(monkeypatch):
    monkeypatch.setattr(settings, "allowed_user_ids", "42")
    tg, tools = FakeTG(), FakeTools("ВІДПОВІДЬ")
    await _route(tg, tools, FakeSTT(), FakeLimiter(True), _msg(text="привіт"))
    assert tools.calls[0]["text"] == "привіт"
    assert tools.calls[0]["type"] == "text"
    assert tg.sent[-1] == (5, "ВІДПОВІДЬ")


async def test_text_flow_streaming(monkeypatch):
    monkeypatch.setattr(settings, "allowed_user_ids", "42")
    monkeypatch.setattr(settings, "enable_streaming", True)
    tg, tools = FakeTG(), FakeTools("ПОТІК")
    await _route(tg, tools, FakeSTT(), FakeLimiter(True), _msg(text="привіт"))
    assert tools.calls[0]["text"] == "привіт"          # стрім отримав payload
    assert (5, _PLACEHOLDER) in tg.sent                 # надіслано плейсхолдер
    assert tg.edits[-1] == (5, "ПОТІК")                 # фінальний едит = відповідь


async def test_audio_file_flow(monkeypatch):
    monkeypatch.setattr(settings, "allowed_user_ids", "42")
    tg = FakeTG(file_path="files/track.mp3", content=b"audio")
    tools = FakeTools("OK")
    await _route(
        tg, tools, FakeSTT("текст з mp3"), FakeLimiter(True),
        _msg(audio={"file_id": "a1", "mime_type": "audio/mpeg", "file_name": "t.mp3"}),
    )
    assert tools.calls[0]["type"] == "audio"


async def test_voice_flow(monkeypatch):
    monkeypatch.setattr(settings, "allowed_user_ids", "42")
    tg = FakeTG(file_path="voice/f.ogg", content=b"audio")
    tools = FakeTools("ГОЛОС-ВІДПОВІДЬ")
    await _route(tg, tools, FakeSTT("розпізнаний текст"), FakeLimiter(True), _msg(voice={"file_id": "abc"}))
    assert any(t.startswith("🎤") for _, t in tg.sent)  # ехо розпізнаного
    assert tools.calls[0]["text"] == "розпізнаний текст"
    assert tools.calls[0]["type"] == "voice"
    assert tg.sent[-1] == (5, "ГОЛОС-ВІДПОВІДЬ")


async def test_voice_unrecognized(monkeypatch):
    monkeypatch.setattr(settings, "allowed_user_ids", "42")
    tg = FakeTG(file_path="voice/f.ogg", content=b"audio")
    tools = FakeTools()
    await _route(tg, tools, FakeSTT(""), FakeLimiter(True), _msg(voice={"file_id": "abc"}))
    assert any("розпізнати" in t.lower() for _, t in tg.sent)
    assert tools.calls == []


async def test_voice_reply_when_enabled(monkeypatch):
    monkeypatch.setattr(settings, "allowed_user_ids", "42")
    tg = FakeTG(file_path="voice/f.ogg", content=b"audio")
    tools = FakeTools("ВІДПОВІДЬ")
    await _route(
        tg, tools, FakeSTT("розпізнано"), FakeLimiter(True), _msg(voice={"file_id": "abc"}), FakeTts(b"OGGDATA")
    )
    assert tg.voices and tg.voices[-1] == (5, b"OGGDATA")  # голосове надіслано
    assert any(t == "ВІДПОВІДЬ" for _, t in tg.sent)  # текст теж (надійність)


async def test_no_voice_reply_for_text_source(monkeypatch):
    monkeypatch.setattr(settings, "allowed_user_ids", "42")
    tg = FakeTG()
    tools = FakeTools("ВІДПОВІДЬ")
    await _route(tg, tools, FakeSTT(), FakeLimiter(True), _msg(text="привіт"), FakeTts())
    assert tg.voices == []  # на текстове повідомлення голосом не відповідаємо


async def test_voice_reply_skipped_when_tts_none(monkeypatch):
    monkeypatch.setattr(settings, "allowed_user_ids", "42")
    tg = FakeTG(file_path="voice/f.ogg", content=b"audio")
    tools = FakeTools("ВІДПОВІДЬ")
    await _route(tg, tools, FakeSTT("розпізнано"), FakeLimiter(True), _msg(voice={"file_id": "abc"}), None)
    assert tg.voices == []  # tts=None → лише текст


# --- будь-який контент: фото / документ / локація + повернення медіа ---
async def test_photo_flow(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "allowed_user_ids", "42")
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    tg = FakeTG(file_path="photos/p.jpg", content=b"JPEGDATA")
    tools = FakeTools("ОК")
    msg = _msg(
        photo=[{"file_id": "ph1", "width": 90, "height": 90},
               {"file_id": "ph2", "width": 800, "height": 600, "file_size": 1234}],
        caption="що тут?",
    )
    await _route(tg, tools, FakeSTT(), FakeLimiter(True), msg)
    assert tools.calls and tools.calls[0]["type"] == "photo"
    assert "що тут?" in tools.calls[0]["text"]           # підпис пробросили агенту
    assert any(str(tmp_path) in t for t in [tools.calls[0]["text"]])  # шлях у промпті
    assert any("прийняв" in t for _, t in tg.sent)        # ехо отримання


async def test_document_flow_inline_text(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "allowed_user_ids", "42")
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    tg = FakeTG(file_path="docs/notes.txt", content="Привіт із файлу".encode("utf-8"))
    tools = FakeTools("ОК")
    msg = _msg(document={"file_id": "d1", "file_name": "notes.txt", "mime_type": "text/plain"})
    await _route(tg, tools, FakeSTT(), FakeLimiter(True), msg)
    assert tools.calls[0]["type"] == "document"
    assert "Привіт із файлу" in tools.calls[0]["text"]    # текстовий файл вшито в промпт


async def test_location_flow(monkeypatch):
    monkeypatch.setattr(settings, "allowed_user_ids", "42")
    tg = FakeTG()
    tools = FakeTools("ОК")
    msg = _msg(location={"latitude": 50.45, "longitude": 30.52})
    await _route(tg, tools, FakeSTT(), FakeLimiter(True), msg)
    assert tools.calls[0]["type"] == "event"
    assert "50.45" in tools.calls[0]["text"] and "30.52" in tools.calls[0]["text"]


async def test_reply_with_media_directive(monkeypatch):
    monkeypatch.setattr(settings, "allowed_user_ids", "42")
    tg = FakeTG()
    tools = FakeTools("Ось картинка [[photo:http://x/y.jpg|котик]]")
    await _route(tg, tools, FakeSTT(), FakeLimiter(True), _msg(text="дай фото"))
    assert any("Ось картинка" in t for _, t in tg.sent)   # чистий текст без директиви
    assert not any("[[photo" in t for _, t in tg.sent)    # директиву вирізано
    assert ("photo", 5, "http://x/y.jpg") in tg.media     # фото надіслано
