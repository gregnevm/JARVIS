#!/usr/bin/env python3
"""Kaizen passport_store — file-backend (the offline default; zero services needed).

Implements the `passport_store` port (engine/ports.md) without any network/DB, so the loop
works standalone. Each iteration passport is one JSON file under
``<artifact_dir>/passports/NNNN-<kind>.json`` (human-inspectable, index-ordered). Read = recency;
search = AND-of-tags + recency (the rag-backend upgrade adds cosine semantic retrieval on top).

Pure stdlib. The L2 contract: the next iteration reads recent/relevant passports first so it does
not re-derive repo state or repeat done work.

Usage:
    python passport_store.py write  <dir> <kind> <summary> [tag ...]
    python passport_store.py recent <dir> [top_k=5]
    python passport_store.py search <dir> <top_k> <tag> [tag ...]
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class Passport:
    i: int
    kind: str
    summary: str
    tags: list[str] = field(default_factory=list)
    ref: str = ""
    ts: str = ""

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _tag_match(passport_tags: list[str], query: str) -> bool:
    """Exact tag, or namespace prefix when the query ends with ':' (e.g. 'pillar:')."""
    if query.endswith(":"):
        return any(t.startswith(query) for t in passport_tags)
    return query in passport_tags


class FilePassportStore:
    """File-backend passport store. ``ref`` is any handle (commit SHA, run id, path)."""

    def __init__(self, artifact_dir: str) -> None:
        self.dir = os.path.join(artifact_dir, "passports")
        os.makedirs(self.dir, exist_ok=True)

    def _files(self) -> list[str]:
        return sorted(f for f in os.listdir(self.dir) if f.endswith(".json"))

    def _next_index(self) -> int:
        files = self._files()
        return (int(files[-1].split("-", 1)[0]) + 1) if files else 0

    def write(self, kind: str, summary: str, tags: list[str] | None = None, ref: str = "") -> Passport:
        idx = self._next_index()
        p = Passport(i=idx, kind=kind, summary=summary, tags=list(tags or []), ref=ref, ts=_now_iso())
        safe_kind = "".join(c if c.isalnum() or c in "-_" else "_" for c in kind)[:24]
        path = os.path.join(self.dir, f"{idx:04d}-{safe_kind}.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(p.to_json(), fh, ensure_ascii=False, indent=2)
        return p

    def _load_all(self) -> list[Passport]:
        out: list[Passport] = []
        for fname in self._files():
            with open(os.path.join(self.dir, fname), "r", encoding="utf-8") as fh:
                d = json.load(fh)
            out.append(Passport(**d))
        return out

    def recent(self, top_k: int = 5) -> list[Passport]:
        return self._load_all()[-top_k:][::-1]

    def search(self, tags: list[str], top_k: int = 5) -> list[Passport]:
        """AND-of-tags filter, recency order (file-backend; no embeddings)."""
        hits = [p for p in self._load_all() if all(_tag_match(p.tags, q) for q in tags)]
        return hits[-top_k:][::-1]


def _selfcheck() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        store = FilePassportStore(d)
        store.write("write", "added blast-radius guard", ["routine:kaizen", "iter:1", "pillar:B", "status:done"], ref="abc123")
        store.write("ci", "all six services green", ["routine:kaizen", "iter:1", "status:done"], ref="def456")
        store.write("write", "reverted ast refactor", ["routine:kaizen", "iter:2", "status:reverted"])
        assert len(store.recent(10)) == 3
        assert store.recent(1)[0].kind == "write" and store.recent(1)[0].i == 2
        done = store.search(["status:done"])
        assert len(done) == 2, done
        b = store.search(["pillar:", "status:done"])
        assert len(b) == 1 and b[0].ref == "abc123", b
        # reopen keeps indices monotonic
        store2 = FilePassportStore(d)
        p = store2.write("loop", "iteration 2 complete", ["iter:2"])
        assert p.i == 3, p.i
        print("passport_store self-check ok:", store2.recent(1)[0].summary)


def main(argv: list[str]) -> int:
    if not argv:
        _selfcheck()
        return 0
    cmd, rest = argv[0], argv[1:]
    if cmd == "write":
        store = FilePassportStore(rest[0])
        p = store.write(rest[1], rest[2], rest[3:])
        print(json.dumps(p.to_json(), ensure_ascii=False))
    elif cmd == "recent":
        store = FilePassportStore(rest[0])
        k = int(rest[1]) if len(rest) > 1 else 5
        print(json.dumps([p.to_json() for p in store.recent(k)], ensure_ascii=False, indent=2))
    elif cmd == "search":
        store = FilePassportStore(rest[0])
        print(json.dumps([p.to_json() for p in store.search(rest[2:], int(rest[1]))], ensure_ascii=False, indent=2))
    else:
        print(f"unknown command: {cmd}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
