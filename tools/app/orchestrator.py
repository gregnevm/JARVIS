"""Phase 7.1 — Orchestrator + Critic (DESIGN §4.7 Mediator pattern)."""
from __future__ import annotations

import uuid
from typing import Any

from jarvis_core.llm.parsers import extract_json_object

from .config import settings
from .redis_store import RedisIndexedStore, now_ts

_STORE = RedisIndexedStore(
    key_prefix="jarvis:orch:",
    index_prefix="jarvis:orch:index:",
    ttl=86400,
    history_max=30,
)

ORCHESTRATOR_SYSTEM = (
    "Ти Orchestrator JARVIS. Розбий задачу на чіткий план для Worker-агента: "
    "мета, кроки, обмеження, критерії якості. Без коду — лише план українською, стисло."
)

CRITIC_SYSTEM = (
    "Ти Critic JARVIS. Перевір чернетку відповіді Worker на фактичні помилки, прогалини, "
    "ризики та відхилення від задачі. НЕ виправляй сам — лише оціни.\n"
    'Відповідай JSON: {"approved": true|false, "issues": ["..."], "feedback": "..."}'
)


def parse_critic_verdict(text: str) -> dict[str, Any]:
    data = extract_json_object(text)
    if data and "approved" in data:
        issues = data.get("issues")
        if not isinstance(issues, list):
            issues = [str(issues)] if issues else []
        return {
            "approved": bool(data["approved"]),
            "issues": [str(x)[:300] for x in issues[:10]],
            "feedback": str(data.get("feedback") or "")[:1000],
        }
    upper = (text or "").upper()
    if "APPROVED" in upper and "NOT APPROVED" not in upper:
        return {"approved": True, "issues": [], "feedback": text[:500]}
    return {"approved": False, "issues": [text[:300]], "feedback": text[:500]}


async def get_run(run_id: str) -> dict[str, Any] | None:
    return await _STORE.get(run_id)


async def create_run(
    user_id: int,
    task: str,
    *,
    worker_budget: int | None = None,
    max_revisions: int | None = None,
) -> dict[str, Any]:
    task = (task or "").strip()
    if not task:
        raise ValueError("task required")
    run_id = uuid.uuid4().hex[:12]
    now = now_ts()
    rec: dict[str, Any] = {
        "id": run_id,
        "user_id": int(user_id),
        "status": "queued",
        "task": task[:4000],
        "worker_budget": max(
            1, min(int(worker_budget or settings.orchestrator_worker_budget), settings.subagent_max_budget)
        ),
        "max_revisions": max(0, min(int(max_revisions or settings.orchestrator_max_revisions), 3)),
        "steps": [],
        "plan": "",
        "draft": "",
        "result": "",
        "error": "",
        "created_at": now,
        "updated_at": now,
    }
    await _STORE.save(rec)
    await _STORE.index_append(user_id, run_id)
    return rec


async def list_runs(user_id: int, limit: int = 20) -> list[dict[str, Any]]:
    return await _STORE.list_for_user(user_id, limit)


async def append_step(run_id: str, step: dict[str, Any]) -> None:
    rec = await get_run(run_id)
    if rec is None:
        return
    raw_steps = rec.get("steps")
    steps: list[Any] = raw_steps if isinstance(raw_steps, list) else []
    steps.append(step)
    rec["steps"] = steps
    await _STORE.save(rec)


async def finish_run(
    run_id: str,
    *,
    result: str = "",
    error: str = "",
    status: str = "done",
    draft: str = "",
    plan: str = "",
) -> dict[str, Any] | None:
    rec = await get_run(run_id)
    if rec is None:
        return None
    rec["status"] = status
    if result:
        rec["result"] = result[:8000]
    if draft:
        rec["draft"] = draft[:8000]
    if plan:
        rec["plan"] = plan[:4000]
    rec["error"] = (error or "")[:2000]
    await _STORE.save(rec)
    return rec


async def _chat(
    chat_backend: Any,
    *,
    system: str,
    user: str,
    model: str,
) -> str:
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    msg = await chat_backend.chat(model, messages, tools=None, num_predict=1024)
    return str(msg.get("content") or "").strip()


async def run_orchestrator_pipeline(
    chat_backend: Any,
    agent_runner: Any,
    user_id: int,
    run_id: str,
    *,
    progress_cb: Any = None,
) -> dict[str, Any]:
    """Plan → Worker draft → Critic → optional revision → final."""
    rec = await get_run(run_id)
    if rec is None:
        return {"error": "run not found"}
    rec["status"] = "running"
    await _STORE.save(rec)
    task = str(rec.get("task") or "")
    budget = int(rec.get("worker_budget") or settings.orchestrator_worker_budget)
    max_rev = int(rec.get("max_revisions") or settings.orchestrator_max_revisions)
    model = settings.ollama_model_agent

    try:
        if progress_cb:
            await progress_cb(10, "Orchestrator plan")
        plan = await _chat(
            chat_backend,
            system=ORCHESTRATOR_SYSTEM,
            user=f"Задача:\n{task}",
            model=model,
        )
        rec["plan"] = plan
        await append_step(run_id, {"phase": "plan", "output": plan[:2000]})

        draft = ""
        critique: dict[str, Any] = {"approved": False, "issues": [], "feedback": ""}
        for round_i in range(max_rev + 1):
            if progress_cb:
                await progress_cb(25 + round_i * 30, f"Worker draft r{round_i + 1}")
            worker_prompt = (
                f"План Orchestrator:\n{plan}\n\n"
                f"Задача користувача:\n{task}\n"
            )
            if round_i > 0 and critique.get("feedback"):
                worker_prompt += (
                    f"\n\nКритика Critic (виправ):\n{critique['feedback']}\n"
                    f"Проблеми: {', '.join(critique.get('issues') or [])}"
                )
            turn = await agent_runner.run(
                user_id,
                worker_prompt,
                mode="agent",
                max_iters_override=budget,
            )
            draft = str(turn.get("text") or "")
            await append_step(
                run_id,
                {"phase": "worker", "round": round_i + 1, "output": draft[:2000], "iters": turn.get("iters")},
            )

            if progress_cb:
                await progress_cb(50 + round_i * 25, "Critic review")
            critic_raw = await _chat(
                chat_backend,
                system=CRITIC_SYSTEM,
                user=(
                    f"Задача:\n{task}\n\nПлан:\n{plan}\n\n"
                    f"Чернетка Worker:\n{draft}"
                ),
                model=model,
            )
            critique = parse_critic_verdict(critic_raw)
            await append_step(run_id, {"phase": "critic", "round": round_i + 1, **critique})

            if critique.get("approved"):
                break

        final = draft.strip() or "Orchestrator не дав результату."
        await finish_run(run_id, result=final, draft=draft, plan=plan, status="done")
        if progress_cb:
            await progress_cb(100, "done")
        return {
            "run_id": run_id,
            "result": final,
            "plan": plan,
            "approved": bool(critique.get("approved")),
            "critique": critique,
        }
    except Exception as exc:  # noqa: BLE001
        await finish_run(run_id, error=str(exc), status="failed")
        return {"error": str(exc), "run_id": run_id}
