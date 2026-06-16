"""Coding-agent helper endpoints: /coding/* — repo intelligence для Platform Coding tab (CA-6.5).

Тонкі HTTP-обгортки навколо read-only coding-інструментів (`coding_tools`), щоб
Platform SPA міг показати repo-tree без прямого доступу до host-agent. Мутацій тут немає —
правки йдуть через agent-флоу (`/agent/code/*`) і bg coding_task.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from ..schemas import RepoTreeRequest


def register(router: APIRouter) -> None:
    @router.post("/coding/repo_tree")
    async def coding_repo_tree(req: RepoTreeRequest) -> dict[str, Any]:
        """Дерево файлів репо (gitignore-aware). Вимкнено/недоступно → текст у `tree`."""
        from ..tools import coding_tools

        text = await coding_tools.repo_tree(
            req.path, max_depth=req.max_depth, user_id=req.user_id
        )
        return {"tree": text, "path": req.path}
