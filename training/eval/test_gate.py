"""gate: task-success-вимір LoRA-promote (in-process, fail-closed, back-compat)."""
from __future__ import annotations

import sys
from pathlib import Path

_EVAL_DIR = Path(__file__).resolve().parent
if str(_EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(_EVAL_DIR))

import gate  # noqa: E402
import task_success  # noqa: E402


def test_run_task_success_gate_pass(monkeypatch):
    monkeypatch.setattr(task_success, "run_all", lambda *a, **k: [{"id": "x", "ok": True, "latency_ms": 5, "reason": "ok"}])
    passed, pct, report = gate.run_task_success_gate(90.0)
    assert passed and pct == 100.0 and "task-success" in report


def test_run_task_success_gate_fail_below_threshold(monkeypatch):
    monkeypatch.setattr(task_success, "run_all", lambda *a, **k: [
        {"id": "a", "ok": True, "latency_ms": 5, "reason": "ok"},
        {"id": "b", "ok": False, "latency_ms": 5, "reason": "boom"},
    ])
    passed, pct, _ = gate.run_task_success_gate(90.0)
    assert not passed and pct == 50.0


def test_run_task_success_gate_fail_closed_on_stack_error(monkeypatch):
    def _boom(*a, **k):
        raise ConnectionError("stack down")

    monkeypatch.setattr(task_success, "run_all", _boom)
    passed, pct, report = gate.run_task_success_gate(90.0)
    assert not passed and pct == 0.0 and "run failed" in report


def test_gate_main_task_success_dimension_blocks_promote(monkeypatch, tmp_path, capsys):
    """Формат зелений, але task-success нижче порогу → GATE FAIL (exit 4)."""
    holdout = tmp_path / "h.jsonl"
    holdout.write_text('{"conversations":[{"from":"human","value":"x"},{"from":"gpt","value":"y"}]}\n')

    # run_eval subprocess → фейкаємо: формат 100%
    import subprocess as _sp

    class _FakeProc:
        returncode = 0
        stdout = "format pass: 1/1 (100.0%)\n"
        stderr = ""

    monkeypatch.setattr(_sp, "run", lambda *a, **k: _FakeProc())
    monkeypatch.setattr(task_success, "run_all", lambda *a, **k: [
        {"id": "sec", "ok": False, "latency_ms": 1, "reason": "guard regressed"},
    ])
    monkeypatch.setattr(sys, "argv", [
        "gate.py", "--holdout", str(holdout), "--with-task-success", "--task-success-min-pct", "90",
    ])
    assert gate.main() == 4
    assert "GATE FAIL: task-success" in capsys.readouterr().err


def test_gate_main_task_success_pass_promotes(monkeypatch, tmp_path, capsys):
    holdout = tmp_path / "h.jsonl"
    holdout.write_text('{"conversations":[{"from":"human","value":"x"},{"from":"gpt","value":"y"}]}\n')
    import subprocess as _sp

    class _FakeProc:
        returncode = 0
        stdout = "format pass: 1/1 (100.0%)\n"
        stderr = ""

    monkeypatch.setattr(_sp, "run", lambda *a, **k: _FakeProc())
    monkeypatch.setattr(task_success, "run_all", lambda *a, **k: [
        {"id": "ok", "ok": True, "latency_ms": 1, "reason": "ok"},
    ])
    monkeypatch.setattr(sys, "argv", [
        "gate.py", "--holdout", str(holdout), "--with-task-success",
    ])
    assert gate.main() == 0
    assert "task-success 100.0%" in capsys.readouterr().out


def test_gate_main_backcompat_no_task_success(monkeypatch, tmp_path, capsys):
    """Без --with-task-success поведінка незмінна (лише формат)."""
    holdout = tmp_path / "h.jsonl"
    holdout.write_text('{"conversations":[{"from":"human","value":"x"},{"from":"gpt","value":"y"}]}\n')
    import subprocess as _sp

    class _FakeProc:
        returncode = 0
        stdout = "format pass: 1/1 (100.0%)\n"
        stderr = ""

    monkeypatch.setattr(_sp, "run", lambda *a, **k: _FakeProc())
    monkeypatch.setattr(sys, "argv", ["gate.py", "--holdout", str(holdout)])
    assert gate.main() == 0
    assert "GATE OK (format 100.0%)" in capsys.readouterr().out
