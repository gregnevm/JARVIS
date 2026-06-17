"""OrgGraph — зібраний граф зв'язків організації (TEAM_ECOSYSTEM §3.2).

Будується з трьох наборів (`squads`, `squad_members`, `relationships`) одного org.
Чистий домен — жодного I/O; кешування (Redis `jarvis:{org_id}:orggraph`) робить
викличний шар. Усі запити обмежені одним `org_id` (анти-IDOR крос-org за дизайном).
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

from .models import Relationship, Squad, SquadMember


class OrgGraph:
    """Незмінний знімок графа одного org для швидких реляційних запитів."""

    def __init__(
        self,
        org_id: str,
        squads: Iterable[Squad] = (),
        members: Iterable[SquadMember] = (),
        relationships: Iterable[Relationship] = (),
    ) -> None:
        self.org_id = org_id
        self._squads: dict[str, Squad] = {s.id: s for s in squads if s.org_id == org_id}
        # squad_id → set(user_id) і user_id → set(squad_id)
        self._squad_users: dict[str, set[str]] = defaultdict(set)
        self._user_squads: dict[str, set[str]] = defaultdict(set)
        for m in members:
            if m.squad_id in self._squads:
                self._squad_users[m.squad_id].add(m.user_id)
                self._user_squads[m.user_id].add(m.squad_id)
        # ребра графа: (src, kind) → set(dst)
        self._edges: dict[tuple[str, str], set[str]] = defaultdict(set)
        self._rev_edges: dict[tuple[str, str], set[str]] = defaultdict(set)
        for r in relationships:
            if r.org_id != org_id:
                continue
            self._edges[(r.src_user_id, r.kind)].add(r.dst_user_id)
            self._rev_edges[(r.dst_user_id, r.kind)].add(r.src_user_id)

    # --- squad-ієрархія ------------------------------------------------------

    def squad_ancestors(self, squad_id: str) -> list[str]:
        """Шлях угору по parent_id (виключно сам вузол), від найближчого предка."""
        out: list[str] = []
        seen: set[str] = {squad_id}
        node = self._squads.get(squad_id)
        while node and node.parent_id and node.parent_id not in seen:
            out.append(node.parent_id)
            seen.add(node.parent_id)
            node = self._squads.get(node.parent_id)
        return out

    def squad_descendants(self, squad_id: str) -> list[str]:
        """Усі нащадки в піддереві (BFS), виключно сам вузол."""
        children: dict[str, list[str]] = defaultdict(list)
        for s in self._squads.values():
            if s.parent_id:
                children[s.parent_id].append(s.id)
        out: list[str] = []
        queue = list(children.get(squad_id, []))
        seen: set[str] = set()
        while queue:
            cur = queue.pop(0)
            if cur in seen:
                continue
            seen.add(cur)
            out.append(cur)
            queue.extend(children.get(cur, []))
        return out

    def squads_of(self, user_id: str) -> set[str]:
        return set(self._user_squads.get(user_id, set()))

    def members_of(self, squad_id: str) -> set[str]:
        return set(self._squad_users.get(squad_id, set()))

    def share_squad(self, a: str, b: str) -> bool:
        """Чи входять двоє в один і той самий squad (пряме спільне членство)."""
        if a == b:
            return True
        return bool(self._user_squads.get(a, set()) & self._user_squads.get(b, set()))

    # --- ребра графа ---------------------------------------------------------

    def neighbors(self, user_id: str, kind: str) -> set[str]:
        """dst-вузли вихідних ребер заданого типу (напр. кого user `manages`)."""
        return set(self._edges.get((user_id, kind), set()))

    def inbound(self, user_id: str, kind: str) -> set[str]:
        """src-вузли вхідних ребер заданого типу (напр. хто `reports_to` user)."""
        return set(self._rev_edges.get((user_id, kind), set()))

    def manager_chain(self, user_id: str) -> list[str]:
        """Ланцюг керівників угору по `reports_to` (від прямого менеджера)."""
        out: list[str] = []
        seen: set[str] = {user_id}
        cur = user_id
        while True:
            mgrs = self._edges.get((cur, "reports_to"), set()) - seen
            if not mgrs:
                break
            nxt = sorted(mgrs)[0]  # детермінізм за множинного reports_to
            out.append(nxt)
            seen.add(nxt)
            cur = nxt
        return out

    def manages_transitively(self, manager: str, target: str) -> bool:
        """Чи є `manager` десь у ланцюгу керівників `target` (вгору по reports_to)."""
        return manager in set(self.manager_chain(target))
