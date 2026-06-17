"""Platform Autopilot tab — OKR-керована авто-корутина (status / tick / OKR / dashboard).

Тонкий UI поверх `app.auto_coroutine`: читає/мутує OKR, рендерить дашборд, і за
запитом адміна крутить один цикл вручну (`/tick`) тим самим прод-диспатчем, що й
фоновий loop. Реальні мутації коду гейтяться tools-політикою `CODING_HEADLESS_APPLY`.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from ..auto_coroutine import (
    load_okr,
    make_tools_dispatch,
    render_dashboard,
    run_cycle,
    save_dashboard,
    save_okr,
)
from ..config import settings
from jarvis_core.okr import mutate_okr, okr_to_dict
from .auth import PlatformAuth, require_platform_auth, resolve_uid


class OkrMutateBody(BaseModel):
    admin_context: str | None = None
    kr_deltas: dict[str, float] | None = None


class TickBody(BaseModel):
    user_id: int | None = None


def _state(data_dir: str) -> dict[str, Any]:
    okr = load_okr(data_dir)
    return {
        "enabled": settings.auto_coroutine_enabled,
        "interval": settings.auto_coroutine_interval,
        "okr": okr_to_dict(okr),
    }


def register(router: APIRouter) -> None:
    @router.get("/platform/api/autopilot/status")
    async def autopilot_status(
        _auth: PlatformAuth = Depends(require_platform_auth),
    ) -> dict[str, Any]:
        return _state(settings.data_dir)

    @router.get("/platform/api/autopilot/dashboard")
    async def autopilot_dashboard(
        _auth: PlatformAuth = Depends(require_platform_auth),
    ) -> dict[str, Any]:
        okr = load_okr(settings.data_dir)
        return {"markdown": render_dashboard(okr, [])}

    @router.post("/platform/api/autopilot/okr")
    async def autopilot_okr_mutate(
        body: OkrMutateBody,
        _auth: PlatformAuth = Depends(require_platform_auth),
    ) -> dict[str, Any]:
        okr = mutate_okr(
            load_okr(settings.data_dir),
            admin_context=body.admin_context,
            kr_deltas=body.kr_deltas,
        )
        save_okr(settings.data_dir, okr)
        save_dashboard(settings.data_dir, okr, [])
        return {"okr": okr_to_dict(okr)}

    @router.post("/platform/api/autopilot/tick")
    async def autopilot_tick(
        request: Request,
        body: TickBody,
        auth: PlatformAuth = Depends(require_platform_auth),
    ) -> dict[str, Any]:
        uid = resolve_uid(auth, body.user_id)
        dispatch = make_tools_dispatch(request.app.state.tools)
        okr = load_okr(settings.data_dir)
        new_okr, result = await run_cycle(
            okr, dispatch, user_id=uid, repo_path=settings.data_dir
        )
        if result is None:
            return {"ran": False, "reason": "no actionable objectives"}
        save_okr(settings.data_dir, new_okr)
        save_dashboard(settings.data_dir, new_okr, [result])
        return {
            "ran": True,
            "objective": result.objective_id,
            "ok": result.ok_count,
            "stages": [{"stage": s, "ok": ok, "summary": m} for s, ok, m in result.stages],
            "okr": okr_to_dict(new_okr),
        }
