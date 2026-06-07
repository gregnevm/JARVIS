"""Спільні валідатори тіла запитів для gateway routes (Platform + WebApp/PS)."""
from __future__ import annotations

from typing import AbstractSet, TypeVar

from fastapi import HTTPException

_T = TypeVar("_T")


def require_text(value: str | None, *, field: str = "text") -> str:
    """Strip і перевірити, що поле непорожнє — інакше 400 `"{field} required"`.

    Узагальнює патерн `x = (body.X or "").strip(); if not x: raise
    HTTPException(status_code=400, detail="X required")`, побайтово (чи майже
    побайтово — лише назва поля різниться) повторений по всьому `gateway/app`:
    `platform/{jobs,plans,workbench,memory}.py` (`text`/`query`),
    `platform/models.py`+`webapp.py` (`version`, той самий promote_lora
    ендпоінт у двох місцях), `webapp_ps.py` (`text`/`code`/`result`).
    Дзеркало `tools/app/routes/_helpers.py::require_text` — той самий патерн,
    але інший сервіс/пакет (немає спільної бібліотеки між `gateway`/`tools`,
    тож дублюємо тонкий хелпер локально)."""
    text = (value or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail=f"{field} required")
    return text


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
    виклику, щоб хелпер не приховував різні дефолти різних ендпоінтів.

    Побіжно виправляє приховану розбіжність: `webapp.py::app_set_mode` НЕ
    нормалізував `body.mode` перед звіркою (на відміну від трьох сусідів) —
    тож `"Agent"`/`" agent "` отримували тут 400, хоча бекенд
    (`tools/app/runtime.py::set_agent_mode`, теж `.lower().strip()`) їх
    прийняв би. Тепер нормалізація уніфікована й однакова всюди."""
    m = (value or "").strip().lower()
    if m not in valid:
        raise HTTPException(status_code=400, detail=f"bad {field}")
    return m


def require_found(value: _T | None, *, detail: str) -> _T:
    """404 `detail`, якщо значення відсутнє — інакше повернути його як є.

    Узагальнює побайтово ідентичний (з різним лише `detail`) патерн
    `rec = await tools.x_plan(...); if rec is None: raise HTTPException(404,
    detail="plan not found"); return rec`, повторений у `platform/plans.py::
    {plans_approve,plans_deny}`. Дженерик через `TypeVar`, бо в принципі може
    повернутись запис будь-якого проксі-ресурсу — generic-параметр усуває
    потребу в `cast`/`Any` на виклику. Дзеркало
    `tools/app/routes/_helpers.py::require_found` — той самий патерн в іншому
    сервісі/пакеті (немає спільної бібліотеки між `gateway`/`tools`)."""
    if value is None:
        raise HTTPException(status_code=404, detail=detail)
    return value
