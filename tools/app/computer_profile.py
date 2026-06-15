"""COMPUTER_PROFILE — пресети tier для Agent Mode (AM-0.3)."""
from __future__ import annotations

from typing import Any, Literal

from .config import settings

ProfileName = Literal["safe", "standard", "full"]
_VALID: frozenset[str] = frozenset({"safe", "standard", "full"})

_TIER_BY_TOOL: dict[str, str] = {
    "run_powershell": "T0",
    "fs_list": "T0",
    "fs_read": "T0",
    "fs_write": "T0",
    "code_edit": "T1",
    "code_edit_batch": "T1",
    "rename_symbol": "T1",
    "capture_screenshot": "T0",
    "see_screen": "T0",
    "clipboard_read": "T0",
    "clipboard_write": "T0",
    "cursor_task": "T0",
    "continue_dev": "T0",
    "run_cli": "T1",
    "browser_open": "T2",
    "browser_read": "T2",
    "browser_click": "T2",
    "browser_fill": "T2",
    "browser_eval": "T2",
    "window_list": "T3",
    "window_focus": "T3",
    "uia_invoke": "T3",
    "screen_click": "T4",
    "screen_type": "T4",
    "screen_hotkey": "T4",
    "screen_scroll": "T4",
}


def allows_screen_input() -> bool:
    """T4 keyboard/mouse input (full profile)."""
    return allows_screen_click()


def normalize_profile(raw: str | None = None) -> ProfileName:
    p = (raw if raw is not None else settings.computer_profile or "safe").lower().strip()
    if p not in _VALID:
        return "safe"
    return p  # type: ignore[return-value]


def allows_browser() -> bool:
    if normalize_profile() == "safe":
        return False
    return settings.enable_browser


def allows_uia() -> bool:
    return normalize_profile() in ("standard", "full")


def allows_screen_click() -> bool:
    return normalize_profile() == "full"


def allows_see_screen() -> bool:
    return (
        normalize_profile() in ("standard", "full")
        and bool(settings.ollama_model_vision)
        and settings.computer_auto_vision
    )


def profile_summary() -> str:
    p = normalize_profile()
    if p == "safe":
        return "safe (T0/T1: PS, CLI, FS, screenshot)"
    if p == "standard":
        return "standard (+ T2 browser, T3 UIA, see_screen)"
    return "full (+ T4 screen_click, type, hotkey, scroll)"


def computer_tool_names(*, computer: bool = True) -> set[str]:
    """Імена computer-tools з урахуванням профілю."""
    if not computer or not settings.enable_computer_use:
        return set()
    names = {
        "run_powershell",
        "run_cli",
        "fs_list",
        "fs_read",
        "fs_write",
        "capture_screenshot",
        "clipboard_read",
        "clipboard_write",
    }
    if settings.cursor_tasks_enabled:
        names.add("cursor_task")
    if settings.enable_continue_dev:
        names.add("continue_dev")
    if settings.enable_coding_tools:
        names.add("code_edit")
        names.add("code_edit_batch")
        names.add("rename_symbol")
    if allows_see_screen():
        names.add("see_screen")
    if allows_uia():
        names.update({"window_list", "window_focus", "uia_invoke"})
    if allows_screen_input():
        names.update({"screen_click", "screen_type", "screen_hotkey", "screen_scroll"})
    if allows_browser():
        names.update(
            {
                "browser_open",
                "browser_read",
                "browser_click",
                "browser_fill",
                "browser_eval",
            }
        )
    return names


def format_tools_prompt_block(*, computer: bool = True) -> str:
    """Рядок для system_computer: доступні tools по tier."""
    names = computer_tool_names(computer=computer)
    if not names:
        return "Computer Use вимкнено."
    by_tier: dict[str, list[str]] = {}
    for name in sorted(names):
        tier = _TIER_BY_TOOL.get(name, "T0")
        by_tier.setdefault(tier, []).append(name)
    parts = [f"{tier}: {', '.join(by_tier[tier])}" for tier in sorted(by_tier)]
    return f"Доступні інструменти ({profile_summary()}): " + "; ".join(parts) + "."


def tier_for_tool(name: str) -> str:
    return _TIER_BY_TOOL.get(name, "T0")


def profile_status() -> dict[str, Any]:
    p = normalize_profile()
    return {
        "computer_profile": p,
        "profile_summary": profile_summary(),
        "allows_browser": allows_browser(),
        "allows_uia": allows_uia(),
        "allows_screen_click": allows_screen_click(),
        "allows_screen_input": allows_screen_input(),
        "allows_see_screen": allows_see_screen(),
    }
