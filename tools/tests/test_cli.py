"""jarvis-code CLI (CA-6.1/6.2) — парсинг, маршрутизація запитів, форматування."""
from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from app import cli


def _run_dispatch(argv: list[str]) -> tuple[str, dict[str, Any], AsyncMock]:
    ns = cli.build_parser().parse_args(argv)
    with patch("app.cli._post", new_callable=AsyncMock, return_value={"ok": True}) as post:
        import asyncio

        asyncio.run(cli.dispatch(ns))
    return ns.cmd, post.await_args.args[1], post  # (cmd, payload, mock)


def test_run_posts_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JARVIS_USER_ID", "7")
    cmd, payload, post = _run_dispatch(["run", "fix", "the", "bug"])
    assert post.await_args.args[0] == "/agent"
    assert payload == {"user_id": 7, "text": "fix the bug", "mode": "agent"}


def test_plan_posts_code_plan() -> None:
    _cmd, payload, post = _run_dispatch(["plan", "extract helpers"])
    assert post.await_args.args[0] == "/agent/code/plan"
    assert payload["text"] == "extract helpers"


def test_fix_posts_with_runner_args() -> None:
    _cmd, payload, post = _run_dispatch(
        ["fix", "--exe", "pytest", "--path", "/repo", "--max-rounds", "2", "--", "-q", "tests/"]
    )
    assert post.await_args.args[0] == "/agent/code/fix"
    assert payload["exe"] == "pytest" and payload["args"] == ["-q", "tests/"]
    assert payload["path"] == "/repo" and payload["max_rounds"] == 2


def test_review_reads_diff_file(tmp_path: Path) -> None:
    f = tmp_path / "x.diff"
    f.write_text("--- a\n+++ b\n@@ -1 +1 @@\n-x\n+y\n", encoding="utf-8")
    ns = cli.build_parser().parse_args(["review", "--diff-file", str(f)])
    with patch("app.cli._post", new_callable=AsyncMock, return_value={"verdict": "approve"}) as post:
        import asyncio

        asyncio.run(cli.dispatch(ns))
    assert post.await_args.args[0] == "/agent/code/review"
    assert "+y" in post.await_args.args[1]["diff"]


def test_headers_include_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JARVIS_API_KEY", "secret123")
    assert cli._headers()["Authorization"] == "Bearer secret123"


def test_headers_empty_without_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("JARVIS_API_KEY", raising=False)
    assert cli._headers() == {}


def test_base_url_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JARVIS_TOOLS_URL", "http://host:9000/")
    assert cli._base_url() == "http://host:9000"


def test_format_review() -> None:
    out = cli.format_result(
        "review",
        {"verdict": "changes_requested", "summary": "x",
         "findings": [{"severity": "high", "file": "a.py", "line": 3, "comment": "bug"}]},
    )
    assert "changes_requested" in out and "a.py:3" in out and "bug" in out


def test_fix_default_no_confirm_false() -> None:
    _cmd, payload, _post = _run_dispatch(["fix", "--exe", "pytest"])
    assert payload["no_confirm"] is False


def test_fix_apply_flag_sets_no_confirm() -> None:
    # --apply і --no-confirm — синоніми headless-режиму (CA-6.4)
    for flag in ("--no-confirm", "--apply"):
        _cmd, payload, _post = _run_dispatch(["fix", "--exe", "pytest", flag])
        assert payload["no_confirm"] is True


def test_format_fix() -> None:
    out = cli.format_result("fix", {"status": "fixed", "rounds": 2, "report": "✅ PASS"})
    assert "fixed" in out and "rounds=2" in out and "PASS" in out


def test_format_fix_with_review() -> None:
    out = cli.format_result(
        "fix",
        {"status": "fixed", "rounds": 1, "report": "✅ PASS",
         "review": {"verdict": "changes_requested", "summary": "magic", "fix_attempted": True, "tests_after_fix": "pass"}},
    )
    assert "review: changes_requested" in out and "tests pass" in out


def test_fix_review_flag() -> None:
    _cmd, payload, _post = _run_dispatch(["fix", "--exe", "pytest", "--review"])
    assert payload["review"] is True


def test_edit_reads_file_and_posts(tmp_path: Path) -> None:
    f = tmp_path / "m.py"
    f.write_text("x = 1\n", encoding="utf-8")
    ns = cli.build_parser().parse_args(
        ["edit", "--file", str(f), "--instruction", "rename x to y"]
    )
    with patch(
        "app.cli._post",
        new_callable=AsyncMock,
        return_value={"path": str(f), "diff": "d", "proposed": "y = 1\n", "changed": True},
    ) as post:
        import asyncio

        asyncio.run(cli.dispatch(ns))
    assert post.await_args.args[0] == "/agent/code/edit"
    assert post.await_args.args[1]["content"] == "x = 1\n"
    # без --apply файл не чіпаємо
    assert f.read_text(encoding="utf-8") == "x = 1\n"


def test_edit_apply_writes_file(tmp_path: Path) -> None:
    f = tmp_path / "m.py"
    f.write_text("x = 1\n", encoding="utf-8")
    ns = cli.build_parser().parse_args(
        ["edit", "--file", str(f), "--instruction", "rename", "--apply"]
    )
    with patch(
        "app.cli._post",
        new_callable=AsyncMock,
        return_value={"path": str(f), "diff": "d", "proposed": "y = 1\n", "changed": True},
    ):
        import asyncio

        asyncio.run(cli.dispatch(ns))
    assert f.read_text(encoding="utf-8") == "y = 1\n"


def test_main_handles_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx

    async def _boom(*a: Any, **k: Any) -> dict[str, Any]:
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(cli, "_post", _boom)
    rc = cli.main(["run", "hello"])
    assert rc == 1
