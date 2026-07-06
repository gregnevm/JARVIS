"""R3 «Тонкий шлюз»: build_store_event — фінішний паспорт (дві швидкості, редакція)."""
from __future__ import annotations

from jarvis_core.passport import (
    PROVISIONAL_SUMMARY_LEN,
    build_store_event,
    default_redactor,
)


def _build(**kw):
    return build_store_event(user_id=42, org_id="org-1", redactor=default_redactor(), **kw)


def test_fast_path_uses_summary_and_stamps_scope():
    store = _build(kind="worklog", summary="зробив X", tags=["proj:jarvis"])
    assert store["summary"] == "зробив X"
    assert store["user_id"] == 42
    assert store["org_id"] == "org-1"
    assert store["kind"] == "worklog"


def test_raw_path_builds_provisional_summary_and_pending_tag():
    content = "довгий сирий текст " * 30
    store = _build(kind="note", content=content)
    assert store["summary"] == content.strip()[:PROVISIONAL_SUMMARY_LEN]
    assert "pending:summary" in store["tags"]
    assert store["payload"]["raw"] == content.strip()


def test_empty_event_yields_empty_summary():
    store = _build(kind="note")
    assert store["summary"] == ""


def test_redaction_applies_to_summary():
    store = _build(summary="токен sk-abcdef1234567890abcdef1234567890abcd у логах")
    assert "sk-abcdef1234567890abcdef1234567890abcd" not in store["summary"]


def test_default_kind_is_note():
    store = _build(summary="x", kind="   ")
    assert store["kind"] == "note"
