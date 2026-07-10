"""Тег-резолвер (P10 addressing) — тег стає хендлом виклику.

Друга роль тегів (DESIGN §1.2.1, C1): не лише індексація (`person:mom AND
topic:rent`), а й **адресація** — тег як хендл. `resolve(tag)` розв'язує тег у
`Handle`:

* `module:<name>` → :class:`ModuleRef` — адресний хендл на модуль/виконавця
  (`resolve("module:erp-sa")` повертає робочий референс; живий диспатч —
  SY-B3.2, реєстрація `kind:module`);
* будь-який інший тег (namespaced чи вільний) → :class:`ContextQuery` — чистий
  дескриптор ретриву (`person:mom` → «дай контекст про маму»).

Модуль **чистий** (P1/P3): без HTTP/DB/FS і без звернень до годинника — момент
`now` інжектиться явно у :meth:`ContextQuery.to_search`. Виконавець (memory
client) споживає `to_search()` і робить фактичний `/context/search`; резолвер
лише планує. Парсинг `:` — єдиний SSOT :func:`~jarvis_core.passport.tags.split_tag`,
не дублюємо (P7).

Закриває FEATURE_AUDIT P2-3 (tag-as-handle: раніше 0 резолверів, лише index-роль).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from .tags import split_tag

# Неймспейс, який адресує модуль/виконавця (а не запит ретриву).
MODULE_NAMESPACE = "module"


@dataclass(frozen=True)
class ModuleRef:
    """Адресний хендл на модуль/виконавця (`module:<name>`).

    `name` — канонічний (lowercase+trim) ідентифікатор, напр. `"scam-shield"`.
    Живий диспатч (`mcp_list`/виклик) — SY-B3.2; тут лише розв'язаний референс.
    """

    name: str


@dataclass(frozen=True)
class ContextQuery:
    """Чистий дескриптор ретриву паспортів (не виконує запит).

    `tags` — кортеж (frozen/hashable) required-тегів (AND-семантика ретриву,
    `tags @> $4`); `since_days` — вікно у днях або `None` (без обмеження).
    """

    tags: tuple[str, ...]
    since_days: int | None = None

    def __post_init__(self) -> None:
        # Fail-fast (P2): від'ємне вікно дало б `since` у майбутньому (порожній
        # результат) — не мовчазний нонсенс, а помилка на вході.
        if self.since_days is not None and self.since_days < 0:
            raise ValueError(f"since_days must be >= 0, got {self.since_days}")

    def to_search(self, now: datetime) -> dict[str, Any]:
        """Дескриптор → payload для memory `/context/search` (`tags`, `since`).

        `now` інжектиться явно (P3, чистота): `since` = `now - since_days` у
        tz-aware UTC ISO, або `None`. Форма збігається з `ContextSearchRequest`
        (`tags: list`, `since: str | None`). Наївний `now` трактуємо як UTC
        детерміновано (не читаємо годинник/таймзону ОС — інакше `since` дрейфує
        на локальний офсет, ламаючи чистоту P1/P3).
        """
        since: str | None = None
        if self.since_days is not None:
            aware = now if now.tzinfo is not None else now.replace(tzinfo=timezone.utc)
            since = (aware - timedelta(days=self.since_days)).astimezone(timezone.utc).isoformat()
        return {"tags": list(self.tags), "since": since}


# Тег розв'язується або в запит контексту, або в референс модуля.
Handle = ContextQuery | ModuleRef


def _require_tag(tag: str) -> str:
    """Fail-fast (P2): порожній тег — не адресовний хендл."""
    stripped = tag.strip()
    if not stripped:
        raise ValueError("tag is empty")
    return stripped


def resolve(tag: str) -> Handle:
    """Тег → `Handle`: `module:<name>` → :class:`ModuleRef`, решта → запит.

    `module:` з порожнім значенням — не диспатчабельний хендл → `ValueError`.
    Не гейтить на `KNOWN_NAMESPACES` (open/closed, P5): невідомий неймспейс —
    валідний тег ретриву. Нормалізація: увесь тег lowercase+trim, щоб `tags @> $4`
    матчив збережені (lowercased) теги — не покладаємось на `split_tag`, який
    lowercase-ить лише неймспейс, не значення.
    """
    stripped = _require_tag(tag)
    ns, val = split_tag(stripped)
    if ns == MODULE_NAMESPACE:
        # split_tag lowercase-ить лише неймспейс → значення доводимо до канону тут.
        name = val.lower()
        if not name:
            raise ValueError(f"module tag has no name: {tag!r}")
        return ModuleRef(name=name)
    return ContextQuery(tags=(stripped.lower(),))


def context_of(tag: str, days: int = 7) -> ContextQuery:
    """Зручність: «дай контекст про `tag` за останні `days` днів».

    Завжди повертає :class:`ContextQuery` (ретрив-намір) — навіть для `module:`
    тегу (контекст ПРО модуль), тому не диспатчить у :class:`ModuleRef`.
    Порожній тег → `ValueError` (як :func:`resolve`).
    """
    stripped = _require_tag(tag)
    return ContextQuery(tags=(stripped.lower(),), since_days=days)
