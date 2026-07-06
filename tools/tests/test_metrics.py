"""Metrics rolling window."""
import pytest
from app import metrics


class FakeRedis:
    def __init__(self) -> None:
        self.lists: dict[str, list[str]] = {}
        self.kv: dict[str, int] = {}

    def pipeline(self) -> "FakePipe":
        return FakePipe(self)

    async def lpush(self, key: str, val: str) -> None:
        self.lists.setdefault(key, []).insert(0, val)

    async def ltrim(self, key: str, start: int, end: int) -> None:
        self.lists[key] = self.lists.get(key, [])[start : end + 1]

    async def lrange(self, key: str, start: int, end: int) -> list[str]:
        return self.lists.get(key, [])[start : end + 1]

    async def get(self, key: str) -> str | None:
        v = self.kv.get(key)
        return str(v) if v is not None else None

    async def incr(self, key: str) -> int:
        self.kv[key] = self.kv.get(key, 0) + 1
        return self.kv[key]

    def scan_iter(self, match: str = "", count: int = 50):
        async def _gen():
            prefix = match.replace("*", "")
            for k in self.lists:
                if k.startswith(prefix):
                    yield k

        return _gen()


class FakePipe:
    def __init__(self, r: FakeRedis) -> None:
        self._r = r
        self._ops: list[tuple[str, str, object]] = []

    def lpush(self, key: str, val: str) -> None:
        self._ops.append(("lpush", key, val))

    def ltrim(self, key: str, start: int, end: int) -> None:
        self._ops.append(("ltrim", key, (start, end)))

    def incr(self, key: str) -> None:
        self._ops.append(("incr", key, None))

    async def execute(self) -> None:
        for op, key, arg in self._ops:
            if op == "lpush":
                await self._r.lpush(key, str(arg))
            elif op == "ltrim":
                s, e = arg
                await self._r.ltrim(key, s, e)
            elif op == "incr":
                await self._r.incr(key)


@pytest.mark.asyncio
async def test_record_and_summary(monkeypatch: pytest.MonkeyPatch):
    fake = FakeRedis()
    monkeypatch.setattr(metrics, "get_redis", lambda: fake)

    await metrics.record_turn(1200, "agent", 2)
    await metrics.record_turn(800, "chat", 0)
    await metrics.record_tool("calc", 50)
    await metrics.record_rag(2)
    await metrics.record_rag(0)
    await metrics.record_inference("qwen2.5:7b", 100, 2_000_000_000)
    await metrics.record_inference("qwen2.5:7b", 50, 1_000_000_000)

    s = await metrics.summary()
    assert s["turn_ms"]["count"] == 2
    assert s["tok_s"]["count"] == 2
    assert s["tok_s"]["p50"] > 0
    assert s["rag_queries"] == 2
    assert s["rag_hit_rate"] == 0.5
    assert "calc" in s["tools"]


@pytest.mark.asyncio
async def test_org_id_scopes_keys_and_isolates(monkeypatch: pytest.MonkeyPatch):
    """AP-4.4: org_id produces `jarvis:{org}:metrics:*` keys; the default (None)
    org is isolated from a scoped org and stays byte-compatible (S2)."""
    fake = FakeRedis()
    monkeypatch.setattr(metrics, "get_redis", lambda: fake)

    await metrics.record_turn(1000, "agent", 1, org_id="acme")
    await metrics.record_tool("calc", 42, org_id="acme")
    await metrics.record_rag(1, org_id="acme")

    # keys carry the org prefix
    assert "jarvis:acme:metrics:turns" in fake.lists
    assert "jarvis:acme:metrics:tool_lat:calc" in fake.lists
    assert "jarvis:acme:metrics:rag_queries" in fake.kv

    # the scoped org reads back its own data
    s_acme = await metrics.summary(org_id="acme")
    assert s_acme["turn_ms"]["count"] == 1
    assert "calc" in s_acme["tools"]
    assert s_acme["rag_queries"] == 1

    # default (unscoped) org sees none of acme's data — isolation holds
    s_default = await metrics.summary()
    assert s_default["turn_ms"]["count"] == 0
    assert s_default["tools"] == {}
    assert s_default["rag_queries"] == 0


def test_default_keys_are_byte_compatible_with_legacy():
    """S2: org_id=None must yield the exact pre-split literals so self-hosted
    deployments keep their existing metrics keys — zero migration."""
    assert metrics._mkey(None, "turns") == "jarvis:metrics:turns"
    assert metrics._mkey(None, "tok_s") == "jarvis:metrics:tok_s"
    assert metrics._mkey(None, "rag_queries") == "jarvis:metrics:rag_queries"
    assert metrics._mkey(None, "rag_hits") == "jarvis:metrics:rag_hits"
    assert metrics._mkey(None, "tool_lat", "calc") == "jarvis:metrics:tool_lat:calc"
