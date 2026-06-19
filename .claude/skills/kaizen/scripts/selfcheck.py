#!/usr/bin/env python3
"""Kaizen toolkit self-check — run every script's self-test. One command verifies the engine.

Eco: pure, deterministic, no services, no LLM. Exit 0 = the whole offline toolkit works.
Run as a CI tripwire and after any toolkit edit.
"""
from __future__ import annotations

import subprocess
import sys
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = ["run_jsonl.py", "passport_store.py", "ledger.py", "sigdedup.py"]
PURITY = ["check_engine_purity.py", "jarvis"]


def _run(args: list[str]) -> bool:
    env = dict(os.environ, PYTHONUTF8="1")
    proc = subprocess.run([sys.executable, *args], cwd=HERE, capture_output=True, text=True, env=env)
    ok = proc.returncode == 0
    tail = (proc.stdout.strip().splitlines() or [""])[-1]
    print(f"  [{'ok ' if ok else 'FAIL'}] {args[0]:<22} {tail if ok else (proc.stderr.strip()[-200:])}")
    return ok


def main() -> int:
    print("kaizen toolkit self-check")
    results = [_run([os.path.join(HERE, s)]) for s in SCRIPTS]
    results.append(_run([os.path.join(HERE, PURITY[0]), PURITY[1]]))
    # render a sample digest end-to-end (renderer + a minimal summary the ledger could build)
    sample = os.path.join(HERE, "_sample_summary.json")
    import json
    with open(sample, "w", encoding="utf-8") as fh:
        json.dump({"run_id": "selfcheck", "day": 1, "iters": 1, "duration_min": 1, "ci": "green",
                   "kaizen_score": 50, "score_delta": 0, "score_history": [50],
                   "shipped": [{"title": "t", "before": "a", "after": "b"}],
                   "tests_delta": "+1", "tokens": {"total": 1000, "inner_local": 0, "outer_remote": 1000},
                   "meta_kr": {"felt": True}}, fh)
    results.append(_run([os.path.join(HERE, "render_digest.py"), sample, "--status"]))
    os.remove(sample)
    ok = all(results)
    print(("PASS — toolkit fully working" if ok else "FAIL — see above"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
