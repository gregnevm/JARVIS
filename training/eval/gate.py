#!/usr/bin/env python3
"""Correctness gate (C.4): format eval + optional LLM-as-judge before LoRA promote.

  python training/eval/gate.py --holdout data/twin/export/sharegpt_holdout.jsonl
  python training/eval/gate.py --holdout ... --min-pass-pct 95
  python training/eval/gate.py --holdout ... --with-judge --judge-min-pass-pct 90
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def _parse_pct(stdout: str, label: str) -> float | None:
    for line in stdout.splitlines():
        if label in line and "(" in line:
            frag = line.split("(")[-1].replace("%)", "").strip()
            try:
                return float(frag)
            except ValueError:
                continue
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--holdout", type=Path, required=True)
    ap.add_argument("--min-pass-pct", type=float, default=100.0)
    ap.add_argument("--with-judge", action="store_true")
    ap.add_argument("--judge-min-pass-pct", type=float, default=90.0)
    ap.add_argument("--judge-model", default="")
    ap.add_argument("--ollama-url", default="")
    ap.add_argument("--judge-sample", type=int, default=0)
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
        print(f"GATE OK (format {fmt_pct:.1f}%, judge {judge_pct:.1f}%)")
        return 0

    print(f"GATE OK ({fmt_pct:.1f}%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
