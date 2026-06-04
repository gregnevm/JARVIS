"""Cascade routing: classify → chat | agent | computer (DESIGN §5.3 / PRODUCT 3.4.3)."""
from __future__ import annotations

import re
from dataclasses import dataclass

_URL_RE = re.compile(r"https?://", re.IGNORECASE)
_MATH_RE = re.compile(r"\d\s*[-+*/^]\s*\d")
_COMPUTER_RE = re.compile(
    r"(скріншот|screenshot|скрін\s+екран|"
    r"powershell|pwsh|"
    r"файл\s+на\s+(диск|хост|комп|windows)|"
    r"на\s+(хост|ПК|windows|комп.?ютер)|"
    r"комп.?ютер|"
    r"winget|choco\b|"
    r"каталог\s+[A-Za-z]:\\|"
    r"прочитай\s+файл\s+[A-Za-z]:\\|"
    r"запиши\s+(у\s+)?файл|"
    r"запусти\s+(на\s+)?(хост|комп|windows)|"
    r"docker\s+(ps|compose|logs))",
    re.IGNORECASE,
)
_KW_RE = re.compile(
    r"(знайд|пошук|загугл|google|search|погод|\bкурс\b|новин|обчисл|пораху|"
    r"скільки буде|calculate|відкрий\s+http|нотатк|запиши|занотуй|нагадай|"
    r"згенер|намалю|малюн|картинк|зображен)",
    re.IGNORECASE,
)
_FILE_RE = re.compile(
    r"(parse_file|describe_image|ocr_image|збережено:|надіслав файл|зображення\.)",
    re.IGNORECASE,
)
_BROWSER_RE = re.compile(
    r"(відкрий\s+https?://|browser_open|прочитай\s+сторінк|заголовок\s+сторінк)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class RouteContext:
    agent_mode: str = "hybrid"
    mode_hint: str | None = None
    user_id: int = 0
    enable_computer: bool = False
    computer_allowed: bool = True


def _resolve_hint(hint: str | None) -> str | None:
    h = (hint or "").lower().strip()
    if h in ("chat", "agent", "computer"):
        return h
    return None


def _apply_computer_gate(mode: str, ctx: RouteContext) -> str:
    if mode == "computer" and (not ctx.enable_computer or not ctx.computer_allowed):
        return "agent"
    return mode


def classify_mode(text: str, ctx: RouteContext | None = None) -> str:
    """Повертає chat | agent | computer."""
    c = ctx or RouteContext()
    forced = _resolve_hint(c.mode_hint)
    if forced:
        return _apply_computer_gate(forced, c)

    mode = (c.agent_mode or "hybrid").lower()
    if mode in ("chat", "agent", "computer"):
        return _apply_computer_gate(mode, c)

    t = text or ""
    if c.enable_computer and c.computer_allowed and _COMPUTER_RE.search(t):
        return "computer"
    if c.enable_computer and c.computer_allowed and _BROWSER_RE.search(t):
        return "computer"
    if _FILE_RE.search(t) or _URL_RE.search(t) or _MATH_RE.search(t) or _KW_RE.search(t):
        return "agent"
    return "chat"
