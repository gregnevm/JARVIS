#!/usr/bin/env python3
"""Correctness gate (C.4): format eval + optional LLM-as-judge + optional task-success
before LoRA promote.

  python training/eval/gate.py --holdout data/twin/export/sharegpt_holdout.jsonl
  python training/eval/gate.py --holdout ... --min-pass-pct 95
  python training/eval/gate.py --holdout ... --with-judge --judge-min-pass-pct 90
  python training/eval/gate.py --holdout ... --with-task-success --task-success-min-pct 90

Task-success (`docs/COMPETITIVE_ANALYSIS.md` §3.8): промоушен LoRA має залежати
не лише від формату/стилю (run_eval), а й від КОРИСНОСТІ — чи live-стек досі
проходить end-state сценарії (task_success.py). Замикає петлю самовдосконалення
на результат, а не на стиль. Потребує піднятого стека (як task_success).
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

_EVAL_DIR = Path(__file__).resolve().parent
if str(_EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(_EVAL_DIR))


def _parse_pct(stdout: str, label: str) -> float | None:
    for line in stdout.splitlines():
        if label in line and "(" in line:
            frag = line.split("(")[-1].replace("%)", "").strip()
            try:
                return float(frag)
            except ValueError:
                continue
    return None


def run_task_success_gate(min_pct: float, *, only: str = "") -> tuple[bool, float, str]:
    """In-process прогін task_success проти live-стека → (passed, pct, report).

    Імпорт-і-виклик (не subprocess) — реюз API task_success і тестовність через
    monkeypatch `run_all` без мережі. Виняток імпорту/збою → (False, 0, reason)
    (fail-closed: не можемо довести користь → не промоутимо)."""
    try:
        import task_success
    except ImportError as exc:  # pragma: no cover — захист від зламаного шляху
        return False, 0.0, f"task_success import failed: {exc}"
    try:
        results = task_success.run_all(task_success.load_scenarios(), only=only)
    except Exception as exc:  # noqa: BLE001 — будь-який збій стека = fail-closed
        return False, 0.0, f"task_success run failed: {exc}"
    pct, report = task_success.summarize(results)
    return pct >= min_pct, pct, report


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--holdout", type=Path, required=True)
    ap.add_argument("--min-pass-pct", type=float, default=100.0)
    ap.add_argument("--with-judge", action="store_true")
    ap.add_argument("--judge-min-pass-pct", type=float, default=90.0)
    ap.add_argument("--judge-model", default="")
    ap.add_argument("--ollama-url", default="")
    ap.add_argument("--judge-sample", type=int, default=0)
    ap.add_argument("--with-task-success", action="store_true",
                    help="Також вимагати проходження task_success проти live-стека")
    ap.add_argument("--task-success-min-pct", type=float, default=90.0)
    args = ap.parse_args()
    if not args.holdout.is_file():
        print(f"missing: {args.holdout}", file=sys.stderr)
        return 1
    script = Path(__file__).resolve().parent / "run_eval.py"
    cmd = [sys.executable, str(script), "--dataset", str(args.holdout)]
    if args.with_judge:
        cmd.append("--judge")
        if args.judge_model:
            cmd.extend(["--judge-model", args.judge_model])
        if args.ollama_url:
            cmd.extend(["--ollama-url", args.ollama_url])
        if args.judge_sample:
            cmd.extend(["--judge-sample", str(args.judge_sample)])
    proc = subprocess.run(cmd, capture_output=True, text=True)
    print(proc.stdout, end="")
    if proc.stderr:
        print(proc.stderr, file=sys.stderr, end="")
    if proc.returncode not in (0, 3):
        print("GATE FAIL: eval error", file=sys.stderr)
        return proc.returncode or 1

    fmt_pct = _parse_pct(proc.stdout, "format pass:")
    if fmt_pct is None:
        print("GATE FAIL: could not parse format pass", file=sys.stderr)
        return 1
    if fmt_pct < args.min_pass_pct:
        print(f"GATE FAIL: format {fmt_pct:.1f}% < {args.min_pass_pct}%", file=sys.stderr)
        return 2

    judge_frag = ""
    if args.with_judge:
        judge_pct = _parse_pct(proc.stdout, "judge pass:")
        if judge_pct is None:
            print("GATE FAIL: could not parse judge pass", file=sys.stderr)
            return 1
        if judge_pct < args.judge_min_pass_pct:
            print(
                f"GATE FAIL: judge {judge_pct:.1f}% < {args.judge_min_pass_pct}%",
                file=sys.stderr,
            )
            return 3
        judge_frag = f", judge {judge_pct:.1f}%"

    ts_frag = ""
    if args.with_task_success:
        passed, ts_pct, report = run_task_success_gate(args.task_success_min_pct)
        print(report)
        if not passed:
            print(
                f"GATE FAIL: task-success {ts_pct:.1f}% < {args.task_success_min_pct}%",
                file=sys.stderr,
            )
            return 4
        ts_frag = f", task-success {ts_pct:.1f}%"

    print(f"GATE OK (format {fmt_pct:.1f}%{judge_frag}{ts_frag})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
