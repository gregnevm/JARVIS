"""CA-6.5 Platform Coding tab — repo-tree, diff-viewer (review), test-panel (fix job).

Тонкий проксі до ToolsClient: план (file-targeted), self-review diff, repo-tree та
запуск coding_task (fix-петля) як background job. Мутації коду — лише через bg job
(headless-гейт CODING_HEADLESS_APPLY на tools-боці), не з UI напряму.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from .auth import PlatformAuth, resolve_uid
from .proxy import register_tools_post_call


class CodePlanBody(BaseModel):
    text: str
    user_id: int | None = None


class CodeReviewBody(BaseModel):
    diff: str
    context: str = ""
    user_id: int | None = None


class RepoTreeBody(BaseModel):
    path: str = ""
    max_depth: int = 3
    user_id: int | None = None


class CodingFixBody(BaseModel):
    exe: str
    args: list[str] | None = None
    path: str = ""
    task: str = ""
    max_rounds: int = 0
    user_id: int | None = None


async def _plan(tools: Any, auth: PlatformAuth, body: CodePlanBody) -> dict[str, Any]:
    return await tools.code_plan(resolve_uid(auth, body.user_id), body.text)


async def _review(tools: Any, auth: PlatformAuth, body: CodeReviewBody) -> dict[str, Any]:
    return await tools.code_review(resolve_uid(auth, body.user_id), body.diff, body.context)


async def _tree(tools: Any, auth: PlatformAuth, body: RepoTreeBody) -> dict[str, Any]:
    return await tools.repo_tree(resolve_uid(auth, body.user_id), body.path, body.max_depth)


async def _fix(tools: Any, auth: PlatformAuth, body: CodingFixBody) -> dict[str, Any]:
    return await tools.create_coding_job(
        resolve_uid(auth, body.user_id),
        body.exe,
        args=body.args,
        path=body.path,
        task=body.task,
        max_rounds=body.max_rounds,
    )


def register(router: APIRouter) -> None:
    register_tools_post_call(
        router, "/platform/api/coding/plan", CodePlanBody,
        tools_attr="code_plan", call=_plan, required_field="text", check_error=True,
    )
    register_tools_post_call(
        router, "/platform/api/coding/review", CodeReviewBody,
        tools_attr="code_review", call=_review, required_field="diff", check_error=True,
    )
    register_tools_post_call(
        router, "/platform/api/coding/tree", RepoTreeBody,
        tools_attr="repo_tree", call=_tree, check_error=True,
    )
    register_tools_post_call(
        router, "/platform/api/coding/fix", CodingFixBody,
        tools_attr="create_coding_job", call=_fix, required_field="exe", check_error=True,
    )
