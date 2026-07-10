"""Тести тег-резолвера (P10 addressing, SY-B3.1)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from jarvis_core.passport import (
    ContextQuery,
    Handle,
    ModuleRef,
    context_of,
    resolve,
)

# Заморожений момент для детермінованого `to_search` (без звернень до годинника).
_NOW = datetime(2026, 7, 10, 12, 0, 0, tzinfo=timezone.utc)


# --- resolve: module: → ModuleRef ---

def test_module_tag_resolves_to_moduleref():
    assert resolve("module:scam-shield") == ModuleRef(name="scam-shield")


def test_module_name_is_lowercased_and_trimmed():
    assert resolve("  Module:Scam-Shield  ") == ModuleRef(name="scam-shield")


def test_module_without_name_raises():
    for bad in ("module:", "module:   ", "MODULE:"):
        with pytest.raises(ValueError):
            resolve(bad)


# --- resolve: решта → ContextQuery ---

def test_namespaced_tag_resolves_to_query():
    assert resolve("person:mom") == ContextQuery(tags=("person:mom",))


def test_query_tag_lowercased_whole_string():
    # split_tag lowercase-ить лише неймспейс; резолвер має нормалізувати ЦІЛИЙ
    # тег, інакше `tags @> $4` не матчить збережені lowercased-теги.
    assert resolve("Person:Mom") == ContextQuery(tags=("person:mom",))
    assert resolve("Topic:Rent") == ContextQuery(tags=("topic:rent",))


def test_kind_anchor_tag_is_a_query_not_special_cased():
    # C1 kind-якір лишається звичайним тегом ретриву (не диспатчиться).
    assert resolve("kind:note") == ContextQuery(tags=("kind:note",))


def test_free_tag_resolves_to_query():
    assert resolve("Urgent") == ContextQuery(tags=("urgent",))


def test_unknown_namespace_is_open_closed_query():
    # `capability:` ще не в KNOWN_NAMESPACES — але резолвер не гейтить (P5).
    assert resolve("capability:ocr") == ContextQuery(tags=("capability:ocr",))


def test_multi_colon_module_keeps_split_point():
    # split_tag партиціонить по ПЕРШІЙ двокрапці → module value = "erp:sa".
    assert resolve("module:erp:sa") == ModuleRef(name="erp:sa")


def test_multi_colon_query_tag_preserved_whole():
    assert resolve("topic:a:b") == ContextQuery(tags=("topic:a:b",))


def test_empty_tag_raises():
    for bad in ("", "   ", "\t"):
        with pytest.raises(ValueError):
            resolve(bad)


def test_query_since_days_is_none_by_default():
    q = resolve("person:mom")
    assert isinstance(q, ContextQuery)
    assert q.since_days is None


# --- ContextQuery.to_search ---

def test_to_search_without_since():
    assert resolve("person:mom").to_search(_NOW) == {  # type: ignore[union-attr]
        "tags": ["person:mom"],
        "since": None,
    }


def test_to_search_with_since_is_tz_aware_utc_iso():
    q = context_of("person:mom", days=7)
    out = q.to_search(_NOW)
    assert out["tags"] == ["person:mom"]
    expected = (_NOW - timedelta(days=7)).astimezone(timezone.utc).isoformat()
    assert out["since"] == expected
    # tz-aware ISO round-trips назад до aware datetime.
    assert datetime.fromisoformat(out["since"]).tzinfo is not None


def test_to_search_normalizes_naive_now_to_utc():
    naive = datetime(2026, 7, 10, 12, 0, 0)  # без tzinfo → трактуємо як UTC
    out = ContextQuery(tags=("x",), since_days=1).to_search(naive)
    # Детерміновано: наївний = UTC, НЕ локальна таймзона машини (інакше дрейф).
    assert out["since"] == "2026-07-09T12:00:00+00:00"


def test_negative_since_days_raises():
    with pytest.raises(ValueError):
        ContextQuery(tags=("x",), since_days=-1)
    with pytest.raises(ValueError):
        context_of("person:mom", days=-3)


def test_since_days_zero_is_allowed():
    q = ContextQuery(tags=("x",), since_days=0)
    assert q.to_search(_NOW)["since"] == _NOW.isoformat()


# --- context_of ---

def test_context_of_sets_since_days():
    assert context_of("person:mom", days=30) == ContextQuery(
        tags=("person:mom",), since_days=30
    )


def test_context_of_default_window_is_7():
    assert context_of("topic:rent").since_days == 7


def test_context_of_lowercases_tag():
    assert context_of("Person:Mom").tags == ("person:mom",)


def test_context_of_on_module_tag_returns_query_not_ref():
    # context_of = контекст ПРО модуль → лишається запитом, не диспатчить.
    q = context_of("module:erp-sa", days=1)
    assert isinstance(q, ContextQuery)
    assert q.tags == ("module:erp-sa",)


def test_context_of_empty_raises():
    with pytest.raises(ValueError):
        context_of("  ")


# --- shape-parity з ContextSearchRequest (tags: list, since: str|None) ---

def test_to_search_shape_matches_search_request_contract():
    out = context_of("person:mom", days=3).to_search(_NOW)
    assert set(out.keys()) == {"tags", "since"}
    assert isinstance(out["tags"], list)
    assert all(isinstance(t, str) for t in out["tags"])
    assert isinstance(out["since"], str)


# --- Handle union / immutability ---

def test_handle_union_covers_both():
    assert isinstance(resolve("module:x"), Handle)
    assert isinstance(resolve("person:x"), Handle)


def test_dataclasses_are_frozen():
    with pytest.raises(Exception):
        resolve("module:x").name = "y"  # type: ignore[misc,union-attr]
