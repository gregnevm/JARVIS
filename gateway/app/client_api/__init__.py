"""Client-API пакет — стабільний `/api/v1/*` контракт для всіх клієнтів (CL-1)."""

from .router import router

__all__ = ["router"]
