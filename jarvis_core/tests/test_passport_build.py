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


# --- C1-інваріант приватності: health/finance — сире НІКОЛИ не персиститься ---
# (AGENTS §6 / models.should_store_raw). Regression-lock на порядок
# excerpt→redact у build_store_event: майбутній рефактор не має протягнути
# PAN/IBAN у context_events cleartext ні через payload, ні через summary.

def test_raw_speed_finance_drops_raw_payload_and_redacts_summary():
    # Картка у перших 240 символах content, raw-швидкість (лише content, без summary).
    content = "оплата карткою 4111 1111 1111 1111 за переказ " * 2
    store = _build(kind="expense", content=content, sensitivity="finance")
    assert store["payload"] == {}                      # raw не персиститься (should_store_raw=False)
    assert "4111 1111 1111 1111" not in store["summary"]
    assert "[REDACTED:card]" in store["summary"]       # провізорний excerpt пройшов редакцію
    assert "4111 1111 1111 1111" not in str(store)     # сира картка не вижила ніде в сторі


def test_raw_speed_health_drops_explicit_payload():
    # Навіть явно переданий payload прибирається для health.
    store = _build(kind="note", content="аналіз крові", sensitivity="health",
                   payload={"attachment": "secret"})
    assert store["payload"] == {}
    assert store["summary"] == "аналіз крові"


def test_raw_speed_finance_iban_redacted_in_summary():
    content = "рахунок UA213223130000026007233566001 поповнено"
    store = _build(kind="note", content=content, sensitivity="finance")
    assert store["payload"] == {}
    assert "[REDACTED:iban]" in store["summary"]
    assert "UA213223130000026007233566001" not in str(store)


def test_raw_speed_finance_payload_drop_is_sole_guard_beyond_excerpt():
    # Картка ЗА межами 240-символьного excerpt-у: summary її фізично не містить,
    # тож редакція summary тут ні до чого — єдиний захист це payload-drop. Ізолює
    # інваріант «сире НІКОЛИ не персиститься» від summary-редакції (майбутній
    # рефактор, що прибере drop, але лишить summary-редакцію, впаде саме тут).
    card = "4111 1111 1111 1111"
    content = ("безпечний префікс " * 20) + "решта: картка " + card
    assert len(("безпечний префікс " * 20)) > PROVISIONAL_SUMMARY_LEN  # картка поза excerpt
    store = _build(kind="expense", content=content, sensitivity="finance")
    assert store["payload"] == {}                      # payload-drop — єдиний захист тут
    assert card not in store["summary"]                # excerpt обрізав картку взагалі
    assert card not in str(store)                      # і ніде в сторі


def test_personal_sensitivity_keeps_raw_but_still_redacts_secret():
    # Контраст: personal → raw зберігається (should_store_raw=True), але секрет
    # у ньому все одно редагується (payload не «голий»).
    content = "ключ sk-abcdef1234567890abcdef1234567890abcd у нотатці " * 3
    store = _build(kind="note", content=content, sensitivity="personal")
    assert store["payload"]["raw"]                       # сире збережено для personal
    assert "sk-abcdef1234567890abcdef1234567890abcd" not in str(store)
