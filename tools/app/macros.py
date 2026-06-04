"""Remote macros — іменовані PS/CLI скрипти без LLM."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from .config import settings

logger = logging.getLogger("jarvis.tools.macros")

_MACROS_FILE = "macros.json"


def _path() -> Path:
    return Path(settings.data_dir) / _MACROS_FILE


def _default_macros() -> dict[str, Any]:
    return {
        "deploy": {
            "description": "git pull + docker compose up -d",
            "type": "cli",
            "exe": "docker",
            "args": ["compose", "up", "-d", "--build"],
            "cwd": None,
        },
        "stack-status": {
            "description": "docker compose ps",
            "type": "cli",
            "exe": "docker",
            "args": ["compose", "ps"],
            "cwd": None,
        },
    }


def load_macros() -> dict[str, Any]:
    p = _path()
    if not p.is_file():
        return _default_macros()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else _default_macros()
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("macros read failed: %s", exc)
        return _default_macros()


def save_macros(data: dict[str, Any]) -> None:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def list_macros() -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for name, spec in sorted(load_macros().items()):
        if not isinstance(spec, dict):
            continue
        out.append({"name": name, "description": str(spec.get("description", ""))})
    return out


async def run_macro(name: str, user_id: int) -> str:
    from . import computer

    macros = load_macros()
    spec = macros.get(name.strip().lower())
    if not spec or not isinstance(spec, dict):
        return f"Макрос '{name}' не знайдено. /macro list"
    mtype = str(spec.get("type", "powershell")).lower()
    if mtype == "cli":
        return await computer.run_cli(
            str(spec.get("exe", "")),
            [str(a) for a in (spec.get("args") or [])],
            str(spec.get("cwd", "")) or None,
            user_id=user_id,
        )
    return await computer.run_powershell(str(spec.get("script", "")), user_id=user_id)
