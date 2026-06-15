"""parse_directives + deliver — вирізання медіа-директив і доставка."""
import json

from app.outbound import deliver, parse_directives, resolve_media_src


class FakeTG:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []
        self.media: list[tuple[str, int, object]] = []
        self.photo_ok = True

    async def send_message(self, chat_id, text, parse_mode=None, reply_markup=None, **kwargs):
        self.sent.append((chat_id, text))

    async def send_photo(self, chat_id, src, caption=None):
        self.media.append(("photo", chat_id, src))
        return self.photo_ok

    async def send_document(self, chat_id, src, caption=None):
        self.media.append(("document", chat_id, src))
        return True

    async def send_location(self, chat_id, latitude, longitude):
        self.media.append(("location", chat_id, (latitude, longitude)))
        return True

    async def send_voice(self, chat_id, audio, caption=None):
        self.media.append(("voice", chat_id, audio))


def test_no_directives_returns_text():
    clean, directives = parse_directives("просто текст")
    assert clean == "просто текст"
    assert directives == []


def test_photo_directive_with_caption():
    clean, directives = parse_directives("дивись [[photo:http://x/y.jpg|котик]]")
    assert clean == "дивись"
    assert len(directives) == 1
    d = directives[0]
    assert d.kind == "photo" and d.src == "http://x/y.jpg" and d.caption == "котик"


def test_file_alias_and_location():
    text = "файл [[file:/data/uploads/a.pdf]] і місце [[location:50.45,30.52]]"
    clean, directives = parse_directives(text)
    assert "файл" in clean and "місце" in clean
    kinds = {d.kind for d in directives}
    assert kinds == {"document", "location"}


def test_unknown_directive_left_intact():
    clean, directives = parse_directives("код [[weird:abc]] далі")
    assert "[[weird:abc]]" in clean
    assert directives == []


async def test_deliver_sends_text_and_media():
    tg = FakeTG()
    out = await deliver(tg, 7, "тут [[photo:http://x/y.jpg]] кінець")
    assert out == "тут  кінець".strip() or "тут" in out
    assert any("тут" in t for _, t in tg.sent)
    assert ("photo", 7, "http://x/y.jpg") in tg.media


async def test_voice_directive_uses_send_voice(tmp_path):
    p = tmp_path / "v.ogg"
    p.write_bytes(b"OggS")
    tg = FakeTG()
    await deliver(tg, 7, f"[[voice:{p}]]")
    assert any(m[0] == "voice" for m in tg.media)


async def test_deliver_media_only():
    tg = FakeTG()
    out = await deliver(tg, 7, "[[photo:http://x/y.jpg]]")
    assert out == ""                       # тексту не лишилось
    assert tg.sent == []                   # порожній текст не шлемо
    assert ("photo", 7, "http://x/y.jpg") in tg.media


def test_resolve_bare_filename_under_uploads(tmp_path, monkeypatch):
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    img = uploads / "puppy.jpg"
    img.write_bytes(b"\xff\xd8\xff")
    monkeypatch.setattr(
        "app.outbound._UPLOAD_SEARCH_DIRS", (str(uploads), str(tmp_path))
    )
    assert resolve_media_src("puppy.jpg") == str(uploads / "puppy.jpg")


async def test_deliver_warns_on_missing_local_photo():
    tg = FakeTG()
    tg.photo_ok = False
    await deliver(tg, 7, "ось [[photo:puppy.jpg|щеня]]")
    assert any("Не вдалося надіслати" in t for _, t in tg.sent)
    assert not any("IMAGE_GEN_URL" in t for _, t in tg.sent)


class _Redis:
    def __init__(self) -> None:
        self.kv: dict[str, str] = {}
        self.lists: dict[str, list[str]] = {}

    async def set(self, key, value, ex=None):
        self.kv[key] = value

    async def lpush(self, key, *values):
        self.lists.setdefault(key, [])
        self.lists[key] = list(values) + self.lists[key]

    async def ltrim(self, key, start, end):
        if key in self.lists:
            self.lists[key] = self.lists[key][start : end + 1]

    async def expire(self, key, seconds):
        pass


async def test_deliver_pushes_app_directive_to_redis():
    tg = FakeTG()
    redis = _Redis()
    out = await deliver(
        tg, 7, "Ось [[app:markdown|# Hi]] готово", redis=redis, user_id=7
    )
    assert "готово" in out and "[[app" not in out
    rec = json.loads(redis.kv["artifact:7"])
    assert rec["kind"] == "markdown" and rec["content"] == "# Hi"
