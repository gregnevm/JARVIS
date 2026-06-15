"""Basic toolkit endpoints: calc, web_fetch, search, parse_file, code_exec, dispatch."""
from __future__ import annotations

from fastapi import APIRouter

from .. import toolkit
from ..schemas import (
    CalcRequest,
    CodeRequest,
    FetchRequest,
    ParseRequest,
    SearchRequest,
    ToolDispatchRequest,
)


def register(router: APIRouter) -> None:
    @router.post("/tool/dispatch")
    async def tool_dispatch_ep(req: ToolDispatchRequest) -> dict[str, str]:
        text = await toolkit.dispatch(
            req.name.strip(),
            req.arguments,
            req.user_id,
            allow_computer=req.allow_computer,
        )
        return {"text": text}

    @router.post("/calc")
    async def calc_ep(req: CalcRequest) -> dict[str, str]:
        return {"result": toolkit.calc(req.expression)}

    @router.post("/web_fetch")
    async def web_fetch_ep(req: FetchRequest) -> dict[str, str]:
        return {"text": await toolkit.web_fetch(req.url)}

    @router.post("/search")
    async def search_ep(req: SearchRequest) -> dict[str, str]:
        return {"text": await toolkit.web_search(req.query, req.max_results)}

    @router.post("/parse_file")
    async def parse_file_ep(req: ParseRequest) -> dict[str, str]:
        return {"text": toolkit.parse_file(req.path)}

    @router.post("/code_exec")
    async def code_exec_ep(req: CodeRequest) -> dict[str, str]:
        return {"result": toolkit.code_exec(req.code)}
