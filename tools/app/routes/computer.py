"""Computer Use endpoints: /computer/*."""
from __future__ import annotations

import base64
from typing import Any

from fastapi import APIRouter, HTTPException

from .. import computer_policy
from ..config import settings
from ..schemas import (
    ComputerConfirmRequest,
    ComputerUserRequest,
    FilePathRequest,
    FileUploadRequest,
    MacroRunRequest,
    SeeRequest,
    TrustRequest,
)
from ._helpers import require_text


def register(router: APIRouter) -> None:
    @router.post("/computer/confirm")
    async def computer_confirm_ep(req: ComputerConfirmRequest) -> dict[str, str]:
        from ..computer_access import computer_denied_message
        from ..computer_confirm import execute_confirmed

        denied = computer_denied_message(req.user_id)
        if denied:
            return {"result": denied, "origin": ""}
        code = require_text(req.code, field="code")
        result, origin = await execute_confirmed(req.user_id, code)
        return {"result": result, "origin": origin}

    @router.post("/computer/cancel")
    async def computer_cancel_ep(req: ComputerConfirmRequest) -> dict[str, str]:
        from ..computer_confirm import cancel_pending

        await cancel_pending(req.user_id)
        return {"status": "cancelled"}

    @router.post("/computer/screenshot")
    async def computer_screenshot_ep(req: ComputerUserRequest) -> dict[str, str]:
        from .. import computer
        from ..computer_access import computer_denied_message

        denied = computer_denied_message(req.user_id)
        if denied:
            return {"text": denied}
        text = await computer.capture_screenshot(user_id=req.user_id)
        return {"text": text}

    @router.post("/computer/file/pull")
    async def computer_file_pull(req: FilePathRequest) -> dict[str, Any]:
        from .. import computer
        from ..computer_access import computer_denied_message

        denied = computer_denied_message(req.user_id)
        if denied:
            return {"error": denied}
        data, name, err = await computer.download_file(req.path, user_id=req.user_id)
        if err:
            return {"error": err}
        if len(data) > settings.remote_file_max_bytes:
            return {"error": "file too large for Telegram"}
        return {"filename": name, "data_b64": base64.b64encode(data).decode("ascii")}

    @router.post("/computer/file/push")
    async def computer_file_push(req: FileUploadRequest) -> dict[str, str]:
        from .. import computer
        from ..computer_access import computer_denied_message

        denied = computer_denied_message(req.user_id)
        if denied:
            return {"error": denied}
        try:
            raw = base64.b64decode(req.data_b64, validate=True)
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="invalid base64") from None
        text = await computer.upload_file_bytes(req.path, raw, user_id=req.user_id)
        return {"text": text}

    @router.post("/computer/clipboard/read")
    async def computer_clipboard_read(req: ComputerUserRequest) -> dict[str, str]:
        from .. import computer
        from ..computer_access import computer_denied_message

        denied = computer_denied_message(req.user_id)
        if denied:
            return {"text": denied}
        return {"text": await computer.clipboard_read(user_id=req.user_id)}

    @router.post("/computer/see")
    async def computer_see_ep(req: SeeRequest) -> dict[str, str]:
        from .. import computer
        from ..computer_access import computer_denied_message

        denied = computer_denied_message(req.user_id)
        if denied:
            return {"text": denied}
        return {"text": await computer.see_screen(req.question, user_id=req.user_id)}

    @router.get("/computer/macros")
    async def computer_macros_list() -> dict[str, Any]:
        from ..macros import list_macros

        return {"macros": list_macros()}

    @router.post("/computer/macro/run")
    async def computer_macro_run(req: MacroRunRequest) -> dict[str, str]:
        from ..computer_access import computer_denied_message
        from ..macros import run_macro

        denied = computer_denied_message(req.user_id)
        if denied:
            return {"text": denied}
        return {"text": await run_macro(req.name, req.user_id)}

    @router.post("/computer/trust")
    async def computer_trust_ep(req: TrustRequest) -> dict[str, str]:
        from ..computer_trust import grant_trust, trust_remaining, trust_ttl_seconds

        await grant_trust(req.user_id, full=req.full)
        ttl = await trust_remaining(req.user_id) or trust_ttl_seconds(full=req.full)
        return {
            "status": "trusted",
            "mode": "full" if req.full else "session",
            "ttl_seconds": str(ttl),
        }

    @router.delete("/computer/trust")
    async def computer_revoke_trust_ep(req: TrustRequest) -> dict[str, str]:
        from ..computer_trust import revoke_trust

        await revoke_trust(req.user_id)
        return {"status": "revoked"}

    @router.get("/computer/trust/status")
    async def computer_trust_status_ep(user_id: int) -> dict[str, Any]:
        from ..computer_trust import is_trusted, trust_remaining

        return {
            "trusted": await is_trusted(user_id),
            "ttl_seconds": await trust_remaining(user_id),
        }

    @router.get("/computer/pending")
    async def computer_pending_ep(user_id: int) -> dict[str, Any]:
        from ..computer_confirm import load_pending_raw

        return await load_pending_raw(user_id)

    @router.get("/computer/audit")
    async def computer_audit_ep(limit: int = 20, tool: str | None = None) -> dict[str, Any]:
        from ..computer_audit import tail_actions

        lim = max(1, min(limit, 100))
        return {"entries": tail_actions(limit=lim, tool=tool)}

    @router.get("/computer/powershell/policy")
    async def computer_powershell_policy_ep() -> dict[str, Any]:
        from .. import computer
        from ..computer_learned import effective_ps_allowed, learned_summary
        from ..ps_whitelist import parse_whitelist

        env_ps = sorted(parse_whitelist(settings.ps_whitelist))
        learned = learned_summary()["ps"]
        effective = sorted(effective_ps_allowed())
        return {
            "enable_computer_use": settings.enable_computer_use,
            "allow_admin": settings.computer_allow_admin,
            "approval_policy": computer_policy.policy() or "(flags)",
            "require_confirm": computer_policy.require_confirm(),
            "hostagent_up": await computer.hostagent_healthy(),
            "ps_whitelist": env_ps,
            "learned_ps": learned,
            "effective": effective,
        }

    @router.get("/computer/learned")
    async def computer_learned_ep() -> dict[str, Any]:
        from ..computer_learned import learned_summary

        return learned_summary()
