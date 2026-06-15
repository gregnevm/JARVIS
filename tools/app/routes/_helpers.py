"""Спільні helpers для Tools route-модулів."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypeVar

from fastapi import HTTPException

from ..config import settings

_T = TypeVar("_T")


def clamp_budget(value: int) -> int:
    """Затиснути запитаний бюджет ітерацій/ролей у `[1, settings.subagent_max_budget]`.

    Узагальнює `max(1, min(body.budget_X, settings.subagent_max_budget))`,
    що повторювалось у `subagents`/`teams` route-модулях."""
    return max(1, min(value, settings.subagent_max_budget))


def require_text(value: str | None, *, field: str = "task") -> str:
    """Strip і перевірити, що поле непорожнє — інакше 400.

    Узагальнює повторюваний патерн `task = (body.task or "").strip(); if not task: raise ...`,
    що зустрічався 6 разів у `cursor`/`orchestrator`/`subagents`/`teams` route-модулях
    (різнилось лише ім'я поля в тексті помилки).
    """
    text = (value or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail=f"{field} required")
    return text


def require_found(value: _T | None, *, detail: str) -> _T:
    """404 `detail`, якщо значення відсутнє — інакше повернути його як є.

    Узагальнює побайтово ідентичний (з різним лише `detail`) патерн
    `rec = await store.get_x(id); if rec is None: raise HTTPException(404,
    detail="x not found"); return rec`, повторений 9 разів — `agent.py`
    (×3: get/approve/deny plan), `bgjobs.py` (×2: get/result), `orchestrator.py`,
    `skills.py`, `subagents.py`, `teams.py`. Дженерик через `TypeVar`, бо тип
    запису різний у кожному модулі (plan/job/run/skill/team) — generic-параметр
    усуває потребу в `cast`/`Any` на виклику."""
    if value is None:
        raise HTTPException(status_code=404, detail=detail)
    return value


def ndjson(obj: dict[str, Any]) -> bytes:
    return (json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8")


def lora_paths() -> tuple[Path, str, Path]:
    data = Path(settings.data_dir)
    active = Path(settings.lora_active_dir or (data / "twin" / "lora" / "active"))
    base = (settings.lora_base_model or settings.ollama_model_agent).strip()
    return data, base, active
