#!/usr/bin/env python3
"""Мінімальний eval harness (Фаза 3 C.3): format-check + optional Ollama judge.

Usage:
  python training/eval/run_eval.py --dataset data/eval/holdout.jsonl
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def format_check(row: dict) -> tuple[bool, str]:
    conv = row.get("conversations") or row.get("messages")
    if not conv or not isinstance(conv, list):
        return False, "missing conversations/messages"
    roles = {m.get("role") for m in conv if isinstance(m, dict)}
    if not roles & {"user", "human"}:
        return False, "no user turn"
    if not roles & {"assistant", "gpt"}:
        return False, "no assistant turn"
    return True, "ok"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", type=Path, required=True)
    args = ap.parse_args()
    if not args.dataset.is_file():
        print(f"not found: {args.dataset}", file=sys.stderr)
        return 1
    rows = load_jsonl(args.dataset)
    ok = 0
    for i, row in enumerate(rows):
        passed, msg = format_check(row)
        if passed:
            ok += 1
        else:
            print(f"FAIL row {i}: {msg}")
    pct = (ok / len(rows) * 100) if rows else 0
    print(f"format pass: {ok}/{len(rows)} ({pct:.1f}%)")
    return 0 if ok == len(rows) else 2


if __name__ == "__main__":
    raise SystemExit(main())
