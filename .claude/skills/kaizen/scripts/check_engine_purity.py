#!/usr/bin/env python3
"""DR1 engine-purity gate — fail the build if the generic engine leaked a repo string.

The kaizen engine (``engine/**`` + ``SKILL.md``) must speak PORTS, never repo nouns, so the
same engine is portable to any product. This gate greps those files for repo-coupling
identifiers and exits non-zero on any hit (run it as a CI tripwire).

Usage:
    python check_engine_purity.py                     # default repo-coupling red flags
    python check_engine_purity.py jarvis memory:8100  # a profile's own identifiers

Exit 0 = pure; exit 1 = leak (prints file:line); exit 2 = engine dir missing.
"""
from __future__ import annotations

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE_ROOT = os.path.normpath(os.path.join(HERE, ".."))
SCAN = ["engine", "SKILL.md"]

# Default denylist: identifiers that almost always mean "this engine got coupled to one repo".
# A profile name (the abstract port `roadmap_source` is deliberately allowed) is NOT here —
# pass concrete profile identifiers as argv to also forbid those.
DEFAULT_DENY = [
    r"jarvis_core",
    r"memory:\d{2,5}",          # hardcoded service host:port
    r"AGENTS\.md",
    r"docs/[A-Za-z_]*ROADMAP",  # a concrete roadmap path (the port name is fine)
    r"pytest\s+\w+/tests",      # an inlined per-service test command
    r"\bOllama\b",
]


def _iter_files() -> list[str]:
    files: list[str] = []
    for entry in SCAN:
        path = os.path.join(ENGINE_ROOT, entry)
        if os.path.isfile(path):
            files.append(path)
        elif os.path.isdir(path):
            for root, _dirs, names in os.walk(path):
                files.extend(os.path.join(root, n) for n in names if n.endswith(".md"))
    return files


def main(argv: list[str] | None = None) -> int:
    extra = argv if argv is not None else sys.argv[1:]
    patterns = DEFAULT_DENY + [re.escape(a) for a in extra]
    regex = re.compile("|".join(f"({p})" for p in patterns), re.IGNORECASE)

    files = _iter_files()
    if not files:
        print(f"check_engine_purity: nothing to scan under {ENGINE_ROOT}", file=sys.stderr)
        return 2

    leaks: list[str] = []
    for fpath in files:
        with open(fpath, "r", encoding="utf-8") as fh:
            for n, line in enumerate(fh, 1):
                if regex.search(line):
                    rel = os.path.relpath(fpath, ENGINE_ROOT)
                    leaks.append(f"{rel}:{n}: {line.strip()[:100]}")

    if leaks:
        print("DR1 VIOLATION — engine leaked repo strings (engine must be profile-agnostic):")
        for leak in leaks:
            print("  " + leak)
        return 1
    print(f"DR1 ok — {len(files)} engine files pure (no repo coupling).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
