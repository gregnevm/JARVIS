"""LoRA deploy endpoints."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from ..config import settings
from ..schemas import LoraDeployRequest
from ._helpers import lora_paths


def register(router: APIRouter) -> None:
    @router.get("/lora/status")
    async def lora_status_ep() -> dict[str, Any]:
        from .. import lora_deploy

        data, base, active = lora_paths()
        twin = await lora_deploy.fetch_active_from_twin(settings.twin_url)
        return {
            "deploy_enabled": settings.lora_deploy_enabled,
            "base_model": base,
            "model_prefix": settings.lora_ollama_model,
            "active_dir": str(active),
            "active_dir_exists": active.exists(),
            "twin_active": twin if twin.get("ok") else {"error": twin.get("error")},
        }

    @router.post("/lora/deploy")
    async def lora_deploy_ep(body: LoraDeployRequest | None = None) -> dict[str, Any]:
        if not settings.lora_deploy_enabled:
            raise HTTPException(status_code=400, detail="lora deploy disabled (LORA_DEPLOY_ENABLED=false)")
        from .. import lora_deploy

        data, base, active = lora_paths()
        req = body or LoraDeployRequest()
        version = (req.version or "").strip()
        path = (req.path or "").strip()
        if version and path:
            result = await lora_deploy.deploy_lora(
                version=version,
                path=path,
                data_dir=data,
                ollama_host=settings.ollama_host,
                base_model=base,
                model_prefix=settings.lora_ollama_model,
                active_dir=active,
            )
        else:
            result = await lora_deploy.sync_active_from_twin(
                settings.twin_url,
                data_dir=data,
                ollama_host=settings.ollama_host,
                base_model=base,
                model_prefix=settings.lora_ollama_model,
                active_dir=active,
            )
        if not result.get("ok"):
            raise HTTPException(status_code=400, detail=result.get("error") or "deploy failed")
        return result
