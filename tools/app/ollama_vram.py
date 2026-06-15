"""C6.1 — on-demand vision: вивантажити agent/chat моделі перед vision, потім keep_alive=0.

ВАЖЛИВО: вивантаження = `/api/generate` з `keep_alive=0` (звільняє VRAM, лишає модель
на диску). НЕ `/api/delete` — той фізично видаляє модель з диска.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

import httpx

from .config import settings

logger = logging.getLogger("jarvis.tools.ollama_vram")


async def _loaded_models() -> set[str]:
    """Імена моделей, що ЗАРАЗ у VRAM (GET /api/ps). Помилка → порожньо."""
    url = f"{settings.ollama_host.rstrip('/')}/api/ps"
    try:
        async with httpx.AsyncClient(timeout=10.0) as cli:
            resp = await cli.get(url)
            if resp.status_code != 200:
                return set()
            data = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("ollama /api/ps failed: %s", exc)
        return set()
    names: set[str] = set()
    for m in data.get("models", []):
        for key in ("name", "model"):
            val = (m.get(key) or "").strip()
            if val:
                names.add(val)
    return names


async def _unload_model(name: str) -> bool:
    """Вивантажити модель з VRAM (keep_alive=0), якщо вона завантажена. Диск НЕ чіпаємо."""
    name = name.strip()
    if not name:
        return False
    loaded = await _loaded_models()
    # Точний збіг або з тегом ':latest' (Ollama /api/ps віддає повне ім'я).
    if name not in loaded and f"{name}:latest" not in loaded:
        return True  # уже не у VRAM — нічого робити
    url = f"{settings.ollama_host.rstrip('/')}/api/generate"
    try:
        async with httpx.AsyncClient(timeout=30.0) as cli:
            resp = await cli.post(url, json={"model": name, "keep_alive": 0})
            return resp.status_code == 200
    except httpx.HTTPError as exc:
        logger.warning("ollama unload %s failed: %s", name, exc)
    return False


async def unload_agent_models() -> None:
    """Звільнити VRAM під vision (chat + agent)."""
    for model in (settings.ollama_model_chat, settings.ollama_model_agent):
        await _unload_model(model)


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


def vision_chat_payload(prompt: str, image_b64: str) -> dict[str, Any]:
    """Payload для /api/chat з мінімальним keep_alive (не тримати vision у VRAM)."""
    payload: dict[str, Any] = {
        "model": settings.ollama_model_vision,
        "messages": [{"role": "user", "content": prompt, "images": [image_b64]}],
        "stream": False,
    }
    if settings.ollama_vision_on_demand:
        payload["keep_alive"] = 0
    return payload
