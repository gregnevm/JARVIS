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


def test_redact_jarvis_multisegment_key():
    """Власний формат ключа JARVIS (sk-jarvis-…) з внутрішнім дефісом — теж редактиться."""
    key = "sk-jarvis-ABCDEF0123456789ABCDEF0123456789"
    out = default_redactor().redact(f"clone https://x:{key}@example.com/r")
    assert "[REDACTED:secret]" in out
    assert key not in out


def test_redact_aws_access_key():
    r = default_redactor()
    out = r.redact("creds AKIAIOSFODNN7EXAMPLE and ASIAY34FZKBOKMUTVV7A here")
    assert out.count("[REDACTED:secret]") == 2
    assert "AKIAIOSFODNN7EXAMPLE" not in out and "ASIAY34FZKBOKMUTVV7A" not in out


def test_redact_aws_key_no_false_positive():
    # 'AKIA' як звичайне слово (не 20-символьний ключ) лишається недоторканим
    out = default_redactor().redact("AKIA is an Amazon prefix word")
    assert out == "AKIA is an Amazon prefix word"


def test_redact_google_api_key():
    key = "AIzaSy" + "B" * 33  # 'AIza' + 35 -> 39 chars
    out = default_redactor().redact(f"gmaps {key} ok")
    assert "[REDACTED:secret]" in out and key not in out


def test_redact_standalone_jwt():
    jwt = (
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
        ".eyJzdWIiOiIxMjM0NTY3ODkwIn0"
        ".SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
    )
    # без key=value-контексту — спрацьовує саме jwt-правило, не cred_kv
    out = default_redactor().redact(f"received {jwt} from client")
    assert "[REDACTED:secret]" in out and jwt not in out


def test_redact_jwt_no_false_positive_on_dotted_name():
    out = default_redactor().redact("import module.submodule.func")
    assert out == "import module.submodule.func"


def test_redact_bearer_and_credential_kv():
    r = default_redactor()
    bearer = r.redact("Authorization: Bearer eyJhbGciOi.payloadpart.signaturehere")
    assert "Bearer [REDACTED:secret]" in bearer
    kv = r.redact("password=hunter2longvalue")
    assert kv == "password=[REDACTED:secret]"
    assert "hunter2longvalue" not in kv


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


def test_redact_passport_recurses_nested_payload():
    r = default_redactor()
    key = "sk-ABCDEF0123456789abcdef"
    p = Passport(
        kind="note", summary="x", tags=["kind:note"], sensitivity="personal",
        payload={
            "top": key,
            "nested": {"inner": key, "n": 7},
            "lst": [key, {"deep": key}],
        },
    )
    out = r.redact_passport(p)
    assert out.payload["top"] == "[REDACTED:secret]"
    assert out.payload["nested"]["inner"] == "[REDACTED:secret]"
    assert out.payload["nested"]["n"] == 7  # не-рядки лишаються як є
    assert out.payload["lst"][0] == "[REDACTED:secret]"
    assert out.payload["lst"][1]["deep"] == "[REDACTED:secret]"
    assert key not in str(out.payload)


def test_redact_payload_public_recurses():
    # Публічний SSOT redact_payload (реюзається memory-route backstop'ом) —
    # рекурсія на будь-якій глибині, ключі й скаляри недоторкані.
    r = default_redactor()
    key = "sk-ABCDEF0123456789abcdef"
    out = r.redact_payload({"a": key, "b": {"c": [key, 5]}, "n": 0})
    assert out["a"] == "[REDACTED:secret]"
    assert out["b"]["c"][0] == "[REDACTED:secret]"
    assert out["b"]["c"][1] == 5 and out["n"] == 0
    assert key not in str(out)
    assert r.redact_payload({}) == {}


def test_redact_payload_leaves_keys_untouched():
    # Документована поведінка: ключі — це назви полів (структура), не значення;
    # редагуємо лише значення. Пін, щоб зміна дизайну була свідомою.
    r = default_redactor()
    out = r.redact_payload({"4111 1111 1111 1111": "note"})
    assert "4111 1111 1111 1111" in out  # ключ не змінено
    assert out["4111 1111 1111 1111"] == "note"


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
