"""ToolsClient · домен Jobs/Plans (R3): /tasks, /reminders, /dataset, /bgjobs, /agent/plan*."""
from __future__ import annotations

from typing import Any

import httpx

from .tools_client_base import ToolsClientBase, extract_text, logger


class JobsMixin(ToolsClientBase):
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

    async def get_bg_job(self, job_id: str, user_id: int) -> dict[str, Any] | None:
        resp = await self._request("GET", f"/bgjobs/{job_id}", params={"user_id": user_id})
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

    async def get_plan(self, plan_id: str, user_id: int) -> dict[str, Any] | None:
        resp = await self._request("GET", f"/agent/plan/{plan_id}", params={"user_id": user_id})
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
