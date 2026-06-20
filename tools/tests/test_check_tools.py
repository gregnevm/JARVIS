"""run_tests / run_lint — структуровані раннери (CA-3.1 / CA-3.3)."""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from app import toolkit
from app.config import settings
from app.tools import check_tools


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self.store.get(key)

    async def setex(self, key: str, ttl: int, value: str) -> None:
        self.store[key] = value

    async def delete(self, key: str) -> None:
        self.store.pop(key, None)


@pytest.fixture()
def coding_enabled(monkeypatch: pytest.MonkeyPatch) -> FakeRedis:
    monkeypatch.setattr(settings, "enable_computer_use", True)
    monkeypatch.setattr(settings, "enable_coding_tools", True)
    monkeypatch.setattr(settings, "computer_owner_user_ids", "1")
    monkeypatch.setattr(settings, "hostagent_token", "tok")
    fake = FakeRedis()
    monkeypatch.setattr("app.tools.fix_loop.get_redis", lambda: fake)
    return fake


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

async def test_run_tests_pytest_failures_structured(coding_enabled: FakeRedis) -> None:
    with _patch_cli({"stdout": _PYTEST_FAIL, "stderr": "", "code": 1}) as req:
        out = await check_tools.run_tests("pytest", args=["-q"], path="O:/repo", user_id=1)
    sent = req.await_args.kwargs["json"]
    assert sent["exe"] == "pytest" and sent["cwd"] == "O:/repo"
    assert "❌ FAIL" in out
    assert "failed=2" in out and "passed=3" in out and "skipped=1" in out
    assert "test_a.py::test_one" in out and "test_b.py::test_two" in out


async def test_run_tests_pytest_pass(coding_enabled: FakeRedis) -> None:
    with _patch_cli({"stdout": _PYTEST_PASS, "code": 0}):
        out = await check_tools.run_tests("python", args=["-m", "pytest"], user_id=1)
    assert "✅ PASS" in out and "passed=12" in out


async def test_run_tests_pass_with_error_in_captured_log(coding_enabled: FakeRedis) -> None:
    # Регресія: 'N error' у захопленому виводі тесту НЕ має перевертати зелений прогін
    # у FAIL (лічильники беремо зі summary-рядка pytest, не з усього блобу).
    stdout = (
        "tests/test_log.py::test_error_path PASSED\n"
        "----- Captured log call -----\n"
        "ERROR app: 1 error while retrying (expected, handled)\n"
        "=== 5 passed in 0.30s ===\n"
    )
    with _patch_cli({"stdout": stdout, "code": 0}):
        out = await check_tools.run_tests("pytest", args=["-q"], path="O:/repo", user_id=1)
    assert "✅ PASS" in out and "passed=5" in out and "errors=0" in out


async def test_run_tests_quiet_pass_bare_summary_no_frame(coding_enabled: FakeRedis) -> None:
    # Регресія (найважливіший шлях): `pytest -q` на зеленому прогоні друкує ГОЛИЙ
    # підсумок `N passed in Xs` БЕЗ рамки `=`. Tally-слово в captured-виводі
    # (`3 failed attempts`) не має перевертати його у FAIL — ловимо summary за
    # таймінг-хвостом `in <dur>s`, а не за рамкою `=`.
    stdout = "WARN retried 3 failed attempts then recovered\n5 passed in 0.10s\n"
    with _patch_cli({"stdout": stdout, "code": 0}):
        out = await check_tools.run_tests("pytest", args=["-q"], path="O:/repo", user_id=1)
    assert "✅ PASS" in out and "passed=5" in out and "failed=0" in out


async def test_run_tests_ansi_colored_summary_pass(coding_enabled: FakeRedis) -> None:
    # ANSI-кольоровий підсумок (`--color=yes`) не має ламати розпізнавання: рядок
    # обчищається від escape-кодів перед матчем, тож `1 error` у логах не дає FAIL.
    stdout = (
        "ERROR app: 1 error while retrying\n"
        "\x1b[32m============ 2 passed in 0.61s ============\x1b[0m\n"
    )
    with _patch_cli({"stdout": stdout, "code": 0}):
        out = await check_tools.run_tests("pytest", user_id=1)
    assert "✅ PASS" in out and "passed=2" in out and "errors=0" in out


async def test_run_tests_trailing_banner_after_summary(coding_enabled: FakeRedis) -> None:
    # Трейлінг-банер ПІСЛЯ справжнього підсумку (teardown/плагін) не має перебивати
    # лічильники: скануємо знизу, але банер без `in <dur>s` ігнорується.
    stdout = "=== 3 passed in 0.20s ===\n===== teardown: 2 errors flushed =====\n"
    with _patch_cli({"stdout": stdout, "code": 0}):
        out = await check_tools.run_tests("pytest", user_id=1)
    assert "✅ PASS" in out and "passed=3" in out and "errors=0" in out


