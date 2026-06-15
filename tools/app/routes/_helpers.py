"""Спільні helpers для Tools route-модулів.

`require_text`/`require_found` консолідовано в `jarvis_core.http_helpers` (PR#1).
Ре-експортуємо: `require_found` — напряму; `require_text` — через тонкий wrapper,
бо tools історично має дефолт `field="task"` (gateway — `"text"`), і 6 викликів
покладаються на нього (`require_text(body.task)` без явного `field`). Wrapper зберігає
цей дефолт побайтово; решта (`clamp_budget`/`ndjson`/`lora_paths`) — tools-локальні.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jarvis_core.http_helpers import require_found
from jarvis_core.http_helpers import require_text as _require_text

from ..config import settings

__all__ = ["clamp_budget", "require_text", "require_found", "ndjson", "lora_paths"]


def clamp_budget(value: int) -> int:
    """Затиснути запитаний бюджет ітерацій/ролей у `[1, settings.subagent_max_budget]`.

    Узагальнює `max(1, min(body.budget_X, settings.subagent_max_budget))`,
    що повторювалось у `subagents`/`teams` route-модулях."""
    return max(1, min(value, settings.subagent_max_budget))


def require_text(value: str | None, *, field: str = "task") -> str:
    """Strip+непорожнє → 400 `"{field} required"`. tools-дефолт `field="task"`
    (gateway — `"text"`); делегує в `jarvis_core.http_helpers.require_text`."""
    return _require_text(value, field=field)


def ndjson(obj: dict[str, Any]) -> bytes:
    return (json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8")


def lora_paths() -> tuple[Path, str, Path]:
    data = Path(settings.data_dir)
    active = Path(settings.lora_active_dir or (data / "twin" / "lora" / "active"))
    base = (settings.lora_base_model or settings.ollama_model_agent).strip()
    return data, base, active
