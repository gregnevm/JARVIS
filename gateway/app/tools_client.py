"""Клієнт Tools-сервісу: Gateway → POST /agent (DESIGN — агент-луп у Python, без n8n)."""
from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import httpx

from .tools_client_http import tools_request

logger = logging.getLogger("jarvis.gateway.tools")

FALLBACK = "Вибач, зараз не можу обробити запит — агент недоступний. Спробуй ще раз трохи згодом."


def extract_text(data: Any) -> str:
    """Дістає текст відповіді з JSON Tools / legacy n8n-форматів."""
    if isinstance(data, str):
        return data or FALLBACK
    if isinstance(data, dict):
        for key in ("text", "reply", "message", "output", "answer", "response"):
            val = data.get(key)
            if isinstance(val, str) and val.strip():
                return val
        msg = data.get("message")
        if isinstance(msg, dict) and isinstance(msg.get("content"), str):
            return msg["content"]
    return FALLBACK


class ToolsClient:
    def __init__(self, base_url: str, timeout: float = 300.0) -> None:
        base = base_url.rstrip("/")
        self._base = base
        self._url = f"{base}/agent"
        self._stream_url = f"{base}/agent/stream"
        self._client = httpx.AsyncClient(timeout=timeout)

    @staticmethod
    def _extra_headers(payload: dict[str, Any]) -> dict[str, str]:
        rid = payload.get("request_id")
        if isinstance(rid, str) and rid.strip():
            return {"X-Request-ID": rid.strip()}
        return {}

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        timeout: float | None = None,
        log_label: str = "",
    ) -> httpx.Response | None:
        return await tools_request(
            self._client,
            self._base,
            method,
            path,
            json=json,
            params=params,
            timeout=timeout,
            log_label=log_label,
        )

    async def stream(self, payload: dict[str, Any]) -> AsyncIterator[dict[str, Any]]:
        """Стрімить події інференсу (NDJSON) з /agent/stream. HTTP-помилки кидає назовні
        (виклик робить фолбек). Невалідні рядки тихо пропускаємо."""
        user_id = payload.get("user_id")
        text = payload.get("text")
        if user_id is None or not isinstance(text, str) or not text.strip():
            return
        body = {"user_id": int(user_id), "text": text}
        mode = payload.get("mode")
        if isinstance(mode, str) and mode.strip() and mode.strip().lower() != "auto":
            body["mode"] = mode.strip().lower()
        async with self._client.stream(
            "POST", self._stream_url, json=body, headers=self._extra_headers(payload)
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue
                if isinstance(obj, dict):
                    yield obj

    async def process(self, payload: dict[str, Any]) -> str:
        user_id = payload.get("user_id")
        text = payload.get("text")
        if user_id is None or not isinstance(text, str) or not text.strip():
            return FALLBACK
        body = {"user_id": int(user_id), "text": text}
        mode = payload.get("mode")
        if isinstance(mode, str) and mode.strip() and mode.strip().lower() != "auto":
            body["mode"] = mode.strip().lower()
        try:
            resp = await self._client.post(
                self._url, json=body, headers=self._extra_headers(payload)
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.error("tools /agent failed: %s", exc)
            return FALLBACK
        try:
            return extract_text(resp.json())
        except ValueError:
            return resp.text or FALLBACK

    async def confirm_computer(self, user_id: int, code: str) -> tuple[str, str]:
        """Повертає (result, origin_user_text)."""
        resp = await self._request(
            "POST", "/computer/confirm",
            json={"user_id": int(user_id), "code": code},
            log_label="/computer/confirm",
        )
        if resp is None:
            return "Не вдалося виконати дію — tools недоступний.", ""
        try:
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, dict) and isinstance(data.get("result"), str):
                return data["result"], str(data.get("origin") or "")
        except httpx.HTTPError:
            pass
        return FALLBACK, ""

    async def cancel_computer(self, user_id: int) -> None:
        await self._request(
            "POST", "/computer/cancel",
            json={"user_id": int(user_id)},
            log_label="/computer/cancel",
        )

    async def capture_screenshot(self, user_id: int) -> str:
        resp = await self._request(
            "POST", "/computer/screenshot",
            json={"user_id": int(user_id)},
            log_label="/computer/screenshot",
        )
        if resp is None:
            return "Не вдалося зняти скріншот — перевір host-agent на хості (порт 8400)."
        try:
            resp.raise_for_status()
            return extract_text(resp.json())
        except httpx.HTTPError:
            return "Не вдалося зняти скріншот — перевір host-agent на хості (порт 8400)."

    async def pull_file(self, user_id: int, path: str) -> dict[str, Any]:
        resp = await self._request(
            "POST", "/computer/file/pull",
            json={"user_id": int(user_id), "path": path},
            log_label="file pull",
        )
        if resp is None:
            return {"error": "tools unavailable"}
        try:
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, dict) else {"error": "invalid response"}
        except httpx.HTTPError as exc:
            return {"error": str(exc)}

    async def push_file(self, user_id: int, path: str, data_b64: str) -> dict[str, Any]:
        resp = await self._request(
            "POST", "/computer/file/push",
            json={"user_id": int(user_id), "path": path, "data_b64": data_b64},
        )
        if resp is None:
            return {"error": "tools unavailable"}
        try:
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as exc:
            return {"error": str(exc)}

    async def clipboard_read(self, user_id: int) -> str:
        resp = await self._request(
            "POST", "/computer/clipboard/read",
            json={"user_id": int(user_id)},
        )
        if resp is None:
            return "Clipboard недоступний"
        try:
            resp.raise_for_status()
            return extract_text(resp.json())
        except httpx.HTTPError as exc:
            return f"Clipboard недоступний: {exc}"

    async def see_screen(self, user_id: int, question: str = "") -> str:
        resp = await self._request(
            "POST", "/computer/see",
            json={"user_id": int(user_id), "question": question},
        )
        if resp is None:
            return "See screen failed"
        try:
            resp.raise_for_status()
            return extract_text(resp.json())
        except httpx.HTTPError as exc:
            return f"See screen failed: {exc}"

    async def list_macros(self) -> dict[str, Any]:
        resp = await self._request("GET", "/computer/macros")
        if resp is None or resp.status_code != 200:
            return {"macros": []}
        return resp.json()

    async def run_macro(self, user_id: int, name: str) -> str:
        resp = await self._request(
            "POST", "/computer/macro/run",
            json={"user_id": int(user_id), "name": name},
        )
        if resp is None:
            return "Macro failed"
        try:
            resp.raise_for_status()
            return extract_text(resp.json())
        except httpx.HTTPError as exc:
            return f"Macro failed: {exc}"

    async def grant_trust(self, user_id: int) -> None:
        await self._request(
            "POST", "/computer/trust",
            json={"user_id": int(user_id)},
            log_label="grant trust",
        )

    async def get_ps_pending(self, user_id: int) -> dict[str, Any]:
        resp = await self._request("GET", "/computer/pending", params={"user_id": user_id})
        if resp is None or resp.status_code != 200:
            return {"pending": False}
        return resp.json()

    async def get_ps_audit(self, *, limit: int = 30) -> dict[str, Any]:
        resp = await self._request(
            "GET", "/computer/audit",
            params={"limit": limit, "tool": "run_powershell"},
        )
        if resp is None or resp.status_code != 200:
            return {"entries": []}
        return resp.json()

    async def get_ps_policy(self) -> dict[str, Any]:
        resp = await self._request("GET", "/computer/powershell/policy")
        if resp is None or resp.status_code != 200:
            return {}
        return resp.json()

    async def get_trust_status(self, user_id: int) -> dict[str, Any]:
        resp = await self._request(
            "GET", "/computer/trust/status", params={"user_id": user_id}
        )
        if resp is None or resp.status_code != 200:
            return {"trusted": False, "ttl_seconds": 0}
        return resp.json()

    async def remote_status(self, user_id: int) -> dict[str, Any]:
        out: dict[str, Any] = {}
        r = await self._request("GET", "/computer/pending", params={"user_id": user_id})
        out["pending"] = r.json() if r and r.status_code == 200 else {}
        r2 = await self._request("GET", "/computer/audit", params={"limit": 20})
        r3 = await self._request("GET", "/computer/learned")
        out["learned"] = r3.json() if r3 and r3.status_code == 200 else {}
        out["audit"] = r2.json() if r2 and r2.status_code == 200 else {}
        return out

    async def list_tasks(self, user_id: int) -> str:
        resp = await self._request("GET", "/tasks", params={"user_id": user_id})
        if resp is None:
            return "Tasks недоступні."
        try:
            resp.raise_for_status()
            return extract_text(resp.json())
        except httpx.HTTPError:
            return "Tasks недоступні."

    async def cancel_tasks(self, user_id: int) -> None:
        await self._request("DELETE", "/tasks", params={"user_id": user_id})

    async def reminders_ics(self, user_id: int) -> bytes:
        resp = await self._request("GET", "/reminders/ics", params={"user_id": user_id})
        if resp is None:
            return b""
        if resp.status_code == 404:
            return b""
        try:
            resp.raise_for_status()
            return resp.content
        except httpx.HTTPError as exc:
            logger.error("reminders ics failed: %s", exc)
            return b""

    async def export_dataset(self, user_id: int | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {}
        if user_id is not None:
            params["user_id"] = int(user_id)
        resp = await self._request(
            "POST", "/dataset/export/sharegpt",
            params=params,
            log_label="dataset export",
        )
        if resp is None:
            return {"error": "tools unavailable"}
        try:
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, dict) else {"error": "bad response"}
        except httpx.HTTPError as exc:
            return {"error": str(exc)}

    async def dataset_stats(self, user_id: int | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {}
        if user_id is not None:
            params["user_id"] = int(user_id)
        resp = await self._request("GET", "/dataset/stats", params=params)
        if resp is None:
            return {"error": "tools unavailable"}
        try:
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as exc:
            return {"error": str(exc)}

    async def due_jobs(self) -> list[dict[str, Any]]:
        resp = await self._request("GET", "/jobs/due")
        if resp is None:
            return []
        try:
            resp.raise_for_status()
            data = resp.json()
            jobs = data.get("jobs") if isinstance(data, dict) else []
            return jobs if isinstance(jobs, list) else []
        except httpx.HTTPError:
            return []

    async def create_bg_job(self, user_id: int, text: str, mode: str = "auto") -> dict[str, Any]:
        resp = await self._request(
            "POST", "/bgjobs",
            json={"user_id": int(user_id), "text": text, "mode": mode},
            log_label="create bg job",
        )
        if resp is None:
            return {"error": "tools unavailable"}
        try:
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, dict) else {"error": "bad response"}
        except httpx.HTTPError as exc:
            return {"error": str(exc)}

    async def get_bg_job(self, job_id: str) -> dict[str, Any] | None:
        resp = await self._request("GET", f"/bgjobs/{job_id}")
        if resp is None or resp.status_code == 404:
            return None
        try:
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, dict) else None
        except httpx.HTTPError:
            return None

    async def list_bg_jobs(self, user_id: int, limit: int = 20) -> list[dict[str, Any]]:
        resp = await self._request(
            "GET", "/bgjobs", params={"user_id": user_id, "limit": limit}
        )
        if resp is None:
            return []
        try:
            resp.raise_for_status()
            data = resp.json()
            jobs = data.get("jobs") if isinstance(data, dict) else []
            return jobs if isinstance(jobs, list) else []
        except httpx.HTTPError:
            return []

    async def cancel_bg_job(self, job_id: str, user_id: int) -> bool:
        resp = await self._request(
            "DELETE", f"/bgjobs/{job_id}", params={"user_id": user_id}
        )
        return resp is not None and resp.status_code == 200

    async def dequeue_bg_job(self) -> dict[str, Any] | None:
        resp = await self._request("GET", "/bgjobs/dequeue")
        if resp is None:
            return None
        try:
            resp.raise_for_status()
            data = resp.json()
            job = data.get("job") if isinstance(data, dict) else None
            return job if isinstance(job, dict) else None
        except httpx.HTTPError:
            return None

    async def finish_bg_job(
        self, job_id: str, *, result: str = "", error: str = "", status: str = "done"
    ) -> None:
        await self._request(
            "POST", f"/bgjobs/{job_id}/finish",
            json={"result": result, "error": error, "status": status},
            log_label=f"finish bg job {job_id}",
        )

    async def create_plan(self, user_id: int, text: str) -> dict[str, Any]:
        resp = await self._request(
            "POST", "/agent/plan",
            json={"user_id": int(user_id), "text": text},
            log_label="create plan",
        )
        if resp is None:
            return {"error": "tools unavailable"}
        try:
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, dict) else {"error": "bad response"}
        except httpx.HTTPError as exc:
            return {"error": str(exc)}

    async def get_plan(self, plan_id: str) -> dict[str, Any] | None:
        resp = await self._request("GET", f"/agent/plan/{plan_id}")
        if resp is None or resp.status_code == 404:
            return None
        try:
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, dict) else None
        except httpx.HTTPError:
            return None

    async def list_plans(self, user_id: int, limit: int = 20) -> list[dict[str, Any]]:
        resp = await self._request(
            "GET", "/agent/plans", params={"user_id": user_id, "limit": limit}
        )
        if resp is None:
            return []
        try:
            resp.raise_for_status()
            data = resp.json()
            plans = data.get("plans") if isinstance(data, dict) else []
            return plans if isinstance(plans, list) else []
        except httpx.HTTPError:
            return []

    async def approve_plan(self, plan_id: str, user_id: int) -> dict[str, Any] | None:
        resp = await self._request(
            "POST", f"/agent/plan/{plan_id}/approve",
            json={"user_id": int(user_id)},
            log_label="approve plan",
        )
        if resp is None or resp.status_code == 404:
            return None
        try:
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, dict) else None
        except httpx.HTTPError:
            return None

    async def deny_plan(self, plan_id: str, user_id: int) -> dict[str, Any] | None:
        resp = await self._request(
            "POST", f"/agent/plan/{plan_id}/deny",
            json={"user_id": int(user_id)},
        )
        if resp is None or resp.status_code == 404:
            return None
        try:
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, dict) else None
        except httpx.HTTPError:
            return None

    async def execute_plan(self, plan_id: str, user_id: int) -> dict[str, Any]:
        resp = await self._request(
            "POST", f"/agent/plan/{plan_id}/execute",
            json={"user_id": int(user_id)},
            timeout=180.0,
            log_label="execute plan",
        )
        if resp is None:
            return {"error": "tools unavailable"}
        try:
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, dict) else {"error": "bad response"}
        except httpx.HTTPError as exc:
            return {"error": str(exc)}

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

    async def get_team(self, team_id: str) -> dict[str, Any] | None:
        resp = await self._request("GET", f"/teams/{team_id}")
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
