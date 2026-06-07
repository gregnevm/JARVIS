#!/usr/bin/env python3
"""Запуск Cursor local agent на Windows-хості (Computer Use / host-agent CLI).

  pip install cursor-sdk
  set CURSOR_API_KEY=cursor_...
  python scripts/cursor_run_task.py --task "Fix login bug" --cwd O:\\JARVIS
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", required=True)
    ap.add_argument("--cwd", required=True)
    ap.add_argument("--model", default=os.environ.get("CURSOR_MODEL", "composer-2.5"))
    ap.add_argument("--api-key", default="")
    ap.add_argument("--api-key-env", default="CURSOR_API_KEY")
    args = ap.parse_args()

    task = args.task.strip()
    cwd = Path(args.cwd).resolve()
    if not cwd.is_dir():
        print(json.dumps({"ok": False, "error": f"cwd not found: {cwd}"}))
        return 1

    api_key = (args.api_key or os.environ.get(args.api_key_env, "")).strip()
    if not api_key:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": f"{args.api_key_env} not set — get key from Cursor Dashboard → API Keys",
                }
            )
        )
        return 2

    try:
        from cursor_sdk import Agent, AgentOptions, LocalAgentOptions
    except ImportError:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "cursor-sdk not installed — run: pip install cursor-sdk",
                }
            )
        )
        return 3

    try:
        result = Agent.prompt(
            task,
            AgentOptions(
                api_key=api_key,
                model=args.model,
                local=LocalAgentOptions(cwd=str(cwd)),
            ),
        )
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": str(exc)[:500]}))
        return 4

    out = {
        "ok": str(getattr(result, "status", "")).lower() != "error",
        "status": getattr(result, "status", None),
        "result": (getattr(result, "result", None) or "")[:8000],
    }
    print(json.dumps(out, ensure_ascii=False))
    return 0 if out["ok"] else 5


if __name__ == "__main__":
    raise SystemExit(main())
