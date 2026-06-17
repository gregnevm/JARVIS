"""Agent hooks (P10) — pre_turn / post_tool / on_error з `data/hooks/`."""
from __future__ import annotations

import importlib.util
import logging
from pathlib import Path
from typing import Any, Awaitable, Callable

from .config import settings

logger = logging.getLogger("jarvis.tools.hooks")

HookFn = Callable[[dict[str, Any]], Awaitable[dict[str, Any] | None]]

_LOADED: dict[str, list[HookFn]] | None = None


def _hooks_dir() -> Path:
    return Path(settings.data_dir) / "hooks"


def _load_module_hooks(path: Path) -> list[HookFn]:
    spec = importlib.util.spec_from_file_location(f"jarvis_hook_{path.stem}", path)
    if spec is None or spec.loader is None:
        return []
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception as exc:  # noqa: BLE001
        logger.warning("hook load failed %s: %s", path.name, exc)
        return []
    fn = getattr(mod, "run", None)
    if callable(fn):
        return [fn]
    hooks = getattr(mod, "HOOKS", None)
    if isinstance(hooks, list):
        return [h for h in hooks if callable(h)]
    return []


def _ensure_loaded() -> dict[str, list[HookFn]]:
    global _LOADED
    if _LOADED is not None:
        return _LOADED
    out: dict[str, list[HookFn]] = {"pre_turn": [], "post_tool": [], "on_error": []}
    if not settings.hooks_enabled:
        _LOADED = out
        return out
    root = _hooks_dir()
    if root.is_dir():
        mapping = {
            "pre_turn": "pre_turn.py",
            "post_tool": "post_tool.py",
            "on_error": "on_error.py",
        }
        for kind, fname in mapping.items():
            p = root / fname
            if p.is_file():
                out[kind].extend(_load_module_hooks(p))
    # CA-5.5: turnkey built-in pre-commit lint gate (post_tool) за прапором —
    # без копіювання файлів у data/hooks/. Іде ПІСЛЯ user-хуків.
    if settings.coding_precommit_gate:
        from .precommit_gate import run as precommit_run

        out["post_tool"].append(precommit_run)
    _LOADED = out
    return out


def reload_hooks() -> None:
    global _LOADED
    _LOADED = None
    _ensure_loaded()


def hook_status() -> dict[str, Any]:
    loaded = _ensure_loaded()
    return {
        "enabled": settings.hooks_enabled,
        "pre_turn": len(loaded["pre_turn"]),
        "post_tool": len(loaded["post_tool"]),
        "on_error": len(loaded["on_error"]),
        "dir": str(_hooks_dir()),
    }


async def run_pre_turn(ctx: dict[str, Any]) -> dict[str, Any]:
    cur = dict(ctx)
    for fn in _ensure_loaded()["pre_turn"]:
        try:
            out = await fn(cur)
            if isinstance(out, dict):
                cur = out
        except Exception as exc:  # noqa: BLE001
            logger.warning("pre_turn hook error: %s", exc)
    return cur


async def run_post_tool(ctx: dict[str, Any]) -> dict[str, Any]:
    cur = dict(ctx)
    for fn in _ensure_loaded()["post_tool"]:
        try:
            out = await fn(cur)
            if isinstance(out, dict):
                cur = out
        except Exception as exc:  # noqa: BLE001
            logger.warning("post_tool hook error: %s", exc)
    return cur


async def run_on_error(ctx: dict[str, Any]) -> None:
    for fn in _ensure_loaded()["on_error"]:
        try:
            await fn(dict(ctx))
        except Exception as exc:  # noqa: BLE001
            logger.warning("on_error hook error: %s", exc)
