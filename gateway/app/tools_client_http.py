"""HTTP helpers для ToolsClient — спільний httpx boilerplate."""
from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger("jarvis.gateway.tools")


async def tools_request(
    client: httpx.AsyncClient,
    base: str,
    method: str,
    path: str,
    *,
    json: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
    timeout: float | None = None,
    log_label: str = "",
) -> httpx.Response | None:
    """Виконує HTTP-запит до Tools. path — відносний (/agent/plan/{id})."""
    url = f"{base.rstrip('/')}{path}"
    kwargs: dict[str, Any] = {}
    if json is not None:
        kwargs["json"] = json
    if params is not None:
        kwargs["params"] = params
    if timeout is not None:
        kwargs["timeout"] = timeout
    try:
        resp = await client.request(method.upper(), url, **kwargs)
        return resp
    except httpx.HTTPError as exc:
        label = log_label or f"{method.upper()} {path}"
        logger.error("tools %s failed: %s", label, exc)
        return None
