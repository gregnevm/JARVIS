"""Passport-домен (P9/P10/C1): модель, таксономія тегів, редакція."""
from __future__ import annotations

from jarvis_core.passport import (
    Passport,
    Redactor,
    default_redactor,
    normalize_sensitivity,
    normalize_tags,
    should_store_raw,
    split_tag,
    tags_contain,
)


# --- tags.normalize_tags (P10 + інваріант C1) ---

def test_normalize_adds_kind_tag_first():
    tags = normalize_tags(["topic:rent"], "call")
    assert tags[0] == "kind:call"
    assert "topic:rent" in tags


def test_normalize_lowercases_trims_dedups_preserving_order():
    tags = normalize_tags(["  Person:Mom ", "person:mom", "Topic:Rent"], "note")
    assert tags == ["kind:note", "person:mom", "topic:rent"]


def test_normalize_skips_empty_and_caps_length():
    tags = normalize_tags(["", "   ", "x" * 200], "note")
    assert "kind:note" in tags
    assert all(len(t) <= 80 for t in tags)


def test_normalize_handles_none():
    assert normalize_tags(None, "daily") == ["kind:daily"]


def test_split_tag():
    assert split_tag("person:mom") == ("person", "mom")
    assert split_tag("urgent") == (None, "urgent")
    assert split_tag("KIND:Note")[0] == "kind"


def test_tags_contain_and_semantics():
    tags = ["kind:call", "person:mom", "topic:rent"]
    assert tags_contain(tags, ["person:mom", "topic:rent"]) is True
    assert tags_contain(tags, ["person:dad"]) is False


# --- models / sensitivity ---

def test_normalize_sensitivity_falls_back_to_personal():
    assert normalize_sensitivity("HEALTH") == "health"
    assert normalize_sensitivity("bogus") == "personal"
    assert normalize_sensitivity(None) == "personal"


def test_should_store_raw_blocks_health_finance():
    assert should_store_raw("personal") is True
    assert should_store_raw("public") is True
    assert should_store_raw("health") is False
    assert should_store_raw("finance") is False


def test_passport_to_store_shape():
    p = Passport(kind="note", summary="купив молоко", tags=["kind:note"], source="cli")
    d = p.to_store()
    assert d["kind"] == "note"
    assert d["summary"] == "купив молоко"
    assert d["source"] == "cli"
    assert "payload" in d and d["payload"] == {}


# --- redaction (Strategy) ---

def test_redact_credit_card():
    out = default_redactor().redact("картка 4111 1111 1111 1111 діє")
    assert "[REDACTED:card]" in out
    assert "4111" not in out


def test_redact_iban():
    out = default_redactor().redact("IBAN UA213223130000026007233566001 оплата")
    assert "[REDACTED:iban]" in out


def test_redact_api_secret():
    out = default_redactor().redact("ключ sk-ABCDEF0123456789abcdef тут")
    assert "[REDACTED:secret]" in out
    assert "sk-ABCDEF" not in out


def test_redact_otp_keeps_keyword_masks_digits():
    out = default_redactor().redact("ваш код 482913 для входу")
    assert "[REDACTED:otp]" in out
    assert "482913" not in out
    assert "код" in out  # ключове слово збережено


def test_redact_passport_drops_raw_for_health():
    r = default_redactor()
    p = Passport(
        kind="note", summary="аналізи", tags=["kind:note"],
        sensitivity="health", payload={"raw": "діагноз X"},
    )
    out = r.redact_passport(p)
    assert out.payload == {}  # health → сире не зберігаємо


def test_redact_passport_keeps_redacted_payload_for_personal():
    r = default_redactor()
    p = Passport(
        kind="sms", summary="смс", tags=["kind:sms"],
        sensitivity="personal", payload={"text": "код 482913"},
    )
    out = r.redact_passport(p)
    assert out.payload["text"] == "код [REDACTED:otp]"


def test_custom_rules_override_defaults():
    import re

    from jarvis_core.passport import Rule

    r = Redactor([Rule("digits", re.compile(r"\d+"), "#")])
    assert r.redact("abc 123") == "abc #"


# --- retrieval.format_context_block (consumption, крок 5) ---

def test_format_context_block_joins_summaries():
    from jarvis_core.passport import format_context_block

    out = format_context_block(
        [{"summary": "купив молоко"}, {"summary": "дзвінок мамі"}, {"summary": ""}]
    )
    assert out == "купив молоко | дзвінок мамі"  # порожні пропущено


def test_format_context_block_respects_max_items():
    from jarvis_core.passport import format_context_block

    out = format_context_block([{"summary": str(i)} for i in range(10)], max_items=3)
    assert out == "0 | 1 | 2"
