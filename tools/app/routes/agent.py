"""Agent endpoints: /agent, /agent/stream, /agent/plan*."""
from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from jarvis_core.pipeline.handlers import screen_text

from ..schemas import (
    AgentRequest,
    CodeFixRequest,
    CodeReviewRequest,
    PlanCreateRequest,
    PlanUserRequest,
)
from ._helpers import ndjson, require_found, require_text

logger = logging.getLogger("jarvis.tools.agent_routes")


def register(router: APIRouter) -> None:
    @router.post("/agent")
    async def agent_ep(req: AgentRequest, request: Request) -> dict[str, Any]:
        try:
            return await request.app.state.jarvis.chat(req.user_id, req.text, mode=req.mode)
        except Exception:  # noqa: BLE001
            logger.exception("agent run failed")
            return {
                "text": "Локальна модель зараз недоступна. Перевір, чи піднятий Ollama на хості.",
                "mode": "error",
                "iters": 0,
            }

    @router.post("/agent/stream")
    async def agent_stream_ep(req: AgentRequest, request: Request) -> StreamingResponse:
        safe, block = screen_text(req.text)

        async def gen() -> AsyncIterator[bytes]:
            if block is not None:
                yield ndjson({"done": True, "mode": block.mode, "iters": 0, "text": block.text})
                return
            try:
                hint = req.mode if req.mode and req.mode != "auto" else None
                async for ev in request.app.state.agent.run_stream(
                    req.user_id, safe or req.text, mode=hint, mode_hint=hint
                ):
                    yield ndjson(ev)
            except Exception:  # noqa: BLE001
                logger.exception("agent stream failed")
                yield ndjson(
                    {
                        "done": True,
                        "mode": "error",
                        "iters": 0,
                        "text": "Локальна модель зараз недоступна. Перевір, чи піднятий Ollama на хості.",
                    }
                )

        return StreamingResponse(gen(), media_type="application/x-ndjson")

    @router.post("/agent/plan")
    async def agent_plan_ep(req: PlanCreateRequest, request: Request) -> dict[str, Any]:
        text = require_text(req.text)
        try:
            return await request.app.state.agent.plan(req.user_id, text)
        except Exception as exc:  # noqa: BLE001
            logger.exception("agent plan failed")
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @router.post("/agent/code/plan")
    async def agent_code_plan_ep(req: PlanCreateRequest, request: Request) -> dict[str, Any]:
        """Code-specific план із file-targets (CA-4.1). Той самий approve/execute flow."""
        text = require_text(req.text)
        try:
            return await request.app.state.agent.code_plan(req.user_id, text)
        except Exception as exc:  # noqa: BLE001
            logger.exception("agent code plan failed")
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @router.post("/agent/code/review")
    async def agent_code_review_ep(req: CodeReviewRequest, request: Request) -> dict[str, Any]:
        """Self-review pass (CA-5.1): unified diff → структуровані зауваження."""
        try:
            return await request.app.state.agent.code_review(
                req.user_id, diff=req.diff, context=req.context
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("agent code review failed")
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @router.post("/agent/code/fix")
    async def agent_code_fix_ep(req: CodeFixRequest, request: Request) -> dict[str, Any]:
        """Виділена fix-orchestration (CA-3.2): тест→правка→тест до green/max/no-progress."""
        if not (req.exe or "").strip():
            raise HTTPException(status_code=400, detail="exe required")
        try:
            return await request.app.state.agent.fix_tests(
                req.user_id,
                exe=req.exe,
                args=req.args,
                path=req.path,
                task=req.task,
                max_rounds=req.max_rounds,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("agent code fix failed")
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @router.get("/agent/plan/{plan_id}")
    async def agent_plan_get(plan_id: str, user_id: int) -> dict[str, Any]:
        from .. import plans

        return require_found(await plans.get_plan(plan_id, user_id), detail="plan not found")

    @router.get("/agent/plans")
    async def agent_plans_list(user_id: int, limit: int = 20) -> dict[str, Any]:
        from .. import plans

        return {"plans": await plans.list_plans(user_id, limit), "user_id": user_id}

    @router.post("/agent/plan/{plan_id}/approve")
    async def agent_plan_approve(plan_id: str, req: PlanUserRequest) -> dict[str, Any]:
        from .. import plans

        return require_found(
            await plans.approve_plan(plan_id, req.user_id), detail="plan not found"
        )

    @router.post("/agent/plan/{plan_id}/deny")
    async def agent_plan_deny(plan_id: str, req: PlanUserRequest) -> dict[str, Any]:
        from .. import plans

        return require_found(
            await plans.deny_plan(plan_id, req.user_id), detail="plan not found"
        )

    @router.post("/agent/plan/{plan_id}/execute")
    async def agent_plan_execute(plan_id: str, req: PlanUserRequest, request: Request) -> dict[str, Any]:
        try:
            return await request.app.state.agent.execute_plan(req.user_id, plan_id)
        except Exception as exc:  # noqa: BLE001
            logger.exception("agent plan execute failed")
            raise HTTPException(status_code=502, detail=str(exc)) from exc
