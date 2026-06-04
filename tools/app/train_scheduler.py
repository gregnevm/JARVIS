"""D.4 — чи накопичилось достатньо кураційних прикладів для retrain."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import settings
from .dataset_export import session_stats

_STATE_NAME = "retrain_scheduler.json"


def _state_path() -> Path:
    return Path(settings.data_dir) / "twin" / _STATE_NAME


def load_state() -> dict[str, Any]:
    p = _state_path()
    if not p.is_file():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_state(state: dict[str, Any]) -> None:
    p = _state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def retrain_status(user_id: int | None = None) -> dict[str, Any]:
    """Порівняти curated_turns з порогом і last_export baseline."""
    stats = session_stats(user_id)
    curated = int(stats.get("curated_turns", 0))
    threshold = settings.train_retrain_min_curated
    state = load_state()
    last_at = int(state.get("last_curated_at_export", 0))
    delta = max(0, curated - last_at)
    ready = threshold > 0 and delta >= threshold
    return {
        **stats,
        "retrain_threshold": threshold,
        "last_curated_at_export": last_at,
        "curated_since_export": delta,
        "retrain_ready": ready,
    }


def mark_exported(user_id: int | None = None) -> dict[str, Any]:
    """Після успішного export — зафіксувати baseline для scheduler."""
    stats = session_stats(user_id)
    curated = int(stats.get("curated_turns", 0))
    state = load_state()
    state["last_curated_at_export"] = curated
    save_state(state)
    return retrain_status(user_id)
