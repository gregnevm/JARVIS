"""exec_guard: вбудовані правила, профільні правила, fail-closed по збігу."""
from __future__ import annotations

import pytest

from jarvis_core.safety import exec_guard


@pytest.mark.parametrize(
    "code,label",
    [
        ("import os; print(os.environ)", "env-exfiltration"),
        ("v = os.getenv('API_KEY')", "env-exfiltration"),
        ("import subprocess; subprocess.run(['ls'])", "process-spawn"),
        ("os.system('rm -rf /')", "process-spawn"),
        ("import socket", "raw-socket/ffi"),
        ("import ctypes", "raw-socket/ffi"),
        ("open('.env').read()", "secrets-file"),
        ("open('/proc/self/environ')", "secrets-file"),
        ("__import__('os')", "import-bypass"),
    ],
)
def test_builtin_rules_deny(code: str, label: str):
    allowed, reason = exec_guard.screen(code)
    assert not allowed
    assert reason == f"deny:{label}"


@pytest.mark.parametrize(
    "code",
    [
        "print(2 + 2)",
        "import math; print(math.sqrt(16))",
        "data = [x**2 for x in range(10)]; print(sum(data))",
        "",  # порожнє — не наша вісь, валідує code_exec
    ],
)
def test_clean_code_allowed(code: str):
    allowed, reason = exec_guard.screen(code)
    assert allowed
    assert reason == "clean"


def test_case_insensitive():
    allowed, _ = exec_guard.screen("OS.ENVIRON")
    assert not allowed


def test_extra_rules_extend_builtins():
    extra = exec_guard.parse_extra_rules(r"\bpandas\b=no-pandas, \bnumpy\b")
    allowed, reason = exec_guard.screen("import pandas", extra=extra)
    assert not allowed and reason == "deny:no-pandas"
    allowed, reason = exec_guard.screen("import numpy", extra=extra)
    assert not allowed and reason == "deny:profile-rule"
    # вбудовані лишаються чинними разом із extra
    allowed, _ = exec_guard.screen("import socket", extra=extra)
    assert not allowed


def test_parse_extra_rules_skips_invalid_regex():
    rules = exec_guard.parse_extra_rules(r"[unclosed, \bok\b=ok")
    assert rules == ((r"\bok\b", "ok"),)


def test_parse_extra_rules_empty():
    assert exec_guard.parse_extra_rules("") == ()
    assert exec_guard.parse_extra_rules(" , ,") == ()
