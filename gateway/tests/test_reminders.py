"""deliver_due — доставка прострочених нагадувань із Redis ZSET (фейки, без мережі)."""
import json

from app import reminders


class FakeRedis:
    def __init__(self) -> None:
        self.z: dict[str, float] = {}

    async def zadd(self, key, mapping):
        self.z.update(mapping)

    async def zrangebyscore(self, key, mn, mx, start=0, num=None):
        lo = float("-inf") if mn == "-inf" else float(mn)
        hi = float("inf") if mx == "+inf" else float(mx)
        out = [m for m, s in sorted(self.z.items(), key=lambda kv: kv[1]) if lo <= s <= hi]
        if num is not None:
            return out[start : start + num]
        return out[start:]

    async def zrem(self, key, *members):
        for m in members:
            self.z.pop(m, None)


class FakeTG:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []

    async def send_message(self, chat_id, text, parse_mode=None):
        self.sent.append((chat_id, text))


def _member(user_id: int, text: str) -> str:
    return json.dumps({"id": "x", "user_id": user_id, "text": text}, ensure_ascii=False)


async def test_delivers_due_and_keeps_future():
    r = FakeRedis()
    await r.zadd("reminders", {_member(42, "хліб"): 100})
    await r.zadd("reminders", {_member(42, "потім"): 10_000})
    tg = FakeTG()
    n = await reminders.deliver_due(r, tg, now=200)
    assert n == 1
    assert tg.sent == [(42, "⏰ Нагадування: хліб")]
    assert len(r.z) == 1  # майбутнє нагадування лишилось у ZSET


async def test_drops_malformed_member():
    r = FakeRedis()
    await r.zadd("reminders", {"не-json": 1})
    tg = FakeTG()
    n = await reminders.deliver_due(r, tg, now=100)
    assert n == 0
    assert r.z == {}  # сміття прибрали з ZSET


async def test_nothing_due_sends_nothing():
    r = FakeRedis()
    await r.zadd("reminders", {_member(1, "майбутнє"): 9999})
    tg = FakeTG()
    assert await reminders.deliver_due(r, tg, now=100) == 0
    assert tg.sent == []
    assert len(r.z) == 1
