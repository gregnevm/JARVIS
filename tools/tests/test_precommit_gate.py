"""CA-5.5 pre-commit lint gate — turnkey P10 post_tool built-in."""
from __future__ import annotations

from typing import Any

import pytest

from app import hooks, precommit_gate
from app.config import settings


def _enable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "coding_precommit_gate", True)
    monkeypatch.setattr(settings, "coding_precommit_lint_exe", "ruff")
    monkeypatch.setattr(settings, "coding_precommit_lint_args", "check")


def _patch_lint(monkeypatch: pytest.MonkeyPatch, summary: str) -> list[dict[str, Any]]:
    seen: list[dict[str, Any]] = []

    async def _rl(exe, *, args=None, path="", tool="auto", user_id=0):  # noqa: ANN001
        seen.append({"exe": exe, "args": args, "path": path, "user_id": user_id})
        return summary

    monkeypatch.setattr("app.tools.check_tools.run_lint", _rl)
    return seen


async def test_gate_disabled_is_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "coding_precommit_gate", False)
    out = await precommit_gate.run({"tool": "code_edit", "result": "✅ ok"})
    assert out is None


async def test_gate_ignores_non_edit_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable(monkeypatch)
    out = await precommit_gate.run({"tool": "run_tests", "result": "✅ PASS"})
    assert out is None


async def test_gate_appends_lint_after_edit(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable(monkeypatch)
    seen = _patch_lint(monkeypatch, "ruff ❌ 2 issues (exit 1)")
    ctx = {"tool": "code_edit", "result": "Правку застосовано ✅", "user_id": 1}
    out = await precommit_gate.run(ctx)
    assert out is not None
    assert "pre-commit gate (lint)" in out["result"]
    assert "ruff ❌ 2 issues" in out["result"]
    assert out["result"].startswith("Правку застосовано ✅")  # оригінал збережено
    assert seen and seen[0]["exe"] == "ruff" and seen[0]["args"] == ["check"]


async def test_gate_skips_confirm_marker(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable(monkeypatch)
    _patch_lint(monkeypatch, "ruff ✅ PASS")
    out = await precommit_gate.run(
        {"tool": "code_edit", "result": "[[COMPUTER_CONFIRM:abc]] Очікую підтвердження"}
    )
    assert out is None  # правку ще не застосовано → не гейтимо


async def test_gate_skips_dry_run(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable(monkeypatch)
    _patch_lint(monkeypatch, "ruff ✅ PASS")
    out = await precommit_gate.run(
        {"tool": "code_edit_batch", "result": "Dry-run: 2 файл(ів) — diff без застосування 👀"}
    )
    assert out is None


async def test_gate_graceful_on_lint_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable(monkeypatch)

    async def _boom(*a, **k):  # noqa: ANN002, ANN003
        raise RuntimeError("hostagent down")

    monkeypatch.setattr("app.tools.check_tools.run_lint", _boom)
    out = await precommit_gate.run({"tool": "code_edit", "result": "✅ ok"})
    assert out is None  # помилка гейта не валить tool-результат


def test_loader_includes_gate_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "hooks_enabled", True)
    monkeypatch.setattr(settings, "coding_precommit_gate", True)
    hooks.reload_hooks()
    try:
        status = hooks.hook_status()
        assert status["post_tool"] >= 1
    finally:
        monkeypatch.setattr(settings, "coding_precommit_gate", False)
        hooks.reload_hooks()
