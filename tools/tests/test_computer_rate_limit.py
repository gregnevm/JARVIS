"""Computer rate limit per hour."""
import pytest

from app.computer_rate_limit import check_mutating_allowed, record_mutating
from app.config import settings


class FakeRedis:
    def __init__(self) -> None:
        self.data: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self.data.get(key)

    def pipeline(self) -> "FakePipe":
        return FakePipe(self)


class FakePipe:
    def __init__(self, r: FakeRedis) -> None:
        self._r = r
        self._ops: list[tuple[str, str]] = []

    def incr(self, key: str) -> None:
        self._ops.append(("incr", key))

    def expire(self, key: str, sec: int) -> None:
        self._ops.append(("expire", key, str(sec)))

    async def execute(self) -> None:
        for op, key in self._ops:
            if op == "incr":
                self._r.data[key] = str(int(self._r.data.get(key, "0")) + 1)


@pytest.fixture
def fake_redis(monkeypatch: pytest.MonkeyPatch):
    fr = FakeRedis()
    monkeypatch.setattr("app.computer_rate_limit._redis", fr)
    monkeypatch.setattr(settings, "computer_rate_limit_per_hour", 2)
    return fr


async def test_rate_limit_blocks(fake_redis: FakeRedis):
    await record_mutating(1)
    await record_mutating(1)
    msg = await check_mutating_allowed(1)
    assert msg and "Ліміт" in msg


async def test_rate_limit_disabled(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "computer_rate_limit_per_hour", 0)
    assert await check_mutating_allowed(1) is None
