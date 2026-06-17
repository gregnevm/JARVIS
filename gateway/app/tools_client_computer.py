"""ToolsClient · домен Computer Use (R3): /computer/* — screenshot, файли, trust, audit."""
from __future__ import annotations

from typing import Any

import httpx

from .tools_client_base import FALLBACK, ToolsClientBase, extract_text


class ComputerMixin(ToolsClientBase):
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

    async def grant_trust(self, user_id: int, *, full: bool = False) -> None:
        await self._request(
            "POST", "/computer/trust",
            json={"user_id": int(user_id), "full": full},
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
