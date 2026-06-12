"""T4 screen input — type, hotkey, scroll (Windows PowerShell + SendKeys)."""
from __future__ import annotations

import json
import re

_SENDKEYS_SPECIAL = re.compile(r"[+^%~(){}\[\]]")


def _sendkeys_literal(text: str) -> str:
    """Escape text for SendKeys."""
    out: list[str] = []
    for ch in text:
        if ch == "\n":
            out.append("{ENTER}")
        elif ch == "\r":
            continue
        elif ch == "\t":
            out.append("{TAB}")
        elif _SENDKEYS_SPECIAL.search(ch):
            out.append("{" + ch + "}")
        else:
            out.append(ch)
    return "".join(out)


def build_type_ps(text: str, interval_ms: int = 0) -> str:
    """Type text via SendKeys; long text via clipboard paste."""
    interval_ms = max(0, min(int(interval_ms), 500))
    if len(text) > 80:
        escaped = json.dumps(text)
        delay = f"Start-Sleep -Milliseconds {interval_ms}; " if interval_ms else ""
        return (
            f"$t = {escaped}; Add-Type -AssemblyName System.Windows.Forms; "
            f"[System.Windows.Forms.Clipboard]::SetText($t); "
            f"{delay}"
            "Add-Type -AssemblyName System.Windows.Forms; "
            "[System.Windows.Forms.SendKeys]::SendWait('^v')"
        )
    literal = _sendkeys_literal(text)
    escaped = json.dumps(literal)
    delay = f"Start-Sleep -Milliseconds {interval_ms}; " if interval_ms else ""
    return (
        f"$k = {escaped}; Add-Type -AssemblyName System.Windows.Forms; "
        f"{delay}"
        "[System.Windows.Forms.SendKeys]::SendWait($k)"
    )


_KEY_MAP: dict[str, str] = {
    "enter": "{ENTER}",
    "return": "{ENTER}",
    "tab": "{TAB}",
    "esc": "{ESC}",
    "escape": "{ESC}",
    "space": " ",
    "backspace": "{BACKSPACE}",
    "delete": "{DELETE}",
    "del": "{DELETE}",
    "up": "{UP}",
    "down": "{DOWN}",
    "left": "{LEFT}",
    "right": "{RIGHT}",
    "home": "{HOME}",
    "end": "{END}",
    "pageup": "{PGUP}",
    "pagedown": "{PGDN}",
    "f1": "{F1}",
    "f2": "{F2}",
    "f3": "{F3}",
    "f4": "{F4}",
    "f5": "{F5}",
    "f6": "{F6}",
    "f7": "{F7}",
    "f8": "{F8}",
    "f9": "{F9}",
    "f10": "{F10}",
    "f11": "{F11}",
    "f12": "{F12}",
}


def build_hotkey_ps(keys: list[str]) -> str:
    """Map ['ctrl','s'] -> ^s, ['alt','tab'] -> %{TAB}."""
    mods = ""
    main = ""
    for raw in keys:
        k = (raw or "").strip().lower()
        if not k:
            continue
        if k in ("ctrl", "control"):
            mods += "^"
        elif k == "alt":
            mods += "%"
        elif k == "shift":
            mods += "+"
        elif k in _KEY_MAP:
            main = _KEY_MAP[k]
        elif len(k) == 1:
            main = k
        else:
            main = "{" + k.upper() + "}"
    seq = mods + main
    escaped = json.dumps(seq)
    return (
        "Add-Type -AssemblyName System.Windows.Forms; "
        f"[System.Windows.Forms.SendKeys]::SendWait({escaped})"
    )


def build_scroll_ps(clicks: int, x: int | None = None, y: int | None = None) -> str:
    """Scroll wheel at optional position. clicks: positive=up, negative=down."""
    clicks = max(-50, min(int(clicks), 50))
    delta = clicks * 120
    move = ""
    if x is not None and y is not None:
        move = f"""
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class WinMouse {{
  [DllImport("user32.dll")] public static extern bool SetCursorPos(int X, int Y);
  [DllImport("user32.dll")] public static extern void mouse_event(uint f, uint dx, uint dy, uint d, uint e);
}}
"@
[WinMouse]::SetCursorPos({int(x)}, {int(y)}) | Out-Null
Start-Sleep -Milliseconds 50
""".strip()
    return (
        move
        + f"""
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class WinMouse {{
  [DllImport("user32.dll")] public static extern void mouse_event(uint f, uint dx, uint dy, uint d, uint e);
}}
"@
[WinMouse]::mouse_event(0x0800, 0, 0, {delta}, 0)
""".strip()
    )
