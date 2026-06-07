"""Generic Platform → ToolsClient proxy helpers."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from .auth import PlatformAuth, require_platform_auth, resolve_uid

ToolsClientRef = Any
TBody = TypeVar("TBody", bound=BaseModel)
ToolsCallResult = Callable[[ToolsClientRef, PlatformAuth, TBody], Awaitable[dict[str, Any]]]


def _check_error(result: Any) -> None:
    if isinstance(result, dict) and result.get("error"):
        raise HTTPException(status_code=502, detail=str(result["error"]))


def register_tools_get(
    router: APIRouter,
    path: str,
    tools_attr: str,
    *,
    wrap_key: str | None = None,
) -> None:
    """GET /platform/api/... → await tools.<attr>()."""

    @router.get(path)
    async def _handler(
        request: Request,
        _auth: PlatformAuth = Depends(require_platform_auth),
    ) -> dict[str, Any]:
        fn = getattr(request.app.state.tools, tools_attr)
        result = await fn()
        if wrap_key:
            return {wrap_key: result}
        return result if isinstance(result, dict) else {"result": result}

    _handler.__name__ = f"proxy_get_{tools_attr}"


def register_tools_post_call(
    router: APIRouter,
    path: str,
    body_model: type[TBody],
    *,
    tools_attr: str,
    call: ToolsCallResult[TBody],
    required_field: str | None = None,
    check_error: bool = False,
) -> None:
    """POST з кастомним викликом tools (uid resolution у call)."""

    @router.post(path)
    async def _handler(
        request: Request,
        auth: PlatformAuth = Depends(require_platform_auth),
    ) -> dict[str, Any]:
        try:
            raw = await request.json()
        except Exception as exc:
            raise HTTPException(status_code=400, detail="invalid JSON body") from exc
        if not isinstance(raw, dict):
            raise HTTPException(status_code=400, detail="JSON object expected")
        try:
            body = body_model.model_validate(raw)
        except Exception as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if required_field:
            val = getattr(body, required_field, None)
            if val is None or (isinstance(val, str) and not str(val).strip()):
                raise HTTPException(status_code=400, detail=f"{required_field} required")
        result = await call(request.app.state.tools, auth, body)
        if check_error:
            _check_error(result)
        return result

    _handler.__name__ = f"proxy_post_{tools_attr}"


def register_tools_list(
    router: APIRouter,
    path: str,
    tools_attr: str,
    *,
    wrap_key: str,
) -> None:
    """GET з user_id/limit → await tools.<attr>(uid, limit)."""

    @router.get(path)
    async def _handler(
        request: Request,
        auth: PlatformAuth = Depends(require_platform_auth),
        user_id: int | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        uid = resolve_uid(auth, user_id)
        fn = getattr(request.app.state.tools, tools_attr)
        items = await fn(uid, limit)
        return {wrap_key: items, "user_id": uid}

    _handler.__name__ = f"proxy_list_{tools_attr}"


def register_tools_get_by_id(
    router: APIRouter,
    path: str,
    tools_attr: str,
    *,
    id_name: str,
    not_found: str,
) -> None:
    """GET /platform/api/.../{id} → tools.<attr>(id) або 404, якщо None.

    Узагальнює повторюваний патерн `jobs_get`/`plans_get`/`skills_get`/`teams_get`
    (отримати запис за id, 404 якщо відсутній). `id_name` — ім'я path-параметра
    (FastAPI сам резолвить його з `path` як `str` через `request.path_params`).
    """

    @router.get(path)
    async def _handler(
        request: Request,
        _auth: PlatformAuth = Depends(require_platform_auth),
    ) -> dict[str, Any]:
        item_id = request.path_params[id_name]
        fn = getattr(request.app.state.tools, tools_attr)
        rec = await fn(item_id)
        if rec is None:
            raise HTTPException(status_code=404, detail=not_found)
        return rec

    _handler.__name__ = f"proxy_get_by_id_{tools_attr}"


def register_tools_spawn(
    router: APIRouter,
    path: str,
    body_model: type[TBody],
    *,
    tools_attr: str,
    call: ToolsCallResult[TBody],
    required_field: str = "task",
    check_error: bool = True,
) -> None:
    """POST spawn/create — uid resolution, required field, optional 502 on error."""

    register_tools_post_call(
        router,
        path,
        body_model,
        tools_attr=tools_attr,
        call=call,
        required_field=required_field,
        check_error=check_error,
    )
