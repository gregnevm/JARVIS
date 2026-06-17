"""VisibilityPolicy — наскрізний шар доступу (TEAM_ECOSYSTEM §1.1, §4.2).

Ключовий зсув Стовпа D: `owner-scoped` → `policy-scoped`. Між store і consumer
з'являється політика, що відповідає «чи може актор A прочитати ресурс суб'єкта B?»
на основі org-ізоляції + рівня видимості + ребра графа + чутливості.

Owner-scoped (`private`) лишається ДЕФОЛТОМ — share це явний opt-in (S2: solo-user
нічого не ділить, нічого не змінюється). Чутливе (health/finance) ніколи не
видно нікому, крім власника й суб'єктів — навіть менеджеру (§4.2, privacy §8.1).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..context import RequestContext
from .graph import OrgGraph
from .models import normalize_visibility

# Рівні, що ніколи не виходять за межі власника/суб'єктів незалежно від visibility.
_SENSITIVE = frozenset({"health", "finance"})


@dataclass(frozen=True)
class VisibleResource:
    """Мінімальна ACL-проєкція ресурсу (паспорта) для політики видимості.

    Storage-шар наповнює її з запису; домен не залежить від форми зберігання.
    """

    org_id: str
    owner_uid: str
    visibility: str = "private"
    sensitivity: str = "personal"
    subjects: list[str] = field(default_factory=list)
    audience: list[str] = field(default_factory=list)

    @classmethod
    def from_record(cls, rec: dict[str, object], *, org_id: str, owner_uid: str) -> "VisibleResource":
        """Проєкція збереженого паспорт-запису в ACL-вид (storage → політика).

        `org_id`/`owner_uid` приходять із tenant-метаданих запису (не з домену
        Passport, який їх не несе); решта — з полів §4.1.
        """
        def _strs(v: object) -> list[str]:
            return [str(x) for x in v] if isinstance(v, (list, tuple)) else []

        return cls(
            org_id=org_id,
            owner_uid=owner_uid,
            visibility=str(rec.get("visibility") or "private"),
            sensitivity=str(rec.get("sensitivity") or "personal"),
            subjects=_strs(rec.get("subjects")),
            audience=_strs(rec.get("audience")),
        )


def can_read(actor: RequestContext, res: VisibleResource, graph: OrgGraph) -> bool:
    """Чи може `actor` прочитати ресурс `res` у межах графа `graph`.

    Делегат успадковує видимість principal: викличний шар передає `actor` з
    `user_id` principal (+ scope-розширення вирішується вище). Тут — чиста політика.
    """
    if res.org_id != actor.org_id:
        return False  # tenant-ізоляція (SAAS §4.0) — груба межа
    owner = res.owner_uid
    allowed_sensitive = {owner, *res.subjects}
    if res.sensitivity in _SENSITIVE and actor.user_id not in allowed_sensitive:
        return False  # чутливе — лише власник/суб'єкт, навіть для менеджера
    vis = normalize_visibility(res.visibility)
    if actor.user_id == owner:
        return True
    if vis == "private":
        return False
    if vis == "org":
        return True
    if vis == "squad":
        return graph.share_squad(actor.user_id, owner) or graph.manages_transitively(
            actor.user_id, owner
        )
    if vis == "custom":
        if actor.user_id in res.audience:
            return True
        # audience може містити squad_id — член будь-якого з них теж бачить
        actor_squads = graph.squads_of(actor.user_id)
        return bool(actor_squads & set(res.audience))
    return False
