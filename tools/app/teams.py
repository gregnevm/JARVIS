"""Agent Teams (P9) — Researcher → Coder → Reviewer pipeline."""
from __future__ import annotations

import uuid
from typing import Any

from .config import settings
from .redis_store import RedisIndexedStore, now_ts

_STORE = RedisIndexedStore(
    key_prefix="jarvis:team:",
    index_prefix="jarvis:team:index:",
    ttl=86400,
    history_max=30,
)

DEFAULT_ROLES = ("researcher", "coder", "reviewer")
# CA-5.2: coding-pipeline preset (Coder→Reviewer→Tester) поверх run_team_pipeline.
CODING_ROLES = ("coder", "reviewer", "tester")

ROLE_PROMPTS: dict[str, str] = {
    "researcher": (
        "Ти Researcher у команді JARVIS. Збери факти, контекст, ризики та варіанти. "
        "Використовуй web_search/web_fetch за потреби. Без коду — лише аналіз."
    ),
    "coder": (
        "Ти Coder у команді JARVIS. На основі research запропонуй конкретне рішення, "
        "кроки, команди або код. Стисло, actionable. Для задач кодування редагуй файли "
        "через code_edit / code_edit_batch (диффом, не повним перезаписом), не друкуй код у чат."
    ),
    "reviewer": (
        "Ти Reviewer у команді JARVIS. Перевір research і coder output: помилки, прогалини, "
        "безпека. Для змін коду поклич code_review на diff і перелічи зауваження за severity. "
        "Дай фінальну рекомендацію українською."
    ),
    "tester": (
        "Ти Tester у команді JARVIS. Переконайся, що зміни коду працюють: поклич run_tests "
        "(і run_lint за потреби), прочитай структурований підсумок і чесно звітуй "
        "passed/failed + що саме падає. Не вигадуй результатів — лише з інструментів."
    ),
}


async def get_team(team_id: str, user_id: int | None = None) -> dict[str, Any] | None:
    return await _STORE.get(team_id, owner_user_id=user_id)


async def create_team(
    user_id: int,
    task: str,
    *,
    roles: list[str] | None = None,
    budget_per_role: int = 3,
) -> dict[str, Any]:
    task = (task or "").strip()
    if not task:
        raise ValueError("task required")
    use_roles = [r for r in (roles or list(DEFAULT_ROLES)) if r in ROLE_PROMPTS]
    if not use_roles:
        use_roles = list(DEFAULT_ROLES)
    budget = max(1, min(int(budget_per_role), settings.subagent_max_budget))
    team_id = uuid.uuid4().hex[:12]
    now = now_ts()
    rec: dict[str, Any] = {
        "id": team_id,
        "user_id": int(user_id),
        "status": "queued",
        "task": task[:4000],
        "roles": use_roles,
        "budget_per_role": budget,
        "steps": [],
        "result": "",
        "error": "",
        "created_at": now,
        "updated_at": now,
    }
    await _STORE.save(rec)
    await _STORE.index_append(user_id, team_id)
    return rec


async def list_teams(user_id: int, limit: int = 20) -> list[dict[str, Any]]:
    return await _STORE.list_for_user(user_id, limit)


async def mark_running(team_id: str) -> dict[str, Any] | None:
    rec = await get_team(team_id)
    if rec is None:
        return None
    rec["status"] = "running"
    await _STORE.save(rec)
    return rec


async def append_step(team_id: str, step: dict[str, Any]) -> dict[str, Any] | None:
    rec = await get_team(team_id)
    if rec is None:
        return None
    raw_steps = rec.get("steps")
    steps: list[Any] = raw_steps if isinstance(raw_steps, list) else []
    steps.append(step)
    rec["steps"] = steps
    await _STORE.save(rec)
    return rec


async def finish_team(
    team_id: str,
    *,
    result: str = "",
    error: str = "",
    status: str = "done",
) -> dict[str, Any] | None:
    rec = await get_team(team_id)
    if rec is None:
        return None
    rec["status"] = status
    rec["result"] = (result or "")[:8000]
    rec["error"] = (error or "")[:2000]
    await _STORE.save(rec)
    return rec


def role_system_prompt(role: str) -> str:
    return ROLE_PROMPTS.get(role, f"Ти агент ролі {role}.")


async def run_team_pipeline(
    agent_runner: Any,
    user_id: int,
    team_id: str,
    *,
    progress_cb: Any = None,
) -> dict[str, Any]:
    """Sequential role execution; mutates Redis team record."""
    rec = await get_team(team_id)
    if rec is None:
        return {"error": "team not found"}
    await mark_running(team_id)
    task = str(rec.get("task") or "")
    roles = rec.get("roles") or list(DEFAULT_ROLES)
    budget = int(rec.get("budget_per_role") or settings.subagent_default_budget)
    accumulated = ""
    steps: list[dict[str, Any]] = []

    for i, role in enumerate(roles):
        if progress_cb:
            await progress_cb(int(10 + (80 * i) / max(len(roles), 1)), f"Role: {role}")
        prior = accumulated or "(немає)"
        prompt = (
            f"{role_system_prompt(role)}\n\n"
            f"Загальна задача команди: {task}\n\n"
            f"Результати попередніх ролей:\n{prior}\n\n"
            f"Твій внесок як {role}:"
        )
        try:
            turn = await agent_runner.run(
                user_id,
                prompt,
                mode="agent",
                max_iters_override=budget,
            )
            text = str(turn.get("text") or "")
            step = {"role": role, "output": text[:4000], "iters": int(turn.get("iters") or 0)}
            steps.append(step)
            accumulated += f"\n\n## {role}\n{text}"
            await append_step(team_id, step)
        except Exception as exc:  # noqa: BLE001
            await finish_team(team_id, error=str(exc), status="failed")
            return {"error": str(exc), "steps": steps}

    final = accumulated.strip() or "Команда не дала результату."
    await finish_team(team_id, result=final, status="done")
    if progress_cb:
        await progress_cb(100, "done")
    return {"result": final, "steps": steps, "team_id": team_id}
