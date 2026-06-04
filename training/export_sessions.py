#!/usr/bin/env python3
"""CLI: експорт session JSONL → ShareGPT (з repo root або tools container).

  python training/export_sessions.py
  python training/export_sessions.py --user-id 123456789 --limit 500
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from app.config import settings  # noqa: E402
from app.dataset_export import session_stats, write_sharegpt_jsonl  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--user-id", type=int, default=None)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument(
        "--out",
        type=Path,
        default=None,
        help="output jsonl (default: data/twin/export/sharegpt.jsonl)",
    )
    args = ap.parse_args()
    dest = args.out or Path(settings.data_dir) / "twin" / "export" / "sharegpt.jsonl"
    stats = session_stats(args.user_id)
    print("stats:", stats)
    if stats["curated_turns"] == 0:
        print("no curated turns — chat with JARVIS first", file=sys.stderr)
        return 2
    info = write_sharegpt_jsonl(dest, user_id=args.user_id, limit=args.limit)
    print("export:", info)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
