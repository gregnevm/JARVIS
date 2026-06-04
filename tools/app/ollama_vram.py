"""C6.1 — on-demand vision: вивантажити agent/chat моделі перед vision, потім keep_alive=0."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

import httpx

from .config import settings

logger = logging.getLogger("jarvis.tools.ollama_vram")


async def _delete_model(name: str) -> bool:
    if not name.strip():
        return False
    url = f"{settings.ollama_host.rstrip('/')}/api/delete"
    try:
        async with httpx.AsyncClient(timeout=30.0) as cli:
            resp = await cli.request("DELETE", url, json={"name": name.strip()})
            if resp.status_code in (200, 404):
                return True
    except httpx.HTTPError as exc:
        logger.warning("ollama delete %s failed: %s", name, exc)
    return False


async def unload_agent_models() -> None:
    """Звільнити VRAM під vision (chat + agent)."""
    for model in (settings.ollama_model_chat, settings.ollama_model_agent):
        await _delete_model(model)


@asynccontextmanager
async def vision_vram_scope() -> AsyncIterator[None]:
    """Якщо OLLAMA_VISION_ON_DEMAND=true — unload agent models до/після vision."""
    if not settings.ollama_vision_on_demand or not settings.ollama_model_vision:
        yield
        return
    await unload_agent_models()
    try:
        yield
    finally:
        await unload_agent_models()


def vision_chat_payload(prompt: str, image_b64: str) -> dict:
    """Payload для /api/chat з мінімальним keep_alive (не тримати vision у VRAM)."""
    payload: dict = {
        "model": settings.ollama_model_vision,
        "messages": [{"role": "user", "content": prompt, "images": [image_b64]}],
        "stream": False,
    }
    if settings.ollama_vision_on_demand:
        payload["keep_alive"] = 0
    return payload
