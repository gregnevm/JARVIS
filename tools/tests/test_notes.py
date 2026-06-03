"""take_note / recall_notes — персональні нотатки (ізольовані по user_id)."""
from pathlib import Path

from app import toolkit
from app.config import settings


def test_take_and_recall(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    assert toolkit.take_note("купити молоко", user_id=42).startswith("Нотатку збережено")
    assert toolkit.take_note("подзвонити мамі", user_id=42).startswith("Нотатку збережено")
    out = toolkit.recall_notes(42)
    assert "купити молоко" in out
    assert "подзвонити мамі" in out


def test_recall_empty(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    assert toolkit.recall_notes(999) == "Нотаток поки немає."


def test_take_note_empty(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    assert toolkit.take_note("   ", user_id=1) == "Порожня нотатка."


def test_notes_isolated_per_user(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    toolkit.take_note("секрет юзера один", user_id=1)
    assert "секрет" not in toolkit.recall_notes(2)  # юзер 2 не бачить чужих нотаток


async def test_dispatch_routes_notes(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    r = await toolkit.dispatch("take_note", {"text": "через dispatch"}, user_id=7)
    assert r.startswith("Нотатку збережено")
    r2 = await toolkit.dispatch("recall_notes", {}, user_id=7)
    assert "через dispatch" in r2
