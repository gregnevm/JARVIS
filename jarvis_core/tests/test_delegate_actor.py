"""TEAM_ECOSYSTEM TC-4 — delegate-as-actor (видимість principal + scope-гейт дій)."""
from __future__ import annotations

from jarvis_core.orggraph import (
    OrgGraph,
    Relationship,
    Squad,
    SquadMember,
    VisibleResource,
    delegate_actor,
)
from jarvis_core.proactive import ProposedAction

ORG = "org-A"


def _graph() -> OrgGraph:
    return OrgGraph(
        ORG,
        [Squad(id="backend", org_id=ORG, name="Backend")],
        [SquadMember("backend", "A"), SquadMember("backend", "B")],
        [Relationship(ORG, "A", "M", "reports_to")],
    )


def test_delegate_inherits_principal_visibility() -> None:
    g = _graph()
    d = delegate_actor(org_id=ORG, principal_id="A", scopes=["read:team_context"])
    # squad-ресурс колеги B видно делегату A (бо A у тому ж squad)
    res = VisibleResource(org_id=ORG, owner_uid="B", visibility="squad")
    assert d.can_read(res, g) is True


def test_delegate_does_not_exceed_principal() -> None:
    g = _graph()
    d = delegate_actor(org_id=ORG, principal_id="A", scopes=["read:team_context"])
    # приватний ресурс іншого користувача S — делегату A не видно
    res = VisibleResource(org_id=ORG, owner_uid="S", visibility="private")
    assert d.can_read(res, g) is False


def test_delegate_health_blocked_even_for_manager_delegate() -> None:
    g = _graph()
    d = delegate_actor(org_id=ORG, principal_id="M", scopes=["read:team_context"])
    res = VisibleResource(org_id=ORG, owner_uid="A", visibility="squad", sensitivity="health")
    assert d.can_read(res, g) is False  # чутливе — навіть менеджерському делегату ні


def test_delegate_scope_gates_actions() -> None:
    d = delegate_actor(org_id=ORG, principal_id="A", scopes=["read:self", "act:auto"])
    # мутуюча локальна дія — дозволена scope act:auto
    assert d.can_act_without_confirm(ProposedAction(kind="update", summary="x", mutating=True)) is True
    # зовнішня — завжди confirm, scope не рятує
    assert d.can_act_without_confirm(ProposedAction(kind="send", summary="y", external=True)) is False


def test_delegate_without_act_scope_needs_confirm() -> None:
    d = delegate_actor(org_id=ORG, principal_id="A")  # дефолт read:self
    assert d.can_act_without_confirm(ProposedAction(kind="update", summary="x", mutating=True)) is False
    assert d.principal_id == "A"
