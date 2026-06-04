"""parse_directives + deliver — вирізання медіа-директив і доставка."""
import json

from app.outbound import deliver, parse_directives


class FakeTG:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []
        self.media: list[tuple[str, int, object]] = []

    async def send_message(self, chat_id, text, parse_mode=None, reply_markup=None):
        self.sent.append((chat_id, text))

    async def send_photo(self, chat_id, src, caption=None):
        self.media.append(("photo", chat_id, src))
        return True

    async def send_document(self, chat_id, src, caption=None):
        self.media.append(("document", chat_id, src))
        return True

    async def send_location(self, chat_id, latitude, longitude):
        self.media.append(("location", chat_id, (latitude, longitude)))
        return True


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


async def test_deliver_media_only():
    tg = FakeTG()
    out = await deliver(tg, 7, "[[photo:http://x/y.jpg]]")
    assert out == ""                       # тексту не лишилось
    assert tg.sent == []                   # порожній текст не шлемо
    assert ("photo", 7, "http://x/y.jpg") in tg.media


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
