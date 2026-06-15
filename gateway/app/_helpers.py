"""Спільні валідатори тіла запитів для gateway routes (Platform + WebApp/PS).

`require_text`/`require_found` консолідовано в `jarvis_core.http_helpers` (PR#1 —
тепер є спільна бібліотека між gateway/tools, тож дублювання знято). Ре-експортуємо
їх тут, щоб ~15 наявних `from ._helpers import ...` лишились робочими (backward compat).
Дефолт `require_text(field="text")` у jarvis_core збігається з історичним gateway —
поведінка й тексти помилок незмінні.

`require_mode` + `AGENT_MODES` лишаються локальними: вони gateway-специфічні (дзеркало
`tools/app/runtime.py::set_agent_mode`); у tools-сервісі цих хелперів немає, тож у
спільну бібліотеку їм не місце.
"""
from __future__ import annotations

from typing import AbstractSet

from fastapi import HTTPException

from jarvis_core.http_helpers import require_found, require_text

__all__ = ["require_text", "require_found", "require_mode", "AGENT_MODES"]


AGENT_MODES = frozenset({"chat", "agent", "hybrid", "computer"})
"""Канонічний набір режимів агента — дзеркало `tools/app/runtime.py::set_agent_mode`
(`if m not in ("chat", "agent", "hybrid", "computer")`). Той самий літерал раніше
дублювався у 4 місцях (`admin_panel.py`, `platform/settings_api.py::_MODES`,
`webapp.py`, рядок-перевірка у `bot/admin.py`) — тепер єдине джерело істини."""


def require_mode(value: str | None, valid: AbstractSet[str], *, field: str = "mode") -> str:
    """Normalize (lower+strip) і перевірити належність множині — інакше 400 `"bad {field}"`.

    Узагальнює патерн `m = (x or "<default>").strip().lower(); if m not in
    {...}: raise HTTPException(400, detail="bad mode")`, побайтово повторений
    (з різними множинами!) у `admin_panel.py::admin_set_mode`,
    `platform/settings_api.py::{settings_flag,settings_mode}`,
    `platform/workbench.py::{workbench_ask,workbench_resume}`, `webapp.py::
    {app_set_flag,app_set_mode}`. Множина передається явно — вона різниться за
    призначенням (`workbench.py` додає `"auto"` для авто-вибору режиму запиту,
    а `settings_flag`/`app_set_flag` перевіряють набір прапорців, не режимів).
    Дефолту немає навмисно — викликач сам вирішує (`value or "<default>"`) до
    виклику, щоб хелпер не приховував різні дефолти різних ендпоінтів."""
    m = (value or "").strip().lower()
    if m not in valid:
        raise HTTPException(status_code=400, detail=f"bad {field}")
    return m
