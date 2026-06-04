from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx

from jarvis_core.facade.jarvis import JARVIS
from jarvis_core.llm.chat import CompositeChatBackend, OllamaChatBackend
from jarvis_core.llm.decorators import build_llm_stack
from jarvis_core.pipeline.handlers import build_agent_pipeline

from .agent import AgentRunner, decide_mode
from .config import settings
from .memory_client import MemoryClient
from .runtime import get_agent_mode, set_agent_mode


async def _fetch_status(memory: MemoryClient, twin_url: str) -> dict[str, Any]:
    out: dict[str, Any] = {
        "ollama_host": settings.ollama_host,
        "chat_model": settings.ollama_model_chat,
        "agent_model": settings.ollama_model_agent,
        "code_exec": settings.enable_code_exec,
    }
    try:
        async with httpx.AsyncClient(timeout=5.0) as c:
            r = await c.get(f"{settings.ollama_host.rstrip('/')}/api/tags")
            out["ollama_up"] = r.status_code == 200
    except httpx.HTTPError:
        out["ollama_up"] = False
    out["enable_computer_use"] = settings.enable_computer_use
    out["hostagent_up"] = False
    if settings.enable_computer_use and settings.hostagent_token:
        try:
            async with httpx.AsyncClient(timeout=3.0) as c:
                r = await c.get(
                    f"{settings.hostagent_url.rstrip('/')}/health",
                    headers={"X-Hostagent-Token": settings.hostagent_token},
                )
                out["hostagent_up"] = r.status_code == 200
        except httpx.HTTPError:
            out["hostagent_up"] = False
    if twin_url:
        try:
            async with httpx.AsyncClient(timeout=5.0) as c:
                r = await c.get(f"{twin_url.rstrip('/')}/status")
                if r.status_code == 200:
                    out["twin"] = r.json()
        except httpx.HTTPError:
            out["twin"] = None
    return out


def build_jarvis(memory: MemoryClient, twin_url: str = "") -> tuple[JARVIS, AgentRunner, CompositeChatBackend]:
    log_path = Path(settings.data_dir) / "logs" / "llm.jsonl"
    # LLMInterface обслуговує CHAT-шлях (відповіді без інструментів) → chat-модель.
    # Агентський tool-loop окремо передає ollama_model_agent у OllamaChatBackend.chat().
    llm = build_llm_stack(
        backend="ollama",
        ollama_host=settings.ollama_host,
        ollama_model=settings.ollama_model_chat,
        timeout=settings.ollama_timeout,
        log_path=str(log_path),
    )
    ollama_chat = OllamaChatBackend(
        settings.ollama_host,
        timeout=settings.ollama_timeout,
        fail_threshold=settings.ollama_fail_threshold,
        cooldown=settings.ollama_cooldown,
    )
    chat_backend = CompositeChatBackend(ollama_chat, llm)
    runner = AgentRunner(chat_backend, memory)

    async def run_agent(user_id: int, text: str, mode: str) -> dict[str, Any]:
        return await runner.run(user_id, text, mode=mode)

    pipeline = build_agent_pipeline(decide_mode, run_agent)

    async def status() -> dict[str, Any]:
        return await _fetch_status(memory, twin_url)

    facade = JARVIS(pipeline, get_agent_mode, status_provider=status)
    return facade, runner, chat_backend
