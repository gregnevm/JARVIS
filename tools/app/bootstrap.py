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
    from .runtime import get_agent_mode

    out: dict[str, Any] = {
        "ollama_host": settings.ollama_host,
        "chat_model": settings.ollama_model_chat,
        "agent_model": settings.ollama_model_agent,
        "llm_backend": settings.llm_backend,
        "kobold_host": settings.kobold_host,
        "vision_model": settings.ollama_model_vision or None,
        "code_exec": settings.enable_code_exec,
        "agent_mode": get_agent_mode(),
        "agent_mode_env": settings.agent_mode,
        "max_agent_iters": settings.max_agent_iters,
        "computer_max_iters": settings.computer_max_iters,
        "enable_browser": settings.enable_browser,
        "computer_profile": settings.computer_profile,
        "computer_session_trust_minutes": settings.computer_session_trust_minutes,
        "computer_require_confirm": settings.computer_require_confirm,
        "computer_auto_vision": settings.computer_auto_vision,
        "computer_allow_power": settings.computer_allow_power,
        "image_gen": (settings.image_gen_url or "—") + (
            f" / {settings.image_gen_model}" if settings.image_gen_model else ""
        ),
    }
    try:
        async with httpx.AsyncClient(timeout=5.0) as c:
            r = await c.get(f"{settings.ollama_host.rstrip('/')}/api/tags")
            out["ollama_up"] = r.status_code == 200
    except httpx.HTTPError:
        out["ollama_up"] = False
    out["enable_computer_use"] = settings.enable_computer_use
    out["hostagent_up"] = False
    out["docker_up"] = False
    if settings.enable_computer_use and settings.hostagent_token:
        try:
            async with httpx.AsyncClient(timeout=3.0) as c:
                r = await c.get(
                    f"{settings.hostagent_url.rstrip('/')}/health",
                    headers={"X-Hostagent-Token": settings.hostagent_token},
                )
                out["hostagent_up"] = r.status_code == 200
                if out["hostagent_up"]:
                    rs = await c.get(
                        f"{settings.hostagent_url.rstrip('/')}/health/stack",
                        headers={"X-Hostagent-Token": settings.hostagent_token},
                    )
                    if rs.status_code == 200:
                        stack = rs.json()
                        out["docker_up"] = bool(stack.get("docker_up"))
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
    from .metrics import summary

    out["metrics"] = await summary()
    return out


async def _on_inference_stats(stats: dict[str, Any]) -> None:
    from .metrics import record_inference

    await record_inference(
        str(stats.get("model") or ""),
        int(stats["eval_count"]),
        int(stats["eval_duration_ns"]),
    )


def build_jarvis(memory: MemoryClient, twin_url: str = "") -> tuple[JARVIS, AgentRunner, CompositeChatBackend]:
    log_path = Path(settings.data_dir) / "logs" / "llm.jsonl"
    # LLMInterface обслуговує CHAT-шлях (відповіді без інструментів) → chat-модель.
    # Агентський tool-loop окремо передає ollama_model_agent у OllamaChatBackend.chat().
    llm = build_llm_stack(
        backend=settings.llm_backend,
        ollama_host=settings.ollama_host,
        ollama_model=settings.ollama_model_chat,
        kobold_host=settings.kobold_host,
        timeout=settings.ollama_timeout,
        log_path=str(log_path),
    )
    ollama_chat = OllamaChatBackend(
        settings.ollama_host,
        timeout=settings.ollama_timeout,
        fail_threshold=settings.ollama_fail_threshold,
        cooldown=settings.ollama_cooldown,
        on_inference_stats=_on_inference_stats,
    )
    chat_backend = CompositeChatBackend(ollama_chat, llm)
    runner = AgentRunner(chat_backend, memory)

    async def run_agent(user_id: int, text: str, mode: str) -> dict[str, Any]:
        hint = mode if mode and mode != "auto" else None
        return await runner.run(user_id, text, mode=hint, mode_hint=hint)

    pipeline = build_agent_pipeline(decide_mode, run_agent)

    async def status() -> dict[str, Any]:
        return await _fetch_status(memory, twin_url)

    facade = JARVIS(pipeline, get_agent_mode, status_provider=status)
    return facade, runner, chat_backend
