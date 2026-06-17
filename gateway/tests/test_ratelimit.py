"""RateLimiter — фіксоване вікно + fail-open при проблемах Redis."""
from app.ratelimit import RateLimiter


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, int] = {}
        self.expired: list[tuple[str, int]] = []

    async def incr(self, name: str) -> int:
        self.store[name] = self.store.get(name, 0) + 1
        return self.store[name]

    async def expire(self, name: str, seconds: int) -> None:
        self.expired.append((name, seconds))


class BoomRedis:
    async def incr(self, name: str) -> int:
        raise RuntimeError("redis down")

    async def expire(self, name: str, seconds: int) -> None:  # pragma: no cover
        ...


async def test_allows_under_limit_then_blocks():
    rl = RateLimiter(FakeRedis(), limit_per_min=3)
    assert [await rl.allow(1) for _ in range(4)] == [True, True, True, False]


async def test_expire_set_only_on_first_hit():
    redis = FakeRedis()
    rl = RateLimiter(redis, limit_per_min=5)
    await rl.allow(7)
    await rl.allow(7)
    assert len(redis.expired) == 1
    assert redis.expired[0][1] == 60


async def test_no_redis_always_allows():
    assert await RateLimiter(None, limit_per_min=5).allow(1) is True


async def test_zero_limit_always_allows():
    assert await RateLimiter(FakeRedis(), limit_per_min=0).allow(1) is True


async def test_fail_open_when_redis_errors():
    assert await RateLimiter(BoomRedis(), limit_per_min=1).allow(1) is True


async def test_key_is_org_prefixed():
    """P1-4 (AGENTS §5): ключ rate-limit має org-префікс `jarvis:{org_id}:rl:...`."""
    redis = FakeRedis()
    await RateLimiter(redis, limit_per_min=5).allow(42)
    key = next(iter(redis.store))
    assert key.startswith("jarvis:")
    assert ":rl:42:" in key
