"""P1: резолв активного проєкту в агенті (scoped RAG + system prompt)."""
from __future__ import annotations

from typing import Any

import pytest

from app.agent import AgentRunner


class FakeMem:
    def __init__(self, project: dict[str, Any] | None = None) -> None:
        self.project = project
        self.searched_project_id: Any = "unset"

    async def search(self, user_id, query, top_k=5, project_id=None):  # noqa: ANN001
        self.searched_project_id = project_id
        return []

    async def store(self, user_id, content, role="user", project_id=None):  # noqa: ANN001
        return

    async def history(self, user_id, limit=12):  # noqa: ANN001
        return []

    async def get_project(self, user_id, project_id):  # noqa: ANN001
        return self.project


async def test_resolve_no_active(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _no_active(_uid):
        return None

    monkeypatch.setattr("app.projects.active_project_id", _no_active)
    pid, block = await AgentRunner(object(), FakeMem())._resolve_project(1)
    assert pid is None
    assert block == ""


async def test_resolve_active_injects_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _active(_uid):
        return 5

    monkeypatch.setattr("app.projects.active_project_id", _active)
    proj = {"id": 5, "name": "Робота", "system_prompt": "будь стислим"}
    pid, block = await AgentRunner(object(), FakeMem(proj))._resolve_project(1)
    assert pid == 5
    assert "Робота" in block
    assert "будь стислим" in block


async def test_resolve_missing_clears(monkeypatch: pytest.MonkeyPatch) -> None:
    cleared: dict[str, Any] = {}

    async def _active(_uid):
        return 9

    async def _set_active(uid, pid):
        cleared["call"] = (uid, pid)

    monkeypatch.setattr("app.projects.active_project_id", _active)
    monkeypatch.setattr("app.projects.set_active_project", _set_active)
    # get_project returns None → проєкт видалено/чужий → скидаємо активний.
    pid, block = await AgentRunner(object(), FakeMem(None))._resolve_project(7)
    assert pid is None
    assert block == ""
    assert cleared["call"] == (7, None)


async def test_memory_context_passes_project_id(monkeypatch: pytest.MonkeyPatch) -> None:
    mem = FakeMem()
    ctx, _prof = await AgentRunner(object(), mem)._memory_context(1, "привіт", project_id=5)
    assert mem.searched_project_id == 5
