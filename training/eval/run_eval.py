#!/usr/bin/env python3
"""Мінімальний eval harness (Фаза 3 C.3): format-check + optional Ollama judge.

Usage:
  python training/eval/run_eval.py --dataset data/eval/holdout.jsonl
  python training/eval/run_eval.py --dataset data/twin/export/sharegpt_holdout.jsonl --judge --ollama-url http://127.0.0.1:11434 --judge-model qwen2.5:7b
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
from pathlib import Path

_EVAL_DIR = Path(__file__).resolve().parent
if str(_EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(_EVAL_DIR))

from judge import judge_row


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
    roles = {str(m.get("role") or m.get("from") or "").lower() for m in conv if isinstance(m, dict)}
    if not roles & {"user", "human", "from"}:
        return False, "no user turn"
    if not roles & {"assistant", "gpt", "bot"}:
        return False, "no assistant turn"
    return True, "ok"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", type=Path, required=True)
    ap.add_argument("--judge", action="store_true", help="Run LLM-as-judge on assistant turns")
    ap.add_argument("--judge-model", default=os.environ.get("OLLAMA_MODEL_CHAT", "qwen2.5:7b"))
    ap.add_argument("--ollama-url", default=os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434"))
    ap.add_argument("--judge-sample", type=int, default=0, help="Judge random N rows (0 = all)")
    ap.add_argument("--seed", type=int, default=42)
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
    if pct < 100:
        return 2

    if not args.judge:
        return 0

    indices = list(range(len(rows)))
    if args.judge_sample and args.judge_sample < len(indices):
        rng = random.Random(args.seed)
        indices = sorted(rng.sample(indices, args.judge_sample))

    j_ok = 0
    for i in indices:
        passed, msg = judge_row(
            rows[i],
            ollama_url=args.ollama_url,
            model=args.judge_model,
        )
        if passed:
            j_ok += 1
        else:
            print(f"JUDGE FAIL row {i}: {msg}")
    j_pct = (j_ok / len(indices) * 100) if indices else 0
    print(f"judge pass: {j_ok}/{len(indices)} ({j_pct:.1f}%)")
    return 0 if j_ok == len(indices) else 3


if __name__ == "__main__":
    raise SystemExit(main())
