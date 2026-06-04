"""Персональний профіль користувача (стиль, мова, табу) — data/profiles/{id}.json."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from .config import settings

logger = logging.getLogger("jarvis.tools.profile")

_MAX_FIELD = 500


def _path(user_id: int) -> Path:
    root = Path(settings.data_dir) / "profiles"
    root.mkdir(parents=True, exist_ok=True)
    return root / f"{int(user_id)}.json"


def load_profile(user_id: int) -> dict[str, Any]:
    p = _path(user_id)
    if not p.is_file():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("profile read %s: %s", user_id, exc)
        return {}


def save_profile(user_id: int, patch: dict[str, Any]) -> dict[str, Any]:
    cur = load_profile(user_id)
    for key in ("style", "language", "taboos", "notes"):
        if key in patch and patch[key] is not None:
            cur[key] = str(patch[key])[:_MAX_FIELD].strip()
    _path(user_id).write_text(
        json.dumps(cur, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return cur


def profile_prompt_block(user_id: int) -> str:
    """Фрагмент для system prompt (порожній якщо немає профілю)."""
    p = load_profile(user_id)
    if not p:
        return ""
    parts: list[str] = []
    if p.get("language"):
        parts.append(f"Мова відповідей: {p['language']}.")
    if p.get("style"):
        parts.append(f"Стиль: {p['style']}.")
    if p.get("taboos"):
        parts.append(f"Не роби / не згадуй: {p['taboos']}.")
    if p.get("notes"):
        parts.append(f"Додатково: {p['notes']}.")
    if not parts:
        return ""
    return " Профіль користувача: " + " ".join(parts)
