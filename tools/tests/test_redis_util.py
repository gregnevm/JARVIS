"""get_redis / aclose_redis — канонічний lazy-singleton (консолідований у проході 28).

Іронія: проход 28 звів СІМ копій цього патерну до спільного `redis_util.
get_redis()`, від поведінки якого тепер залежать 8 модулів — а сам модуль
не мав ЖОДНОГО прямого тесту (лише непряме покриття через `monkeypatch.
setattr(<module>, "get_redis", lambda: fake)` у викликачів, що повністю
ОБМИНАЄ реальну singleton-логіку). Тут тестуємо САМЕ lazy-singleton
контракт: ледаче створення, кешування інстансу, і скидання через
`aclose_redis` (щоб наступний `get_redis()` створив новий клієнт)."""
from __future__ import annotations

import pytest

from app import redis_util


class _FakeAsyncRedis:
    """Сентинел замість справжнього aioredis.Redis — без мережі."""

    _n = 0

    def __init__(self) -> None:
        _FakeAsyncRedis._n += 1
        self.id = _FakeAsyncRedis._n
        self.closed = False

    async def aclose(self) -> None:
        self.closed = True


@pytest.fixture(autouse=True)
def _reset_singleton(monkeypatch: pytest.MonkeyPatch):
    """Ізолювати тести один від одного — глобальний `_redis` інакше протікає між ними."""
    monkeypatch.setattr(redis_util, "_redis", None)
    yield
    redis_util._redis = None


def test_get_redis_creates_lazily_via_from_url(monkeypatch: pytest.MonkeyPatch):
    calls: list[tuple[str, dict]] = []

    def fake_from_url(url, **kwargs):
        calls.append((url, kwargs))
        return _FakeAsyncRedis()

    monkeypatch.setattr(redis_util.aioredis, "from_url", fake_from_url)
    assert calls == []  # до першого виклику get_redis — нічого не створено

    client = redis_util.get_redis()
    assert isinstance(client, _FakeAsyncRedis)
    assert len(calls) == 1
    url, kwargs = calls[0]
    assert url == redis_util.settings.redis_url
    assert kwargs.get("decode_responses") is True


def test_get_redis_caches_instance_across_calls(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(redis_util.aioredis, "from_url", lambda *a, **kw: _FakeAsyncRedis())

    first = redis_util.get_redis()
    second = redis_util.get_redis()
    third = redis_util.get_redis()
    assert first is second is third
    assert first.id == second.id == third.id


async def test_aclose_redis_closes_and_resets_for_fresh_instance(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(redis_util.aioredis, "from_url", lambda *a, **kw: _FakeAsyncRedis())

    first = redis_util.get_redis()
    await redis_util.aclose_redis()

    assert first.closed is True
    assert redis_util._redis is None  # singleton скинутий

    second = redis_util.get_redis()
    assert second is not first
    assert second.closed is False


async def test_aclose_redis_is_noop_when_never_created(monkeypatch: pytest.MonkeyPatch):
    calls: list[_FakeAsyncRedis] = []
    monkeypatch.setattr(
        redis_util.aioredis, "from_url", lambda *a, **kw: calls.append(_FakeAsyncRedis()) or calls[-1]
    )

    await redis_util.aclose_redis()  # не повинно створювати клієнт чи падати
    assert calls == []
    assert redis_util._redis is None
