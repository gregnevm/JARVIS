"""Спільні HTTP-валідатори тіла запитів для FastAPI-сервісів (gateway + tools).

Консолідація PR#1 (SAAS_DEEP_DIVE §4.1): раніше `require_text`/`require_found`
дублювалися побайтово у `gateway/app/_helpers.py` та `tools/app/routes/_helpers.py`
з коментарем «немає спільної бібліотеки між gateway/tools, тож дублюємо». Тепер
спільна бібліотека є — `jarvis_core`. Обидва сервіси ре-експортують звідси (тонкі
службові wrapper-и зберігають локальні дефолти, де вони різняться: tools-`require_text`
історично має `field="task"`, gateway — `field="text"`).

⚠️ Цей модуль імпортує FastAPI і тому **не** експортується з `jarvis_core/__init__.py`
(офлайн Edge тягне лише `jarvis_core.llm/facade/pipeline` — без FastAPI). Імпортуй явно:
`from jarvis_core.http_helpers import require_text`.
"""
from __future__ import annotations

from typing import TypeVar

from fastapi import HTTPException

_T = TypeVar("_T")


def require_text(value: str | None, *, field: str = "text") -> str:
    """Strip і перевірити, що поле непорожнє — інакше 400 `"{field} required"`.

    Узагальнює патерн `x = (body.X or "").strip(); if not x: raise
    HTTPException(400, detail="X required")`, повторений десятки разів у
    platform/webapp/route-модулях обох сервісів (різниться лише назва поля)."""
    text = (value or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail=f"{field} required")
    return text


def require_found(value: _T | None, *, detail: str) -> _T:
    """404 `detail`, якщо значення відсутнє — інакше повернути його як є.

    Узагальнює побайтово ідентичний (з різним лише `detail`) патерн
    `rec = await store.get_x(id); if rec is None: raise HTTPException(404,
    detail="x not found"); return rec`. Generic через `TypeVar` — тип запису
    різний у кожному викликачі (plan/job/run/skill/team), параметр усуває
    потребу в `cast`/`Any` на місці виклику."""
    if value is None:
        raise HTTPException(status_code=404, detail=detail)
    return value
