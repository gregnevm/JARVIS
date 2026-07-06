"""RedisBus (SY-B2.1): серіалізація, канал, фан-аут із анти-петлями, малформед."""
from __future__ import annotations

import json
from typing import Any

from jarvis_core.bus import BUS_HOP_KEY, BusMeta, RedisBus
from jarvis_core.passport import Passport


class _FakeRedis:
    def __init__(self) -> None:
        self.published: list[tuple[str, str]] = []
        self.fail = False

    async def publish(self, channel: str, message: str) -> int:
        if self.fail:
            raise ConnectionError("redis down")
        self.published.append((channel, message))
        return 1

    def pubsub(self) -> Any:  # listener не тестуємо циклом — handle_raw напряму
        raise NotImplementedError


class _Spy:
    def __init__(self) -> None:
        self.got: list[tuple[Passport, BusMeta]] = []

    async def __call__(self, passport: Passport, meta: BusMeta) -> None:
        self.got.append((passport, meta))


def _p(kind: str = "note", tags: list[str] | None = None, **kw: Any) -> Passport:
    return Passport(
        kind=kind, summary="подія", tags=tags if tags is not None else [f"kind:{kind}"], **kw
    )


async def test_emit_publishes_json_to_org_channel():
    r = _FakeRedis()
    bus = RedisBus(r, org_id="org-1")
    assert bus.channel == "jarvis:org-1:bus:events"
    await bus.emit(_p("invoice"), BusMeta(user_id=42, org_id="org-1", store_id=7))
    channel, raw = r.published[0]
    assert channel == "jarvis:org-1:bus:events"
    data = json.loads(raw)
    assert data["passport"]["kind"] == "invoice"
    assert data["meta"] == {"user_id": 42, "org_id": "org-1", "store_id": 7}


async def test_default_org_legacy_channel():
    bus = RedisBus(_FakeRedis())
    assert bus.channel == "jarvis:bus:events"


async def test_publish_failure_is_swallowed():
    r = _FakeRedis()
    r.fail = True
    await RedisBus(r).emit(_p())  # не кидає (транспорт нефатальний)


async def test_roundtrip_emit_handle_deliver():
    r = _FakeRedis()
    sender = RedisBus(r, org_id="org-1")
    receiver = RedisBus(_FakeRedis(), org_id="org-1")
    spy = _Spy()
    receiver.subscribe(["kind:invoice"], spy, name="billing")
    await sender.emit(
        _p("invoice", tags=["kind:invoice", "entity:acme"]),
        BusMeta(user_id=42, org_id="org-1", store_id=9),
    )
    receiver.handle_raw(r.published[0][1])  # «доставка» каналу
    await receiver.drain()
    passport, meta = spy.got[0]
    assert passport.kind == "invoice" and "entity:acme" in passport.tags
    assert meta.user_id == 42 and meta.store_id == 9


async def test_handle_raw_containment_and_source_skip():
    bus = RedisBus(_FakeRedis())
    spy = _Spy()
    bus.subscribe(["kind:note"], spy, name="daily_builder")
    own = json.dumps({"passport": _p("note", source="daily_builder").to_store(), "meta": {}})
    other = json.dumps({"passport": _p("note", source="tg").to_store(), "meta": {}})
    unrelated = json.dumps({"passport": _p("sms", tags=["kind:sms"]).to_store(), "meta": {}})
    bus.handle_raw(own)        # власний source — петля, скіп
    bus.handle_raw(unrelated)  # не матчить containment
    bus.handle_raw(other)
    await bus.drain()
    assert len(spy.got) == 1 and spy.got[0][0].source == "tg"


async def test_handle_raw_hop_limit():
    bus = RedisBus(_FakeRedis(), hop_limit=2)
    spy = _Spy()
    bus.subscribe([], spy, name="all")
    deep = _p("note", payload={BUS_HOP_KEY: 2})
    bus.handle_raw(json.dumps({"passport": deep.to_store(), "meta": {}}))
    await bus.drain()
    assert spy.got == []


async def test_handle_raw_malformed_ignored():
    bus = RedisBus(_FakeRedis())
    spy = _Spy()
    bus.subscribe([], spy, name="all")
    bus.handle_raw("не json")
    bus.handle_raw(json.dumps({"нема": "passport"}))
    bus.handle_raw(json.dumps({"passport": "not-a-dict"}))
    await bus.drain()
    assert spy.got == []


async def test_failing_subscriber_isolated():
    bus = RedisBus(_FakeRedis())

    async def boom(passport: Passport, meta: BusMeta) -> None:
        raise RuntimeError("впав")

    spy = _Spy()
    bus.subscribe([], boom, name="boom")
    bus.subscribe([], spy, name="ok")
    bus.handle_raw(json.dumps({"passport": _p().to_store(), "meta": {}}))
    await bus.drain()
    assert len(spy.got) == 1


async def test_unsubscribe():
    bus = RedisBus(_FakeRedis())
    spy = _Spy()
    sub = bus.subscribe([], spy, name="tmp")
    sub.unsubscribe()
    bus.handle_raw(json.dumps({"passport": _p().to_store(), "meta": {}}))
    await bus.drain()
    assert spy.got == []
