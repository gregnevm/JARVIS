#!/usr/bin/env python3
"""Correctness gate (C.4): format eval + optional min score before LoRA promote.

  python training/eval/gate.py --holdout data/twin/export/sharegpt_holdout.jsonl
  python training/eval/gate.py --holdout ... --min-pass-pct 95
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--holdout", type=Path, required=True)
    ap.add_argument("--min-pass-pct", type=float, default=100.0)
    args = ap.parse_args()
    if not args.holdout.is_file():
        print(f"missing: {args.holdout}", file=sys.stderr)
        return 1
    script = Path(__file__).resolve().parent / "run_eval.py"
    proc = subprocess.run(
        [sys.executable, str(script), "--dataset", str(args.holdout)],
        capture_output=True,
        text=True,
    )
    print(proc.stdout, end="")
    if proc.stderr:
        print(proc.stderr, file=sys.stderr, end="")
    if proc.returncode != 0:
        print("GATE FAIL: format eval", file=sys.stderr)
        return proc.returncode
    # Parse "format pass: X/Y (Z%)"
    pct = 0.0
    for line in proc.stdout.splitlines():
        if "format pass:" in line and "(" in line:
            frag = line.split("(")[-1].replace("%)", "").strip()
            try:
                pct = float(frag)
            except ValueError:
                pass
    if pct < args.min_pass_pct:
        print(f"GATE FAIL: {pct:.1f}% < {args.min_pass_pct}%", file=sys.stderr)
        return 2
    print(f"GATE OK ({pct:.1f}%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
