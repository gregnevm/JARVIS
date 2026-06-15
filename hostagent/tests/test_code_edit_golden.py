"""Golden trace (CA-1.6): code_edit apply → verify → revert round-trip.

Кожен кейс застосовуємо через ту саму логіку, що /fs/edit (search_replace/diff),
звіряємо результат, а тоді ДОВОДИМО оборотність:
  * search_replace: зворотна заміна (new→old) повертає оригінал;
  * усі режими: відновлення з .jarvis_backup (як у проді) повертає оригінал.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import _apply_search_replace, _apply_unified_diff, app

_GOLDEN = json.loads(
    (Path(__file__).parent / "golden" / "code_edit.json").read_text(encoding="utf-8")
)

TOKEN = "test-token-secret"
H = {"X-Hostagent-Token": TOKEN}


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(settings, "token", TOKEN)
    monkeypatch.setattr(settings, "fs_roots", "")
    monkeypatch.setattr(settings, "max_bytes", 100_000)
    monkeypatch.setattr(settings, "edit_max_bytes", 2_000_000)
    return TestClient(app)


def _apply(case: dict) -> str:
    base = case["before"].replace("\r\n", "\n")
    if case["mode"] == "diff":
        return _apply_unified_diff(base, case["diff"])
    out, _ = _apply_search_replace(
        base, case["old_string"], case["new_string"], replace_all=False
    )
    return out


@pytest.mark.parametrize("case", _GOLDEN, ids=lambda c: c["id"])
def test_golden_apply(case: dict) -> None:
    assert _apply(case) == case["after"]


@pytest.mark.parametrize(
    "case", [c for c in _GOLDEN if c["mode"] == "search_replace"], ids=lambda c: c["id"]
)
def test_golden_search_replace_reversible(case: dict) -> None:
    # Зворотна заміна new→old відновлює оригінал (оборотність правки).
    reverted, _ = _apply_search_replace(
        case["after"].replace("\r\n", "\n"),
        case["new_string"],
        case["old_string"],
        replace_all=False,
    )
    assert reverted == case["before"]


@pytest.mark.parametrize("case", _GOLDEN, ids=lambda c: c["id"])
def test_golden_endpoint_apply_and_revert(
    case: dict, client: TestClient, tmp_path: Path
) -> None:
    f = tmp_path / f"{case['id']}.txt"
    f.write_text(case["before"], encoding="utf-8")

    body: dict[str, object] = {"path": str(f), "mode": case["mode"]}
    if case["mode"] == "diff":
        body["diff"] = case["diff"]
    else:
        body["old_string"] = case["old_string"]
        body["new_string"] = case["new_string"]

    r = client.post("/fs/edit", headers=H, json=body)
    assert r.status_code == 200, r.text
    assert f.read_text(encoding="utf-8") == case["after"]

    # Revert: відновлення з backup повертає байт-у-байт оригінал.
    backup = Path(r.json()["backup"])
    assert backup.exists()
    f.write_text(backup.read_text(encoding="utf-8"), encoding="utf-8")
    assert f.read_text(encoding="utf-8") == case["before"]
