"""Спільні типи та нормалізація payload для background jobs."""
from __future__ import annotations

from typing import Any

JOB_TYPES: frozenset[str] = frozenset(
    {
        "agent_turn",
        "deep_research",
        "subagent",
        "agent_team",
        "orchestrator",
        "cursor_task",
        "coding_task",
        "delegate_tick",
    }
)

_PLATFORM_CREATE_METHODS: dict[str, str] = {
    "deep_research": "create_research_job",
    "cursor_task": "create_cursor_job",
    "coding_task": "create_coding_job",
}


def platform_create_method(job_type: str) -> str:
    """Ім'я методу ToolsClient для Platform jobs tab."""
    jt = (job_type or "agent_turn").strip()
    return _PLATFORM_CREATE_METHODS.get(jt, "create_bg_job")


def _require_task(payload: dict[str, Any]) -> str:
    """`task = (payload.get("task") or payload.get("text") or "").strip()`, або
    `ValueError("task required")`. Узагальнює патерн, побайтово повторений 4 рази
    у гілках `subagent`/`agent_team`/`orchestrator`/`cursor_task` нижче."""
    task = str(payload.get("task") or payload.get("text") or "").strip()
    if not task:
        raise ValueError("task required")
    return task


def normalize_payload(job_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Валідація та нормалізація payload перед збереженням у Redis."""
    jt = (job_type or "agent_turn").strip()
    if jt not in JOB_TYPES:
        raise ValueError(f"unknown job type: {jt}")

    if jt == "agent_turn":
        text = str(payload.get("text") or "").strip()
        if not text:
            raise ValueError("text required")
        return {"text": text, "mode": (str(payload.get("mode") or "auto")).strip().lower() or "auto"}

    if jt == "deep_research":
        query = str(payload.get("query") or payload.get("text") or "").strip()
        if not query:
            raise ValueError("query required")
        return {"query": query, "max_hops": int(payload.get("max_hops") or 3)}

    if jt == "subagent":
        task = _require_task(payload)
        return {
            "task": task,
            "budget_iters": int(payload.get("budget_iters") or 3),
            "run_id": str(payload.get("run_id") or ""),
            "mode": str(payload.get("mode") or "agent"),
        }

    if jt == "agent_team":
        task = _require_task(payload)
        return {
            "task": task,
            "team_id": str(payload.get("team_id") or ""),
            "budget_per_role": int(payload.get("budget_per_role") or 3),
            "roles": payload.get("roles") or [],
        }

    if jt == "orchestrator":
        task = _require_task(payload)
        return {
            "task": task,
            "run_id": str(payload.get("run_id") or ""),
            "worker_budget": int(payload.get("worker_budget") or 5),
            "max_revisions": int(payload.get("max_revisions") or 1),
        }

    if jt == "coding_task":
        exe = str(payload.get("exe") or "").strip()
        if not exe:
            raise ValueError("exe required")
        return {
            "exe": exe,
            "args": [str(a) for a in (payload.get("args") or [])],
            "path": str(payload.get("path") or ""),
            "task": str(payload.get("task") or ""),
            "max_rounds": int(payload.get("max_rounds") or 0),
        }

    if jt == "delegate_tick":
        # Проактивний тік делегата (Стовп D §7) — principal + org + курсор.
        principal = str(payload.get("principal_id") or payload.get("user_id") or "").strip()
        if not principal:
            raise ValueError("principal_id required")
        return {
            "principal_id": principal,
            "org_id": str(payload.get("org_id") or ""),
            "cursor": str(payload.get("cursor") or ""),
        }

    # cursor_task
    return {"task": _require_task(payload)}
