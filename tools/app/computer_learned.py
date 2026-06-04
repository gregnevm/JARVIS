"""Автоматичний whitelist після підтвердження Computer Use (data/computer_learned.json)."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from .config import settings
from .ps_whitelist import extract_ps_cmdlets, parse_whitelist

logger = logging.getLogger("jarvis.tools.computer_learned")

_LEARNED_FILE = "computer_learned.json"


def _path() -> Path:
    return Path(settings.data_dir) / _LEARNED_FILE


def _load_raw() -> dict[str, list[str]]:
    p = _path()
    if not p.is_file():
        return {"ps": [], "cli": []}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("computer_learned read failed: %s", exc)
        return {"ps": [], "cli": []}
    if not isinstance(data, dict):
        return {"ps": [], "cli": []}
    ps = data.get("ps") if isinstance(data.get("ps"), list) else []
    cli = data.get("cli") if isinstance(data.get("cli"), list) else []
    return {
        "ps": [str(x).strip().lower() for x in ps if str(x).strip()],
        "cli": [str(x).strip().lower() for x in cli if str(x).strip()],
    }


def _save(data: dict[str, list[str]]) -> None:
    p = _path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as exc:
        logger.error("computer_learned write failed: %s", exc)


def learned_ps() -> set[str]:
    return set(_load_raw()["ps"])


def learned_cli() -> set[str]:
    return set(_load_raw()["cli"])


def effective_ps_allowed() -> set[str]:
    return parse_whitelist(settings.ps_whitelist) | learned_ps()


def effective_cli_allowed() -> set[str]:
    return parse_whitelist(settings.cli_whitelist) | learned_cli()


def cli_exe_name(exe: str) -> str:
    return (exe or "").strip().split("\\")[-1].split("/")[-1].lower()


def is_ps_trusted(script: str) -> bool:
    """Після першого ✅ повторні PS-скрипти з тими ж cmdlet — без підтвердження."""
    if not settings.computer_auto_trust_learned:
        return False
    cmdlets = extract_ps_cmdlets(script)
    if not cmdlets:
        return False
    learned = learned_ps()
    return all(c in learned for c in cmdlets)


def is_cli_trusted(exe: str) -> bool:
    if not settings.computer_auto_trust_learned:
        return False
    name = cli_exe_name(exe)
    return bool(name) and name in learned_cli()


def learn_from_action(tool: str, args: dict[str, Any]) -> None:
    if not settings.computer_auto_learn_whitelist:
        return
    data = _load_raw()
    changed = False
    if tool == "run_powershell":
        for cmd in extract_ps_cmdlets(str(args.get("script", ""))):
            if cmd not in data["ps"]:
                data["ps"].append(cmd)
                changed = True
    elif tool == "run_cli":
        name = cli_exe_name(str(args.get("exe", "")))
        if name and name not in data["cli"]:
            data["cli"].append(name)
            changed = True
    if changed:
        _save(data)
        logger.info("computer_learned updated: ps=%d cli=%d", len(data["ps"]), len(data["cli"]))
