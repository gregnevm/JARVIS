"""PassportBus (SY-B1.1): containment-матчинг, фан-аут, ізоляція збоїв, анти-петлі."""
from __future__ import annotations

from typing import Any

from jarvis_core.bus import (
    BUS_HOP_KEY,
    BusMeta,
    InProcBus,
    hop_of,
    next_hop_payload,
)
from jarvis_core.passport import Passport


def _p(
    kind: str = "note",
    tags: list[str] | None = None,
    source: str | None = None,
    payload: dict[str, Any] | None = None,
    summary: str = "подія",
) -> Passport:
    return Passport(
        kind=kind,
        summary=summary,
        tags=tags if tags is not None else [f"kind:{kind}"],
        source=source,
        payload=payload or {},
    )


class _Spy:
    def __init__(self) -> None:
        self.got: list[tuple[Passport, BusMeta]] = []

    async def __call__(self, passport: Passport, meta: BusMeta) -> None:
        self.got.append((passport, meta))


# --- матчинг (та сама containment-семантика, що GIN-ретрив) ---

async def test_containment_matching_and_meta():
    bus = InProcBus()
    spy = _Spy()
    bus.subscribe(["kind:invoice", "sensitivity:finance"], spy, name="fin")
    await bus.emit(
        _p("invoice", tags=["kind:invoice", "sensitivity:finance", "entity:acme"]),
        BusMeta(user_id=42, org_id="org-1", store_id=7),
    )
    await bus.emit(_p("invoice", tags=["kind:invoice"]))  # без другого тега → не матч
    await bus.drain()
    assert len(spy.got) == 1
    passport, meta = spy.got[0]
    assert passport.kind == "invoice"
    assert meta.user_id == 42 and meta.org_id == "org-1" and meta.store_id == 7


async def test_empty_pattern_is_wildcard():
    bus = InProcBus()
    spy = _Spy()
    bus.subscribe([], spy, name="all")
    await bus.emit(_p("note"))
    await bus.emit(_p("sms", tags=["kind:sms", "priority:high"]))
    await bus.drain()
    assert [p.kind for p, _ in spy.got] == ["note", "sms"]


async def test_pattern_normalized_case_and_blank():
    bus = InProcBus()
    spy = _Spy()
    bus.subscribe(["  Priority:HIGH ", ""], spy, name="norm")
    await bus.emit(_p("sms", tags=["kind:sms", "priority:high"]))
    await bus.drain()
    assert len(spy.got) == 1


# --- фан-аут та ізоляція ---

async def test_fanout_to_all_matching_subscribers():
    bus = InProcBus()
    a, b = _Spy(), _Spy()
    bus.subscribe(["kind:note"], a, name="a")
    bus.subscribe(["kind:note"], b, name="b")
    await bus.emit(_p("note"))
    await bus.drain()
    assert len(a.got) == 1 and len(b.got) == 1


async def test_subscriber_error_is_isolated():
    bus = InProcBus()

    async def boom(passport: Passport, meta: BusMeta) -> None:
        raise RuntimeError("впав")

    spy = _Spy()
    bus.subscribe(["kind:note"], boom, name="boom")
    bus.subscribe(["kind:note"], spy, name="ok")
    await bus.emit(_p("note"))  # не кидає (DoD SY-B1)
    await bus.drain()
    assert len(spy.got) == 1  # сусідній підписник не постраждав


async def test_unsubscribe_stops_delivery():
    bus = InProcBus()
    spy = _Spy()
    sub = bus.subscribe(["kind:note"], spy, name="tmp")
    await bus.emit(_p("note"))
    await bus.drain()
    sub.unsubscribe()
    sub.unsubscribe()  # ідемпотентно
    await bus.emit(_p("note"))
    await bus.drain()
    assert len(spy.got) == 1


# --- анти-петлі (SY-B1.4, guardrails §6) ---

async def test_own_source_is_skipped():
    bus = InProcBus()
    spy = _Spy()
    bus.subscribe([], spy, name="daily_builder")
    await bus.emit(_p("daily", source="daily_builder"))  # власна подія — петля
    await bus.emit(_p("daily", source="other"))
    await bus.drain()
    assert len(spy.got) == 1
    assert spy.got[0][0].source == "other"


async def test_hop_limit_stops_chain():
    bus = InProcBus(hop_limit=2)
    spy = _Spy()
    bus.subscribe([], spy, name="all")
    await bus.emit(_p(payload={BUS_HOP_KEY: 2}))  # глибина вичерпана
    await bus.drain()
    assert spy.got == []
    await bus.emit(_p(payload={BUS_HOP_KEY: 1}))  # ще в межах
    await bus.drain()
    assert len(spy.got) == 1


async def test_hop_helpers():
    assert hop_of(_p()) == 0
    assert hop_of(_p(payload={BUS_HOP_KEY: "сміття"})) == 0
    assert hop_of(_p(payload={BUS_HOP_KEY: -3})) == 0
    parent = _p(payload={BUS_HOP_KEY: 1})
    assert next_hop_payload(parent) == {BUS_HOP_KEY: 2}
    assert next_hop_payload(_p()) == {BUS_HOP_KEY: 1}


# --- конверт шини = паспорт (C1): from_store відновлює домен зі store-dict ---

async def test_passport_from_store_roundtrip():
    src = Passport(
        kind="invoice",
        summary="рахунок від acme",
        tags=["kind:invoice", "entity:acme"],
        sensitivity="finance",
        source="erp-sa",
        ref="doc:42",
        event_id="e-1",
        payload={"total": 100},
        subjects=["person:boss"],
        visibility="org",
        audience=["u1"],
        group_ref=5,
    )
    store = src.to_store()
    store["user_id"] = 42  # owner/org поза конвертом — from_store їх ігнорує
    store["org_id"] = "org-1"
    assert Passport.from_store(store) == src
