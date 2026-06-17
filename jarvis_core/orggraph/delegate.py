"""Delegate-as-actor (Стовп D / TEAM_ECOSYSTEM TC-4, §2.1, §4.2).

Делегат діє ВІД ІМЕНІ principal: для читання успадковує видимість principal (той
самий `RequestContext` → `can_read`), а для дій обмежений делегованими `scopes`
через S4-гейт. Чистий домен — зв'язує `orggraph.visibility` і `proactive.gate`.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..context import RequestContext
from ..proactive.gate import ProposedAction, requires_confirmation
from .graph import OrgGraph
from .visibility import VisibleResource, can_read


@dataclass(frozen=True)
class DelegateActor:
    """Актор-делегат: контекст principal (видимість) + делеговані scopes (дії)."""

    context: RequestContext
    scopes: frozenset[str]

    @property
    def principal_id(self) -> str:
        return self.context.user_id

    def can_read(self, res: VisibleResource, graph: OrgGraph) -> bool:
        """Читання — рівно видимість principal (делегат не бачить більше за нього)."""
        return can_read(self.context, res, graph)

    def can_act_without_confirm(self, action: ProposedAction) -> bool:
        """Чи може делегат виконати дію без ✅ principal (S4 + делеговані scopes)."""
        return not requires_confirmation(action, self.scopes)


def delegate_actor(
    *, org_id: str, principal_id: str, scopes: list[str] | None = None,
    role: str = "member", plan: str = "team",
) -> DelegateActor:
    """Будує актора-делегата для principal у межах org (acts AS principal)."""
    ctx = RequestContext(
        org_id=org_id,
        user_id=str(principal_id),
        role=role,
        plan=plan,
        legacy_uid=None,
        via="delegate",
    )
    return DelegateActor(context=ctx, scopes=frozenset(scopes or ["read:self"]))
