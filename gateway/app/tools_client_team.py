"""ToolsClient · домен Team-ecosystem (Стовп D) — Telegram-групи / org-граф.

Тонкі обгортки над tools `/team/*` proxy (який ходить у memory). Помилки → безпечні
дефолти (off / порожньо): груповий шлях ніколи не валить бота (privacy-first §8.1).
"""
from __future__ import annotations

from typing import Any

import httpx

from .tools_client_base import ToolsClientBase


class TeamMixin(ToolsClientBase):
    async def _team_get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        resp = await self._request("GET", path, params=params, log_label=f"team {path}")
        if resp is None:
            return {}
        try:
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, dict) else {}
        except httpx.HTTPError:
            return {}

    async def _team_send(self, method: str, path: str, body: dict[str, Any]) -> dict[str, Any]:
        resp = await self._request(method, path, json=body, log_label=f"team {path}")
        if resp is None:
            return {"error": "tools unavailable"}
        try:
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, dict) else {}
        except httpx.HTTPError as exc:
            return {"error": str(exc)}

    # org-граф (для Platform «Команда»)
    async def team_squads(self, org_id: str) -> dict[str, Any]:
        return await self._team_get("/team/squads", {"org_id": org_id})

    async def team_create_squad(self, body: dict[str, Any]) -> dict[str, Any]:
        return await self._team_send("POST", "/team/squads", body)

    async def team_add_member(self, body: dict[str, Any]) -> dict[str, Any]:
        return await self._team_send("POST", "/team/squads/member", body)

    async def team_relationships(self, org_id: str) -> dict[str, Any]:
        return await self._team_get("/team/relationships", {"org_id": org_id})

    async def team_upsert_relationship(self, body: dict[str, Any]) -> dict[str, Any]:
        return await self._team_send("POST", "/team/relationships", body)

    async def team_graph(self, user_id: str, org_id: str) -> dict[str, Any]:
        return await self._team_get("/team/graph", {"user_id": user_id, "org_id": org_id})

    # процеси (BPO)
    async def team_processes(self, org_id: str) -> dict[str, Any]:
        return await self._team_get("/team/processes", {"org_id": org_id})

    async def team_create_process(self, body: dict[str, Any]) -> dict[str, Any]:
        return await self._team_send("POST", "/team/processes", body)

    async def team_get_process(self, process_id: str, org_id: str) -> dict[str, Any]:
        return await self._team_get(f"/team/processes/{process_id}", {"org_id": org_id})

    async def team_advance_process(self, process_id: str, body: dict[str, Any]) -> dict[str, Any]:
        return await self._team_send("POST", f"/team/processes/{process_id}/advance", body)

    async def group_ingest_level(self, chat_id: int) -> str:
        """Рівень згоди групи: off|addressed|ambient. Будь-яка помилка → off."""
        resp = await self._request(
            "GET", f"/team/group/{chat_id}/ingest", log_label="group ingest"
        )
        if resp is None:
            return "off"
        try:
            resp.raise_for_status()
            data = resp.json()
            return str(data.get("ingest") or "off") if isinstance(data, dict) else "off"
        except httpx.HTTPError:
            return "off"

    async def group_member_seen(
        self, chat_id: int, telegram_id: int, user_id: str | None = None
    ) -> None:
        await self._request(
            "POST", "/team/group/member",
            json={"chat_id": chat_id, "telegram_id": telegram_id, "user_id": user_id},
            log_label="group member",
        )

    async def group_collect(
        self, chat_id: int, user_id: int, summary: str, *, from_name: str = ""
    ) -> dict[str, Any]:
        resp = await self._request(
            "POST", "/team/group/collect",
            json={"chat_id": chat_id, "user_id": user_id, "summary": summary, "from_name": from_name},
            log_label="group collect",
        )
        if resp is None:
            return {"error": "tools unavailable"}
        try:
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, dict) else {}
        except httpx.HTTPError as exc:
            return {"error": str(exc)}
