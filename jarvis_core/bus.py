"""PassportBus (SY-B1) — Observer поверх паспортів: підписка = tag-containment.

Порт + in-proc адаптер (SYNERGY_ROADMAP §3). Шина НЕ має власної схеми повідомлень:
подія = `Passport` (C1 — конверт уже канонізований). Emit відбувається ПІСЛЯ store,
тож durable log шини = `context_events`, а replay пропущеного = звичайний ContextQuery.

Підписка говорить мовою ретриву: pattern = список тегів, матч = containment
(та сама AND-семантика, що GIN `tags @> pattern` у memory). Порожній pattern —
wildcard (отримує все). «Що сталося» і «що я знаю» — один механізм (§1.1).

Захист від петель — обов'язковий із B1 (guardrails треку §6):
  * source-фільтр: підписник із `name=X` не отримує паспортів із `source=X`
    (не реагуй на власні події);
  * hop-limit: похідний паспорт, породжений у реакції на подію шини, МУСИТЬ нести
    `payload["bus_hop"] = hop батька + 1` (хелпер `next_hop_payload`); доставка
    зупиняється при hop >= hop_limit.

Доставка fire-and-forget: збій одного підписника ізольований (лог) і не валить
ні emit, ні інших підписників (DoD SY-B1). Крос-сервісний транспорт — RedisBus
(SY-B2); Edge лишається на InProcBus (P1 offline-first).
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Protocol

from .passport import Passport
from .passport.tags import tags_contain

logger = logging.getLogger("jarvis.core.bus")

# Ключ у Passport.payload, яким реактивні продюсери передають глибину ланцюга.
BUS_HOP_KEY = "bus_hop"
DEFAULT_HOP_LIMIT = 4

Handler = Callable[[Passport, "BusMeta"], Awaitable[None]]


@dataclass(frozen=True)
class BusMeta:
    """Контекст доставки поза конвертом: партиція (user/org) і id рядка в сторі.

    Паспорт свідомо не несе owner/org (див. `Passport.to_store`) — підписникам,
    яким треба скоуп (push per-user, org-префікси RedisBus у SY-B2), його дає meta.
    """

    user_id: int | None = None
    org_id: str | None = None
    store_id: int | None = None


def hop_of(passport: Passport) -> int:
    """Глибина ланцюга подій цього паспорта (0 = первинна подія, не з шини)."""
    try:
        return max(0, int(passport.payload.get(BUS_HOP_KEY, 0)))
    except (TypeError, ValueError):
        return 0


def next_hop_payload(parent: Passport) -> dict[str, Any]:
    """Стартовий payload для ПОХІДНОГО паспорта: hop батька + 1 (анти-петля).

    Реактивний підписник, який у відповідь на подію інжестить нові паспорти,
    зобов'язаний мерджити цей dict у їхній payload — інакше hop-limit не працює.
    """
    return {BUS_HOP_KEY: hop_of(parent) + 1}


class Subscription:
    """Активна підписка. `unsubscribe()` знімає її з шини (ідемпотентно)."""

    __slots__ = ("pattern", "handler", "name", "_bus")

    def __init__(
        self, pattern: list[str], handler: Handler, name: str, bus: "InProcBus"
    ) -> None:
        self.pattern = pattern
        self.handler = handler
        self.name = name
        self._bus = bus

    def unsubscribe(self) -> None:
        self._bus._remove(self)


class PassportBus(Protocol):
    """Порт шини (SY-B1.1). Адаптери: InProcBus (тут), RedisBus (SY-B2)."""

    def subscribe(
        self, pattern: list[str], handler: Handler, *, name: str = ""
    ) -> Subscription: ...

    async def emit(self, passport: Passport, meta: BusMeta | None = None) -> None:
        """Fire-and-forget: помилка підписника не валить emit (і не видима йому)."""
        ...


class InProcBus:
    """In-proc адаптер порту (один процес). P1: Edge/тести працюють без Redis."""

    def __init__(self, *, hop_limit: int = DEFAULT_HOP_LIMIT) -> None:
        self._subs: list[Subscription] = []
        self._tasks: set[asyncio.Task[None]] = set()
        self._hop_limit = hop_limit

    def subscribe(
        self, pattern: list[str], handler: Handler, *, name: str = ""
    ) -> Subscription:
        normalized = [t.strip().lower() for t in pattern if t.strip()]
        sub = Subscription(normalized, handler, name.strip(), self)
        self._subs.append(sub)
        return sub

    def _remove(self, sub: Subscription) -> None:
        try:
            self._subs.remove(sub)
        except ValueError:
            pass  # уже знята — unsubscribe ідемпотентний

    async def emit(self, passport: Passport, meta: BusMeta | None = None) -> None:
        """Матчить підписки і ставить доставки окремими task-ами. Не кидає."""
        meta = meta or BusMeta()
        hop = hop_of(passport)
        if hop >= self._hop_limit:
            logger.warning(
                "bus: hop-limit %s досягнуто (kind=%s source=%s) — ланцюг зупинено",
                self._hop_limit, passport.kind, passport.source,
            )
            return
        for sub in list(self._subs):
            # Петля: не реагуй на власний source (підписник ≠ споживач самого себе).
            if sub.name and passport.source == sub.name:
                continue
            if not tags_contain(passport.tags, sub.pattern):
                continue
            task = asyncio.create_task(self._deliver(sub, passport, meta))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

    async def _deliver(self, sub: Subscription, passport: Passport, meta: BusMeta) -> None:
        try:
            await sub.handler(passport, meta)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 — ізоляція збоїв підписника (DoD SY-B1)
            logger.exception(
                "bus: підписник %r впав на kind=%s — ізольовано", sub.name, passport.kind
            )

    async def drain(self) -> None:
        """Дочекатися всіх уже запланованих доставок (тести, graceful shutdown)."""
        while self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)
