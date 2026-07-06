"""Юніт-тести для app/_helpers.py — спільних валідаторів тіла запитів.

Модуль використовується у 15 файлах (`platform/*`, `bot/*`, `webapp*`,
`admin_panel.py`), але не мав ЖОДНОГО прямого тесту — лише непряме покриття
через інтеграційні тести роутів. Прямі юніт-тести фіксують точний контракт
(нормалізація, статус-коди, точний `detail`), незалежно від конкретних
місць виклику — і ловлять регресію в самому хелпері, а не лише там, де
випадково є route-тест."""
from __future__ import annotations

import pytest
from app._helpers import AGENT_MODES, require_found, require_mode, require_text
from fastapi import HTTPException

# --- require_text ---

def test_require_text_strips_and_returns():
    assert require_text("  привіт  ") == "привіт"


def test_require_text_rejects_empty_with_default_field():
    with pytest.raises(HTTPException) as exc:
        require_text("")
    assert exc.value.status_code == 400
    assert exc.value.detail == "text required"


def test_require_text_rejects_whitespace_only():
    with pytest.raises(HTTPException) as exc:
        require_text("   \n\t  ")
    assert exc.value.status_code == 400
    assert exc.value.detail == "text required"


def test_require_text_rejects_none():
    with pytest.raises(HTTPException) as exc:
        require_text(None)
    assert exc.value.status_code == 400


def test_require_text_uses_custom_field_name_in_detail():
    with pytest.raises(HTTPException) as exc:
        require_text("  ", field="query")
    assert exc.value.detail == "query required"


# --- AGENT_MODES ---

def test_agent_modes_canonical_set():
    assert AGENT_MODES == frozenset({"chat", "agent", "hybrid", "computer"})


# --- require_mode ---

def test_require_mode_normalizes_case_and_whitespace():
    assert require_mode("  Agent ", AGENT_MODES) == "agent"


def test_require_mode_accepts_valid_value():
    assert require_mode("hybrid", AGENT_MODES) == "hybrid"


def test_require_mode_rejects_invalid_with_default_field():
    with pytest.raises(HTTPException) as exc:
        require_mode("turbo", AGENT_MODES)
    assert exc.value.status_code == 400
    assert exc.value.detail == "bad mode"


def test_require_mode_rejects_none_as_empty_string():
    with pytest.raises(HTTPException) as exc:
        require_mode(None, AGENT_MODES)
    assert exc.value.status_code == 400


def test_require_mode_uses_custom_field_name_in_detail():
    with pytest.raises(HTTPException) as exc:
        require_mode("nope", frozenset({"on", "off"}), field="flag")
    assert exc.value.detail == "bad flag"


def test_require_mode_respects_caller_supplied_set():
    valid = frozenset({"on", "off", "auto"})
    assert require_mode("AUTO", valid) == "auto"
    with pytest.raises(HTTPException):
        require_mode("computer", valid)  # дійсний AGENT_MODES, але не в цій множині


# --- require_found ---

def test_require_found_returns_value_when_present():
    assert require_found({"id": "p1"}, detail="plan not found") == {"id": "p1"}


def test_require_found_returns_falsy_but_non_none_value():
    # 0 / "" / [] — не None, тож мають повертатись як є (не трактуються як "не знайдено")
    assert require_found(0, detail="x not found") == 0
    assert require_found("", detail="x not found") == ""
    assert require_found([], detail="x not found") == []


def test_require_found_raises_404_with_given_detail_when_none():
    with pytest.raises(HTTPException) as exc:
        require_found(None, detail="plan not found")
    assert exc.value.status_code == 404
    assert exc.value.detail == "plan not found"
