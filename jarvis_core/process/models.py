"""Доменні моделі бізнес-процесу (TEAM_ECOSYSTEM §6.1).

`ProcessStep` мутабельний (статус змінюється рушієм), `Process` — контейнер.
Серіалізація у Redis/Postgres — викличним шаром (`to_dict`/`from_dict`).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Тип кроку — визначає, КОМУ й ЯК диспетчити (рушій лише класифікує).
STEP_KINDS = frozenset({"human_task", "delegate_task", "approval", "notify", "wait_event"})
STEP_STATUSES = frozenset({"pending", "active", "blocked", "done", "skipped"})
PROCESS_STATUSES = frozenset({"draft", "running", "paused", "done", "cancelled"})


@dataclass
class ProcessStep:
    id: str
    title: str
    assignee_user_id: str
    kind: str = "human_task"
    status: str = "pending"
    due: str | None = None
    depends_on: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "assignee_user_id": self.assignee_user_id,
            "kind": self.kind,
            "status": self.status,
            "due": self.due,
            "depends_on": list(self.depends_on),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ProcessStep":
        return cls(
            id=str(d["id"]),
            title=str(d.get("title") or ""),
            assignee_user_id=str(d.get("assignee_user_id") or ""),
            kind=str(d.get("kind") or "human_task"),
            status=str(d.get("status") or "pending"),
            due=d.get("due"),
            depends_on=[str(x) for x in (d.get("depends_on") or [])],
        )


@dataclass
class Process:
    id: str
    org_id: str
    owner_user_id: str
    title: str
    steps: list[ProcessStep] = field(default_factory=list)
    squad_id: str | None = None
    template: str | None = None
    status: str = "draft"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "org_id": self.org_id,
            "owner_user_id": self.owner_user_id,
            "title": self.title,
            "squad_id": self.squad_id,
            "template": self.template,
            "status": self.status,
            "steps": [s.to_dict() for s in self.steps],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Process":
        return cls(
            id=str(d["id"]),
            org_id=str(d.get("org_id") or ""),
            owner_user_id=str(d.get("owner_user_id") or ""),
            title=str(d.get("title") or ""),
            squad_id=d.get("squad_id"),
            template=d.get("template"),
            status=str(d.get("status") or "draft"),
            steps=[ProcessStep.from_dict(s) for s in (d.get("steps") or [])],
        )
