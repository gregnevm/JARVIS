"""Kernel-sandbox code_exec: argv-конструкція, fail-closed деградація, rlimits."""
from __future__ import annotations

import subprocess
import sys

from app.config import settings
from app.toolkit import sandbox


def test_build_argv_without_bwrap_is_isolated_python():
    argv = sandbox.build_argv("print(1)", bwrap=None)
    assert argv == [sys.executable, "-I", "-c", "print(1)"]


def test_build_argv_with_bwrap_wraps_and_hardens():
    argv = sandbox.build_argv("print(1)", bwrap="/usr/bin/bwrap")
    assert argv[0] == "/usr/bin/bwrap"
    assert argv[-3:] == ["-I", "-c", "print(1)"]
    # ключові гарантії ізоляції — без мережі, без env, tmpfs-cwd, die-with-parent
    for flag in ("--unshare-all", "--clearenv", "--die-with-parent", "--new-session"):
        assert flag in argv
    # жодного bind робочих тек з секретами/кодом
    assert "/app" not in argv and "/data" not in argv


def test_run_python_fail_closed_when_no_bwrap(monkeypatch):
    monkeypatch.setattr(sandbox, "bwrap_path", lambda: None)
    monkeypatch.setattr(settings, "code_exec_require_sandbox", True)
    assert sandbox.run_python("print(1)") == sandbox.SANDBOX_UNAVAILABLE


def test_run_python_legacy_optout_runs(monkeypatch):
    monkeypatch.setattr(sandbox, "bwrap_path", lambda: None)
    monkeypatch.setattr(settings, "code_exec_require_sandbox", False)
    result = sandbox.run_python("print('ok')")
    assert not isinstance(result, str)
    assert result.stdout.strip() == "ok"


def test_run_python_bwrap_startup_failure_stays_closed(monkeypatch):
    """bwrap є, але не стартує (docker seccomp) → відмова, НЕ тихий фолбек."""
    monkeypatch.setattr(sandbox, "bwrap_path", lambda: "/usr/bin/bwrap")
    monkeypatch.setattr(settings, "code_exec_require_sandbox", True)

    def fake_run(argv, **kwargs):
        return subprocess.CompletedProcess(
            argv, returncode=1, stdout="", stderr="bwrap: setting up uid map: Permission denied"
        )

    monkeypatch.setattr(sandbox.subprocess, "run", fake_run)
    assert sandbox.run_python("print(1)") == sandbox.SANDBOX_UNAVAILABLE


def test_run_python_bwrap_failure_falls_back_when_opted_out(monkeypatch):
    monkeypatch.setattr(sandbox, "bwrap_path", lambda: "/usr/bin/bwrap")
    monkeypatch.setattr(settings, "code_exec_require_sandbox", False)
    calls: list[list[str]] = []

    def fake_run(argv, **kwargs):
        calls.append(list(argv))
        if argv[0] == "/usr/bin/bwrap":
            return subprocess.CompletedProcess(argv, 1, stdout="", stderr="bwrap: failed")
        return subprocess.CompletedProcess(argv, 0, stdout="4\n", stderr="")

    monkeypatch.setattr(sandbox.subprocess, "run", fake_run)
    result = sandbox.run_python("print(2+2)")
    assert not isinstance(result, str)
    assert result.stdout.strip() == "4"
    assert len(calls) == 2 and calls[1][0] == sys.executable


def test_run_python_timeout_message(monkeypatch):
    monkeypatch.setattr(sandbox, "bwrap_path", lambda: None)
    monkeypatch.setattr(settings, "code_exec_require_sandbox", False)
    monkeypatch.setattr(settings, "code_exec_timeout", 0.5)
    assert "Таймаут" in str(sandbox.run_python("while True: pass"))


def test_rlimits_cap_memory(monkeypatch):
    """RLIMIT_AS діє: алокація понад стелю падає всередині процесу."""
    monkeypatch.setattr(sandbox, "bwrap_path", lambda: None)
    monkeypatch.setattr(settings, "code_exec_require_sandbox", False)
    monkeypatch.setattr(settings, "code_exec_memory_mb", 64)
    result = sandbox.run_python("x = bytearray(256 * 1024 * 1024); print('grew')")
    assert not isinstance(result, str)
    assert result.returncode != 0 and "grew" not in (result.stdout or "")
