"""P10 hooks loader."""
from pathlib import Path

import pytest

from app import hooks


async def test_pre_turn_passthrough(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr(hooks.settings, "data_dir", str(tmp_path))
    monkeypatch.setattr(hooks.settings, "hooks_enabled", True)
    hooks.reload_hooks()
    out = await hooks.run_pre_turn({"user_id": 1, "text": "hello"})
    assert out["text"] == "hello"


async def test_custom_pre_turn_hook(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr(hooks.settings, "data_dir", str(tmp_path))
    monkeypatch.setattr(hooks.settings, "hooks_enabled", True)
    hdir = tmp_path / "hooks"
    hdir.mkdir()
    (hdir / "pre_turn.py").write_text(
        "async def run(ctx):\n    ctx['text'] = ctx['text'].upper()\n    return ctx\n",
        encoding="utf-8",
    )
    hooks.reload_hooks()
    out = await hooks.run_pre_turn({"user_id": 1, "text": "hi"})
    assert out["text"] == "HI"
