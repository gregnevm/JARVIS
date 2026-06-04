"""[[app:…]] директиви + Redis-історія Канвасу."""
import json

from app import artifacts


class FakeRedis:
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

    async def get(self, key):
        return self.kv.get(key)

    async def lrange(self, key, start, end):
        lst = self.lists.get(key, [])
        return lst[start:] if end == -1 else lst[start : end + 1]

    async def delete(self, *keys):
        for k in keys:
            self.kv.pop(k, None)
            self.lists.pop(k, None)


def test_parse_app_with_title():
    clean, dirs = artifacts.parse_app_directives("дивись [[app:html|Звіт|<b>ok</b>]] тут")
    assert clean == "дивись  тут".strip() or "дивись" in clean
    assert len(dirs) == 1
    assert dirs[0].kind == "html" and dirs[0].title == "Звіт"


def test_parse_app_content_only():
    clean, dirs = artifacts.parse_app_directives("[[app:markdown|# Hi]]")
    assert clean == ""
    assert dirs[0].content == "# Hi" and dirs[0].title == ""


async def test_apply_app_directives_pushes_history():
    fake = FakeRedis()
    text = "Ось [[app:code|snippet|print(1)]] готово"
    clean = await artifacts.apply_app_directives(fake, 5, text)
    assert "[[app" not in clean
    assert "готово" in clean
    cur = await artifacts.get_current(fake, 5)
    assert cur and cur["kind"] == "code" and cur["content"] == "print(1)"
    hist = await artifacts.list_history(fake, 5)
    assert len(hist) == 1


async def test_clear_user():
    fake = FakeRedis()
    await artifacts.apply_app_directives(fake, 1, "[[app:url|https://x.com]]")
    await artifacts.clear_user(fake, 1)
    assert await artifacts.get_current(fake, 1) is None
    assert await artifacts.list_history(fake, 1) == []
