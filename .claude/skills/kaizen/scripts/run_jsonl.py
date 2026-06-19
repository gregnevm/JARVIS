#!/usr/bin/env python3
"""Kaizen run-event sink — thin append-only JSONL writer + reader.

One file per run (``runs/<run_id>/run.jsonl``), NEVER a shared file (a shared
multi-run/multi-user file with no filter would be an IDOR surface if ever exposed).
Pure stdlib. Eco applied to the loop's own instrumentation:

  * in-memory line counter — no O(n) re-read of the file per append;
  * a mandatory redaction pass before every append (truncating is not scrubbing);
  * read-by-index / tail for replay & resume (the SSOT logger lacks this).

The generic engine owns this writer; a profile supplies the envelope fields
(actor, run_id, paths). No repo strings here.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Iterator

# keys whose values must never be persisted verbatim
_SECRET_KEY = re.compile(r"(token|secret|password|passwd|api[_-]?key|authorization|cookie|bearer)", re.I)
# long secret-shaped values (hex/base64-ish) embedded in strings
_SECRET_VAL = re.compile(r"\b(sk-[A-Za-z0-9_-]{12,}|[A-Fa-f0-9]{32,}|[A-Za-z0-9+/]{40,}={0,2})\b")
_MAX_STR = 2000


def _redact(obj: Any) -> Any:
    """Recursively scrub secret-shaped keys/values. Conservative: redact on doubt."""
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for k, v in obj.items():
            if isinstance(k, str) and _SECRET_KEY.search(k):
                out[k] = "***redacted***"
            else:
                out[k] = _redact(v)
        return out
    if isinstance(obj, list):
        return [_redact(v) for v in obj]
    if isinstance(obj, str):
        s = _SECRET_VAL.sub("***redacted***", obj)
        return s if len(s) <= _MAX_STR else s[:_MAX_STR] + "…"
    return obj


class RunLog:
    """Append-only JSONL sink for one run. Cheap counter, redacted writes."""

    def __init__(self, run_dir: str, run_id: str) -> None:
        self.run_id = run_id
        self.path = os.path.join(run_dir, "run.jsonl")
        os.makedirs(run_dir, exist_ok=True)
        # initialise the in-memory counter once (the only O(n) read, at open)
        self._count = 0
        if os.path.exists(self.path):
            with open(self.path, "r", encoding="utf-8") as fh:
                self._count = sum(1 for _ in fh)

    @property
    def count(self) -> int:
        return self._count

    def append(self, phase: str, **fields: Any) -> int:
        """Append one redacted event; returns its 0-based index. O(1) amortised."""
        event = _redact({"i": self._count, "run_id": self.run_id, "phase": phase, **fields})
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False) + "\n")
        idx = self._count
        self._count += 1
        return idx

    def read_all(self) -> list[dict[str, Any]]:
        if not os.path.exists(self.path):
            return []
        with open(self.path, "r", encoding="utf-8") as fh:
            return [json.loads(line) for line in fh if line.strip()]

    def tail(self, n: int = 20, phase: str | None = None) -> list[dict[str, Any]]:
        """Last n events (optionally filtered by phase) via reverse scan."""
        rows = self.read_all()
        if phase is not None:
            rows = [r for r in rows if r.get("phase") == phase]
        return rows[-n:]

    def replay(self) -> Iterator[dict[str, Any]]:
        yield from self.read_all()


if __name__ == "__main__":  # tiny self-check
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        log = RunLog(d, "selfcheck-1")
        log.append("write", task="demo", api_key="sk-shouldNeverPersist1234567890")
        log.append("ci", status="green")
        rows = log.read_all()
        assert log.count == 2, log.count
        assert rows[0]["api_key"] == "***redacted***", rows[0]
        assert rows[1]["phase"] == "ci"
        # reopen keeps the counter correct (no O(n) per append, but correct on resume)
        log2 = RunLog(d, "selfcheck-1")
        assert log2.count == 2, log2.count
        print("run_jsonl self-check ok:", rows[0])
