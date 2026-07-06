"""Cost-дашборд /platform (SY-6.4) — tag-запит по kind:usage, той самий SSOT.

Один агрегатор (`saas/token_usage.py`) живить і `/v1/usage`, і цю панель —
цифри збігаються за побудовою (DoD SY-6).
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from ..saas.token_usage import token_usage_summary
from .auth import PlatformAuth, require_platform_auth


def register(router: APIRouter) -> None:
    @router.get("/platform/api/usage")
    async def platform_usage(
        days: int = 7, _auth: PlatformAuth = Depends(require_platform_auth)
    ) -> dict[str, Any]:
        return await token_usage_summary(days=days)
