"""Консолідовані HTTP-валідатори (PR#1) — раніше дублювалися в gateway+tools."""
import pytest
from fastapi import HTTPException

from jarvis_core.http_helpers import require_found, require_text


def test_require_text_strips_and_returns():
    assert require_text("  привіт  ") == "привіт"


def test_require_text_default_field_is_text():
    with pytest.raises(HTTPException) as exc:
        require_text("")
    assert exc.value.status_code == 400
    assert exc.value.detail == "text required"


def test_require_text_custom_field():
    with pytest.raises(HTTPException) as exc:
        require_text(None, field="task")
    assert exc.value.detail == "task required"


def test_require_found_passes_value_through():
    rec = {"id": "x"}
    assert require_found(rec, detail="nope") is rec


def test_require_found_raises_404_on_none():
    with pytest.raises(HTTPException) as exc:
        require_found(None, detail="plan not found")
    assert exc.value.status_code == 404
    assert exc.value.detail == "plan not found"