async def test_run_tests_green_run_hides_captured_failed_line(coding_enabled: FakeRedis) -> None:
    # На зеленому прогоні рядок `FAILED …` у captured-виводі — не справжній провал;
    # `failed:`-блок не показуємо, щоб не плутати модель примарним списком.
    stdout = (
        "tests/test_p.py::t PASSED\n"
        "----- Captured stdout call -----\n"
        "FAILED pkg/test_a.py::t_one - AssertionError\n"
        "=== 6 passed in 0.20s ===\n"
    )
    with _patch_cli({"stdout": stdout, "code": 0}):
        out = await check_tools.run_tests("pytest", user_id=1)
    # raw-хвіст (`---`) і далі ехом містить captured-рядок — це сирий вивід для
    # моделі; пригнічуємо лише СТРУКТУРОВАНИЙ `failed:`-блок над ним.
    assert "✅ PASS" in out and "passed=6" in out
    assert "failed:\n" not in out


async def test_run_tests_rejects_non_runner_exe(coding_enabled: FakeRedis) -> None:
    out = await check_tools.run_tests("rm", args=["-rf", "/"], user_id=1)
    assert "не дозволений" in out


async def test_run_tests_requires_exe(coding_enabled: FakeRedis) -> None:
    out = await check_tools.run_tests("", user_id=1)
    assert "exe" in out.lower()


async def test_run_tests_venv_python_path_allowed(coding_enabled: FakeRedis) -> None:
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

async def test_run_lint_mypy_errors(coding_enabled: FakeRedis) -> None:
    out_blob = "app/x.py:10: error: bad type [arg-type]\nFound 1 error in 1 file\n"
    with _patch_cli({"stdout": out_blob, "code": 1}):
        out = await check_tools.run_lint("mypy", args=["app/"], user_id=1)
    assert "mypy ❌ 1 errors" in out


async def test_run_lint_mypy_success(coding_enabled: FakeRedis) -> None:
    with _patch_cli({"stdout": "Success: no issues found in 80 source files\n", "code": 0}):
        out = await check_tools.run_lint("mypy", args=["app/"], user_id=1)
    assert "mypy ✅ PASS" in out


async def test_run_lint_ruff_issues(coding_enabled: FakeRedis) -> None:
    blob = "app/x.py:1:1: F401 unused import\nFound 1 error.\n"
    with _patch_cli({"stdout": blob, "code": 1}):
        out = await check_tools.run_lint("ruff", args=["check", "."], user_id=1)
    assert "ruff ❌" in out and "1 issues" in out


async def test_run_lint_rejects_non_linter(coding_enabled: FakeRedis) -> None:
    out = await check_tools.run_lint("curl", args=["http://evil"], user_id=1)
    assert "не дозволений" in out


# --- gating + dispatch -------------------------------------------------------

async def test_check_tools_in_schema(coding_enabled: FakeRedis) -> None:
    names = [s["function"]["name"] for s in toolkit.agent_tool_schemas(computer=True)]
    assert "run_tests" in names and "run_lint" in names


async def test_run_tests_denied_for_non_owner(coding_enabled: FakeRedis) -> None:
    out = await toolkit.dispatch("run_tests", {"exe": "pytest"}, user_id=99)
    assert "власник" in out.lower()


# --- no-progress detector (CA-3.4) -------------------------------------------

async def test_run_tests_no_progress_on_repeated_fail(coding_enabled: FakeRedis) -> None:
    # Той самий набір впалих тестів двічі поспіль → підказка «немає прогресу».
    with _patch_cli({"stdout": _PYTEST_FAIL, "code": 1}):
        first = await check_tools.run_tests("pytest", user_id=1)
        second = await check_tools.run_tests("pytest", user_id=1)
    assert "Немає прогресу" not in first  # перший fail — ще не привід зупинятись
    assert "Немає прогресу" in second and "2-й раз" in second


async def test_run_tests_different_fail_resets_counter(coding_enabled: FakeRedis) -> None:
    other_fail = (
        "F\nFAILED tools/tests/test_c.py::test_three - KeyError\n"
        "=== 1 failed, 3 passed in 0.5s ===\n"
    )
    with _patch_cli({"stdout": _PYTEST_FAIL, "code": 1}):
        await check_tools.run_tests("pytest", user_id=1)
    with _patch_cli({"stdout": other_fail, "code": 1}):
        out = await check_tools.run_tests("pytest", user_id=1)
    assert "Немає прогресу" not in out  # інший набір впалих → лічильник скинуто


async def test_run_tests_pass_clears_no_progress_state(coding_enabled: FakeRedis) -> None:
    with _patch_cli({"stdout": _PYTEST_FAIL, "code": 1}):
        await check_tools.run_tests("pytest", user_id=1)
    with _patch_cli({"stdout": _PYTEST_PASS, "code": 0}):
        await check_tools.run_tests("pytest", user_id=1)
    # після PASS той самий fail знову трактується як перший, без підказки
    with _patch_cli({"stdout": _PYTEST_FAIL, "code": 1}):
        out = await check_tools.run_tests("pytest", user_id=1)
    assert "Немає прогресу" not in out


async def test_run_tests_no_progress_for_generic_runner(coding_enabled: FakeRedis) -> None:
    with _patch_cli({"stdout": "build failed: missing symbol\n", "code": 2}):
        first = await check_tools.run_tests("go", args=["test", "./..."], user_id=1)
        second = await check_tools.run_tests("go", args=["test", "./..."], user_id=1)
    assert "Немає прогресу" not in first
    assert "Немає прогресу" in second
