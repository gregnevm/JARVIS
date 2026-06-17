"""ToolsClient · домен Orchestration (R3): research, cursor, mcp, skills, subagents,
teams, orchestrator, improve, hooks."""
from __future__ import annotations

from typing import Any

import httpx

from .tools_client_base import ToolsClientBase


class OrchestratorMixin(ToolsClientBase):
    async def run_research(self, job_id: str, user_id: int, query: str, max_hops: int = 3) -> dict[str, Any]:
        resp = await self._request(
            "POST", "/research/run",
            json={
                "job_id": job_id,
                "user_id": int(user_id),
                "query": query,
                "max_hops": max_hops,
            },
            timeout=300.0,
            log_label="run research",
        )
        if resp is None:
            return {"error": "tools unavailable"}
        try:
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, dict) else {"error": "bad response"}
        except httpx.HTTPError as exc:
            return {"error": str(exc)}

    async def create_research_job(self, user_id: int, query: str, max_hops: int = 3) -> dict[str, Any]:
        resp = await self._request(
            "POST", "/bgjobs",
            json={
                "user_id": int(user_id),
                "job_type": "deep_research",
                "text": query,
                "max_hops": max_hops,
            },
            log_label="create research job",
        )
        if resp is None:
            return {"error": "tools unavailable"}
        try:
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, dict) else {"error": "bad response"}
        except httpx.HTTPError as exc:
            return {"error": str(exc)}

    async def create_cursor_job(self, user_id: int, task: str) -> dict[str, Any]:
        resp = await self._request(
            "POST", "/bgjobs",
            json={"user_id": int(user_id), "job_type": "cursor_task", "text": task},
            log_label="create cursor job",
        )
        if resp is None:
            return {"error": "tools unavailable"}
        try:
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, dict) else {"error": "bad response"}
        except httpx.HTTPError as exc:
            return {"error": str(exc)}

    async def run_cursor_task(self, task: str, user_id: int) -> dict[str, Any]:
        resp = await self._request(
            "POST", "/cursor/tasks/run",
            json={"user_id": int(user_id), "task": task, "async_mode": False},
            timeout=920.0,
            log_label="run cursor task",
        )
        if resp is None:
            return {"text": "", "error": "tools unavailable"}
        try:
            resp.raise_for_status()
            data = resp.json()
            text = str(data.get("text") or "")[:3500]
            err = "" if data.get("ok") else str(data.get("error") or "failed")
            return {"text": text, "error": err, "raw": data}
        except httpx.HTTPError as exc:
            return {"text": "", "error": str(exc)}

    async def list_mcp_servers(self) -> dict[str, Any]:
        resp = await self._request("GET", "/mcp/servers")
        if resp is None:
            return {"servers": []}
        try:
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, dict) else {"servers": []}
        except httpx.HTTPError:
            return {"servers": []}

    async def list_connectors(self) -> dict[str, Any]:
        resp = await self._request("GET", "/connectors/status")
        if resp is None:
            return {}
        try:
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, dict) else {}
        except httpx.HTTPError:
            return {}

    async def list_skills(self) -> list[dict[str, Any]]:
        resp = await self._request("GET", "/skills")
        if resp is None:
            return []
        try:
            resp.raise_for_status()
            data = resp.json()
            skills = data.get("skills") if isinstance(data, dict) else []
            return skills if isinstance(skills, list) else []
        except httpx.HTTPError:
            return []

    async def set_active_skill(self, user_id: int, skill_id: str | None) -> dict[str, Any]:
        resp = await self._request(
            "POST", "/skills/active",
            json={"user_id": int(user_id), "skill_id": skill_id},
        )
        if resp is None:
            return {"error": "tools unavailable"}
        try:
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as exc:
            return {"error": str(exc)}

    async def get_active_skill(self, user_id: int) -> dict[str, Any]:
        resp = await self._request("GET", f"/skills/active/{int(user_id)}")
        if resp is None:
            return {"user_id": user_id, "skill_id": None}
        try:
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError:
            return {"user_id": user_id, "skill_id": None}

    async def get_skill(self, skill_id: str) -> dict[str, Any] | None:
        resp = await self._request("GET", f"/skills/{skill_id}")
        if resp is None or resp.status_code == 404:
            return None
        try:
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError:
            return None

    async def spawn_subagent(
        self, user_id: int, task: str, budget_iters: int = 3, async_mode: bool = True
    ) -> dict[str, Any]:
        resp = await self._request(
            "POST", "/subagents/spawn",
            json={
                "user_id": int(user_id),
                "task": task,
                "budget_iters": budget_iters,
                "async_mode": async_mode,
            },
        )
        if resp is None:
            return {"error": "tools unavailable"}
        try:
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as exc:
            return {"error": str(exc)}

    async def list_subagents(self, user_id: int, limit: int = 20) -> list[dict[str, Any]]:
        resp = await self._request(
            "GET", "/subagents", params={"user_id": user_id, "limit": limit}
        )
        if resp is None:
            return []
        try:
            resp.raise_for_status()
            data = resp.json()
            runs = data.get("runs") if isinstance(data, dict) else []
            return runs if isinstance(runs, list) else []
        except httpx.HTTPError:
            return []

    async def hooks_status(self) -> dict[str, Any]:
        resp = await self._request("GET", "/hooks/status")
        if resp is None:
            return {"enabled": False}
        try:
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError:
            return {"enabled": False}

    async def run_subagent(
        self,
        job_id: str,
        user_id: int,
        run_id: str,
        task: str,
        budget_iters: int,
        mode: str,
    ) -> dict[str, Any]:
        resp = await self._request(
            "POST", "/subagents/run",
            json={
                "job_id": job_id,
                "user_id": int(user_id),
                "run_id": run_id,
                "task": task,
                "budget_iters": budget_iters,
                "mode": mode,
            },
            timeout=300.0,
        )
        if resp is None:
            return {"error": "tools unavailable"}
        try:
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as exc:
            return {"error": str(exc)}

    async def spawn_team(
        self,
        user_id: int,
        task: str,
        budget_per_role: int = 3,
        async_mode: bool = True,
    ) -> dict[str, Any]:
        resp = await self._request(
            "POST", "/teams/spawn",
            json={
                "user_id": int(user_id),
                "task": task,
                "budget_per_role": budget_per_role,
                "async_mode": async_mode,
            },
        )
        if resp is None:
            return {"error": "tools unavailable"}
        try:
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as exc:
            return {"error": str(exc)}

    async def list_teams(self, user_id: int, limit: int = 20) -> list[dict[str, Any]]:
        resp = await self._request(
            "GET", "/teams", params={"user_id": user_id, "limit": limit}
        )
        if resp is None:
            return []
        try:
            resp.raise_for_status()
            data = resp.json()
            teams = data.get("teams") if isinstance(data, dict) else []
            return teams if isinstance(teams, list) else []
        except httpx.HTTPError:
            return []

    async def get_team(self, team_id: str, user_id: int) -> dict[str, Any] | None:
        resp = await self._request("GET", f"/teams/{team_id}", params={"user_id": user_id})
        if resp is None or resp.status_code == 404:
            return None
        try:
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError:
            return None

    async def run_team(self, job_id: str, user_id: int, team_id: str) -> dict[str, Any]:
        resp = await self._request(
            "POST", "/teams/run",
            json={"job_id": job_id, "user_id": int(user_id), "team_id": team_id},
            timeout=600.0,
        )
        if resp is None:
            return {"error": "tools unavailable"}
        try:
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as exc:
            return {"error": str(exc)}

    async def spawn_orchestrator(
        self,
        user_id: int,
        task: str,
        *,
        worker_budget: int = 5,
        async_mode: bool = True,
    ) -> dict[str, Any]:
        resp = await self._request(
            "POST", "/orchestrator/spawn",
            json={
                "user_id": int(user_id),
                "task": task,
                "worker_budget": worker_budget,
                "async_mode": async_mode,
            },
        )
        if resp is None:
            return {"error": "tools unavailable"}
        try:
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as exc:
            return {"error": str(exc)}

    async def run_orchestrator(self, job_id: str, user_id: int, run_id: str) -> dict[str, Any]:
        resp = await self._request(
            "POST", "/orchestrator/run",
            json={"job_id": job_id, "user_id": int(user_id), "run_id": run_id},
            timeout=900.0,
        )
        if resp is None:
            return {"error": "tools unavailable"}
        try:
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as exc:
            return {"error": str(exc)}

    async def list_orchestrator_runs(self, user_id: int, limit: int = 20) -> list[dict[str, Any]]:
        resp = await self._request(
            "GET", "/orchestrator", params={"user_id": user_id, "limit": limit}
        )
        if resp is None:
            return []
        try:
            resp.raise_for_status()
            data = resp.json()
            runs = data.get("runs") if isinstance(data, dict) else []
            return runs if isinstance(runs, list) else []
        except httpx.HTTPError:
            return []

    async def improve_status(self, user_id: int | None = None) -> dict[str, Any]:
        params = {"user_id": user_id} if user_id is not None else {}
        resp = await self._request("GET", "/improve/status", params=params)
        if resp is None:
            return {"enabled": False}
        try:
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError:
            return {"enabled": False}

    async def improve_scan(self, user_id: int | None = None) -> dict[str, Any]:
        params = {"user_id": user_id} if user_id is not None else {}
        resp = await self._request("POST", "/improve/scan", params=params, timeout=300.0)
        if resp is None:
            return {"error": "tools unavailable"}
        try:
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as exc:
            return {"error": str(exc)}

    async def improve_pending(self, limit: int = 20) -> list[dict[str, Any]]:
        resp = await self._request("GET", "/improve/pending", params={"limit": limit})
        if resp is None:
            return []
        try:
            resp.raise_for_status()
            data = resp.json()
            pending = data.get("pending") if isinstance(data, dict) else []
            return pending if isinstance(pending, list) else []
        except httpx.HTTPError:
            return []

    async def improve_review(self, item_ids: list[str], action: str, reviewer: str = "") -> dict[str, Any]:
        resp = await self._request(
            "POST", "/improve/review",
            json={"item_ids": item_ids, "action": action, "reviewer": reviewer},
        )
        if resp is None:
            return {"error": "tools unavailable"}
        try:
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as exc:
            return {"error": str(exc)}
