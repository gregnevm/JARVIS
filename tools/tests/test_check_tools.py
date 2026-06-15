"""run_tests / run_lint — структуровані раннери (CA-3.1 / CA-3.3)."""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from app import toolkit
from app.config import settings
from app.tools import check_tools


@pytest.fixture()
def coding_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "enable_computer_use", True)
    monkeypatch.setattr(settings, "enable_coding_tools", True)
    monkeypatch.setattr(settings, "computer_owner_user_ids", "1")
    monkeypatch.setattr(settings, "hostagent_token", "tok")


def _patch_cli(rv: dict[str, Any]) -> Any:
    # check_tools._cli → computer._request; мокаємо нижній рівень.
    return patch("app.computer._request", new_callable=AsyncMock, return_value=rv)


_PYTEST_FAIL = (
    "F.F\n"
    "FAILED tools/tests/test_a.py::test_one - AssertionError: nope\n"
    "FAILED tools/tests/test_b.py::test_two - ValueError\n"
    "=== 2 failed, 3 passed, 1 skipped in 1.23s ===\n"
)
_PYTEST_PASS = "....\n=== 12 passed in 0.42s ===\n"


# --- run_tests ---------------------------------------------------------------

async def test_run_tests_pytest_failures_structured(coding_enabled: None) -> None:
    with _patch_cli({"stdout": _PYTEST_FAIL, "stderr": "", "code": 1}) as req:
        out = await check_tools.run_tests("pytest", args=["-q"], path="O:/repo", user_id=1)
    sent = req.await_args.kwargs["json"]
    assert sent["exe"] == "pytest" and sent["cwd"] == "O:/repo"
    assert "❌ FAIL" in out
    assert "failed=2" in out and "passed=3" in out and "skipped=1" in out
    assert "test_a.py::test_one" in out and "test_b.py::test_two" in out


async def test_run_tests_pytest_pass(coding_enabled: None) -> None:
    with _patch_cli({"stdout": _PYTEST_PASS, "code": 0}):
        out = await check_tools.run_tests("python", args=["-m", "pytest"], user_id=1)
    assert "✅ PASS" in out and "passed=12" in out


async def test_run_tests_rejects_non_runner_exe(coding_enabled: None) -> None:
    out = await check_tools.run_tests("rm", args=["-rf", "/"], user_id=1)
    assert "не дозволений" in out


async def test_run_tests_requires_exe(coding_enabled: None) -> None:
    out = await check_tools.run_tests("", user_id=1)
    assert "exe" in out.lower()


async def test_run_tests_venv_python_path_allowed(coding_enabled: None) -> None:
    # повний шлях до venv python — basename 'python.exe' дозволений
    with _patch_cli({"stdout": _PYTEST_PASS, "code": 0}) as req:
        out = await check_tools.run_tests(
            r"O:\repo\.venv\Scripts\python.exe", args=["-m", "pytest"], user_id=1
        )
    assert "✅ PASS" in out
    assert req.await_args.kwargs["json"]["exe"].endswith("python.exe")


async def test_run_tests_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "enable_coding_tools", False)
    monkeypatch.setattr(settings, "enable_computer_use", True)
    out = await check_tools.run_tests("pytest", user_id=1)
    assert "ENABLE_CODING_TOOLS" in out


# --- run_lint ----------------------------------------------------------------

async def test_run_lint_mypy_errors(coding_enabled: None) -> None:
    out_blob = "app/x.py:10: error: bad type [arg-type]\nFound 1 error in 1 file\n"
    with _patch_cli({"stdout": out_blob, "code": 1}):
        out = await check_tools.run_lint("mypy", args=["app/"], user_id=1)
    assert "mypy ❌ 1 errors" in out


async def test_run_lint_mypy_success(coding_enabled: None) -> None:
    with _patch_cli({"stdout": "Success: no issues found in 80 source files\n", "code": 0}):
        out = await check_tools.run_lint("mypy", args=["app/"], user_id=1)
    assert "mypy ✅ PASS" in out


async def test_run_lint_ruff_issues(coding_enabled: None) -> None:
    blob = "app/x.py:1:1: F401 unused import\nFound 1 error.\n"
    with _patch_cli({"stdout": blob, "code": 1}):
        out = await check_tools.run_lint("ruff", args=["check", "."], user_id=1)
    assert "ruff ❌" in out and "1 issues" in out


async def test_run_lint_rejects_non_linter(coding_enabled: None) -> None:
    out = await check_tools.run_lint("curl", args=["http://evil"], user_id=1)
    assert "не дозволений" in out


# --- gating + dispatch -------------------------------------------------------

async def test_check_tools_in_schema(coding_enabled: None) -> None:
    names = [s["function"]["name"] for s in toolkit.agent_tool_schemas(computer=True)]
    assert "run_tests" in names and "run_lint" in names


async def test_run_tests_denied_for_non_owner(coding_enabled: None) -> None:
    out = await toolkit.dispatch("run_tests", {"exe": "pytest"}, user_id=99)
    assert "власник" in out.lower()


# --- no-progress detection (CA-3.4) ------------------------------------------

def test_failure_signature_pass_is_none() -> None:
    assert check_tools.failure_signature("pytest ✅ PASS — passed=12 (exit 0)") is None


def test_failure_signature_non_check_is_none() -> None:
    # помилка раннера / disabled-меседж — не fail, не рахуємо
    assert check_tools.failure_signature("exe обов'язковий (напр. 'pytest').") is None
    assert check_tools.failure_signature("ENABLE_CODING_TOOLS вимкнено") is None


def test_failure_signature_pytest_uses_failed_names() -> None:
    res = check_tools._summarize_pytest(_PYTEST_FAIL, "", 1)
    sig = check_tools.failure_signature(res)
    assert sig is not None and sig.startswith("fail:")
    assert "test_a.py::test_one" in sig and "test_b.py::test_two" in sig


def test_failure_signature_stable_across_timing() -> None:
    a = check_tools._summarize_pytest(_PYTEST_FAIL, "", 1)
    # той самий fail, інший таймінг у хвості → та сама сигнатура
    b = check_tools._summarize_pytest(_PYTEST_FAIL.replace("1.23s", "9.99s"), "", 1)
    assert check_tools.failure_signature(a) == check_tools.failure_signature(b)


def test_failure_signature_lint_verdict() -> None:
    res = check_tools._summarize_lint("mypy", "Found 3 errors in 2 files\n", "", 1)
    assert check_tools.failure_signature(res) == "verdict:mypy ❌ 3 errors (exit 1)"


def test_progress_guard_trips_on_repeat() -> None:
    g = check_tools.ProgressGuard(2)
    assert g.observe("fail:x") is False  # перший fail
    assert g.observe("fail:x") is True   # той самий вдруге → застрягли


def test_progress_guard_resets_on_change_and_pass() -> None:
    g = check_tools.ProgressGuard(2)
    assert g.observe("fail:x") is False
    assert g.observe("fail:y") is False  # інший fail → прогрес, скидання
    assert g.observe("fail:y") is True
    g2 = check_tools.ProgressGuard(2)
    assert g2.observe("fail:x") is False
    assert g2.observe(None) is False     # green між fail → скидання
    assert g2.observe("fail:x") is False


def test_progress_guard_disabled() -> None:
    g = check_tools.ProgressGuard(0)
    assert g.enabled is False
    for _ in range(5):
        assert g.observe("fail:x") is False
