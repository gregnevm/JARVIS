"""Tag-таксономія (P10) — namespaced-теги для індексації ТА адресації.

Дві ролі (DESIGN §1.2.1): (1) індексація/ретрив (`person:mom AND topic:rent`),
(2) адресація — тег як хендл виклику блоку (`module:scam-shield`). Контрольований
словник префіксів; вільні теги дозволені, але префіксовані пріоритетні.
"""
from __future__ import annotations

# Канонічні namespace-префікси (для довідки/валідації; не замикаємо — open/closed).
# Тегова гігієна (SYNERGY_ROADMAP §6): новий неймспейс = рядок тут (+ докстрінг у PR),
# інакше адресний простір деградує. SY-1: tool:/reason: (friction-телеметрія),
# priority: (шина SY-B1: підписка push на priority:high). SY-5: tier: (ярус S5 у
# confirm-паспортах), status: (фіксація де-факто вжитку — proposals `status:offered`,
# kaizen `status:done`, рішення `status:approved|cancelled`). capability: — SY-B3.3.
KNOWN_NAMESPACES = frozenset(
    {
        "kind", "topic", "person", "entity", "source", "pillar", "module",
        "sensitivity", "lang", "tool", "reason", "priority", "tier", "status",
    }
)

_MAX_TAGS = 64
_MAX_TAG_LEN = 80


def split_tag(tag: str) -> tuple[str | None, str]:
    """`'person:mom'` → `('person','mom')`; `'urgent'` → `(None,'urgent')`."""
    t = tag.strip()
    if ":" in t:
        ns, _, val = t.partition(":")
        return ns.strip().lower() or None, val.strip()
    return None, t


def is_namespaced(tag: str) -> bool:
    return split_tag(tag)[0] is not None


def normalize_tags(tags: list[str] | None, kind: str) -> list[str]:
    """P10: lowercase + trim + дедуп (порядок збережено), гарантований `kind:<kind>` першим.

    Інваріант C1: жоден паспорт без `kind`-тега. Стеля `_MAX_TAGS` (анти-роздування).
    Спільна реалізація для memory/gateway/agent — один SSOT (P7), без дублю.
    """
    out: list[str] = []
    seen: set[str] = set()
    for raw in tags or []:
        t = str(raw).strip().lower()[:_MAX_TAG_LEN]
        if not t or t in seen:
            continue
        seen.add(t)
        out.append(t)
    kind_tag = f"kind:{(kind or '').strip().lower()}"
    if kind_tag not in seen:
        out.insert(0, kind_tag)
    return out[:_MAX_TAGS]


def tags_contain(tags: list[str], required: list[str]) -> bool:
    """Containment: усі `required` присутні в `tags` (AND-семантика ретриву)."""
    have = set(tags)
    return all(r.strip().lower() in have for r in required)
