"""TEAM_ECOSYSTEM TC-0/TC-1 — OrgGraph + VisibilityPolicy (чистий домен)."""
from __future__ import annotations

from dataclasses import replace

from jarvis_core.context import RequestContext
from jarvis_core.orggraph import (
    OrgGraph,
    Relationship,
    Squad,
    SquadMember,
    VisibleResource,
    can_read,
)

ORG = "org-A"
OTHER = "org-B"


def _ctx(uid: str, org: str = ORG, role: str = "member") -> RequestContext:
    return RequestContext(org_id=org, user_id=uid, role=role, plan="team", legacy_uid=None, via="test")


def _graph() -> OrgGraph:
    # eng (root) ── backend (child)
    #   manager M reports nobody; A,B in backend; A reports_to M
    squads = [
        Squad(id="eng", org_id=ORG, name="Engineering", kind="department"),
        Squad(id="backend", org_id=ORG, name="Backend", parent_id="eng", kind="team"),
        Squad(id="sales", org_id=ORG, name="Sales", kind="department"),
    ]
    members = [
        SquadMember("backend", "A"),
        SquadMember("backend", "B"),
        SquadMember("eng", "M"),
        SquadMember("sales", "S"),
    ]
    rels = [
        Relationship(ORG, "A", "M", "reports_to"),
        Relationship(ORG, "B", "M", "reports_to"),
        Relationship(ORG, "M", "A", "manages"),
    ]
    return OrgGraph(ORG, squads, members, rels)


# --- graph ----------------------------------------------------------------

def test_squad_hierarchy() -> None:
    g = _graph()
    assert g.squad_ancestors("backend") == ["eng"]
    assert "backend" in g.squad_descendants("eng")
    assert g.squad_descendants("backend") == []


def test_share_squad() -> None:
    g = _graph()
    assert g.share_squad("A", "B") is True   # обидва в backend
    assert g.share_squad("A", "S") is False  # різні squad
    assert g.share_squad("A", "A") is True


def test_manager_chain_and_transitive() -> None:
    g = _graph()
    assert g.manager_chain("A") == ["M"]
    assert g.manages_transitively("M", "A") is True
    assert g.manages_transitively("A", "M") is False


def test_neighbors_directional() -> None:
    g = _graph()
    assert g.neighbors("M", "manages") == {"A"}
    assert g.inbound("M", "reports_to") == {"A", "B"}


def test_cross_org_isolation() -> None:
    # ребро/squad іншого org ігнорується при побудові графа org-A
    g = OrgGraph(
        ORG,
        [Squad(id="x", org_id=OTHER, name="X")],
        [SquadMember("x", "Z")],
        [Relationship(OTHER, "Z", "M", "reports_to")],
    )
    assert g.squads_of("Z") == set()
    assert g.neighbors("Z", "reports_to") == set()


# --- visibility ------------------------------------------------------------

def _res(**kw: object) -> VisibleResource:
    base = dict(org_id=ORG, owner_uid="A", visibility="private", sensitivity="personal")
    base.update(kw)
    return VisibleResource(**base)  # type: ignore[arg-type]


def test_private_blocks_peer() -> None:
    g = _graph()
    assert can_read(_ctx("A"), _res(), g) is True       # власник
    assert can_read(_ctx("B"), _res(), g) is False      # приватне — не видно колезі


def test_squad_visibility_shares_within_squad() -> None:
    g = _graph()
    r = _res(visibility="squad")
    assert can_read(_ctx("B"), r, g) is True   # B у тому ж backend
    assert can_read(_ctx("S"), r, g) is False  # S у sales — не бачить


def test_manager_sees_squad_via_reports_chain() -> None:
    g = _graph()
    r = _res(owner_uid="A", visibility="squad")
    assert can_read(_ctx("M"), r, g) is True   # M керує A транзитивно


def test_manager_never_sees_health() -> None:
    g = _graph()
    r = _res(owner_uid="A", visibility="squad", sensitivity="health")
    assert can_read(_ctx("M"), r, g) is False  # чутливе — навіть менеджеру ні
    assert can_read(_ctx("A"), r, g) is True   # власнику — так


def test_health_visible_to_subject() -> None:
    g = _graph()
    r = _res(owner_uid="A", visibility="squad", sensitivity="finance", subjects=["B"])
    assert can_read(_ctx("B"), r, g) is True   # B — суб'єкт


def test_org_visibility() -> None:
    g = _graph()
    assert can_read(_ctx("S"), _res(visibility="org"), g) is True


def test_custom_audience_user_and_squad() -> None:
    g = _graph()
    assert can_read(_ctx("S"), _res(visibility="custom", audience=["S"]), g) is True
    assert can_read(_ctx("B"), _res(visibility="custom", audience=["backend"]), g) is True
    assert can_read(_ctx("S"), _res(visibility="custom", audience=["backend"]), g) is False


def test_cross_org_resource_blocked() -> None:
    g = _graph()
    assert can_read(_ctx("A", org=OTHER), _res(visibility="org"), g) is False


def test_visibility_normalizes_unknown() -> None:
    g = _graph()
    r = replace(_res(), visibility="garbage")
    assert can_read(_ctx("B"), r, g) is False  # невідоме → private


def test_from_record_projection() -> None:
    rec = {"visibility": "squad", "sensitivity": "health", "subjects": ["B", 7], "audience": ["x"]}
    res = VisibleResource.from_record(rec, org_id=ORG, owner_uid="A")
    assert res.org_id == ORG and res.owner_uid == "A"
    assert res.visibility == "squad" and res.sensitivity == "health"
    assert res.subjects == ["B", "7"] and res.audience == ["x"]


def test_from_record_defaults() -> None:
    res = VisibleResource.from_record({}, org_id=ORG, owner_uid="A")
    assert res.visibility == "private" and res.sensitivity == "personal"
    assert res.subjects == [] and res.audience == []
