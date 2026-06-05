"""show_in_app / історія — підроблений Redis, без мережі."""
import json

from app import artifacts, toolkit


class FakeRedis:
    def __init__(self) -> None:
        self.kv: dict[str, str] = {}
        self.ttl: dict[str, int] = {}
        self.lists: dict[str, list[str]] = {}

    async def set(self, key, value, ex=None):
        self.kv[key] = value
        if ex is not None:
            self.ttl[key] = ex

    async def lpush(self, key, *values):
        self.lists.setdefault(key, [])
        self.lists[key] = list(values) + self.lists[key]

    async def ltrim(self, key, start, end):
        if key in self.lists:
            self.lists[key] = self.lists[key][start : end + 1]

    async def expire(self, key, seconds):
        self.ttl[key] = seconds

    async def get(self, key):
        return self.kv.get(key)

    async def lrange(self, key, start, end):
        lst = self.lists.get(key, [])
        return lst[start:] if end == -1 else lst[start : end + 1]

    async def delete(self, *keys):
        for k in keys:
            self.kv.pop(k, None)
            self.lists.pop(k, None)

    async def aclose(self):
        pass


def _inject(monkeypatch) -> FakeRedis:
    fake = FakeRedis()
    monkeypatch.setattr(artifacts, "_redis", fake)
    return fake


async def test_show_in_app_stores_current_and_history(monkeypatch):
    fake = _inject(monkeypatch)
    out = await artifacts.show_in_app(42, "markdown", "# Привіт", "Звіт")
    assert "Канвас" in out
    rec = json.loads(fake.kv["artifact:42"])
    assert rec["kind"] == "markdown" and rec["title"] == "Звіт"
    assert len(fake.lists["artifacts:42"]) == 1
    assert json.loads(fake.lists["artifacts:42"][0])["id"] == rec["id"]


async def test_history_keeps_multiple(monkeypatch):
    fake = _inject(monkeypatch)
    await artifacts.show_in_app(1, "code", "a=1", "one")
    await artifacts.show_in_app(1, "code", "b=2", "two")
    hist = await artifacts.list_history(fake, 1)
    assert len(hist) == 2
    assert hist[0]["title"] == "two"


async def test_show_in_app_rejects_bad_kind_and_empty(monkeypatch):
    _inject(monkeypatch)
    assert "Невідомий тип" in await artifacts.show_in_app(1, "video", "x")
    assert "Порожній" in await artifacts.show_in_app(1, "html", "   ")


async def test_dispatch_routes_show_in_app(monkeypatch):
    fake = _inject(monkeypatch)
    res = await toolkit.dispatch(
        "show_in_app", {"kind": "code", "content": "print(1)", "title": "snippet"}, user_id=7
    )
    assert "Канвас" in res
    assert json.loads(fake.kv["artifact:7"])["kind"] == "code"
