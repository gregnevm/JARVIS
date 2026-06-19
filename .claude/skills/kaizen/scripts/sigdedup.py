#!/usr/bin/env python3
"""Kaizen signature dedup — cross-iteration no-progress / anti-grakes detector (offline, pure).

The in-loop fix loop already stops when a failed-test set repeats *within* one fix attempt. This
adds the CROSS-iteration memory the engine asked for (engine/loop-contract.md): if iteration N's
failed-test set matches a set already seen in an EARLIER iteration, the loop is re-attempting a
known-failing path (a 'graben') and should stop or change approach instead of burning the window.

The signature mirrors the in-loop ``summary_signature`` concept (a stable hash of the sorted,
de-duplicated failing-test names) but is persisted per run. Pure stdlib.

Files: ``<artifact_dir>/signatures.json`` -> { "history": ["<sig>", ...] }
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from typing import Any

_TEST_RE = re.compile(r"([\w/]+\.py::[\w:\[\]\-.]+|[\w/]+\.py)")


def signature(failed_tests: list[str]) -> str:
    """16-char hex over the sorted-unique failing-test identifiers (deterministic, no I/O)."""
    norm = sorted({t.strip() for t in failed_tests if t.strip()})
    return hashlib.sha1("\n".join(norm).encode("utf-8")).hexdigest()[:16]


def signature_from_output(test_output: str) -> str:
    """Convenience: extract test ids from a rendered failure summary, then sign."""
    return signature(_TEST_RE.findall(test_output))


class SignatureHistory:
    def __init__(self, artifact_dir: str) -> None:
        self.path = os.path.join(artifact_dir, "signatures.json")
        os.makedirs(artifact_dir, exist_ok=True)

    def _load(self) -> list[str]:
        if not os.path.exists(self.path):
            return []
        with open(self.path, "r", encoding="utf-8") as fh:
            data: dict[str, Any] = json.load(fh)
        return list(data.get("history", []))

    def record(self, sig: str) -> bool:
        """Append a signature. Returns True if it REPEATS an earlier iteration (a graben)."""
        hist = self._load()
        repeat = sig in hist
        hist.append(sig)
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump({"history": hist}, fh, ensure_ascii=False, indent=2)
        return repeat

    def is_repeat(self, sig: str) -> bool:
        return sig in self._load()


def _selfcheck() -> None:
    import tempfile

    a = signature(["tools/tests/test_x.py::test_a", "tools/tests/test_x.py::test_b"])
    b = signature(["tools/tests/test_x.py::test_b", "tools/tests/test_x.py::test_a"])  # order-independent
    assert a == b, (a, b)
    assert len(a) == 16 and a != signature(["other.py::t"])
    sig_out = signature_from_output("FAILED memory/tests/test_db.py::test_search - AssertionError")
    assert sig_out == signature(["memory/tests/test_db.py::test_search"]), sig_out
    with tempfile.TemporaryDirectory() as d:
        h = SignatureHistory(d)
        assert h.record(a) is False          # iter 1 — new
        assert h.record(signature(["z.py"])) is False  # iter 2 — different failure
        assert h.record(a) is True           # iter 3 re-fails what iter 1 already failed -> graben
        h2 = SignatureHistory(d)             # persists across reopen
        assert h2.is_repeat(a) is True
    print("sigdedup self-check ok: sig=", a)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "sign":
        print(signature_from_output(sys.stdin.read()))
    else:
        _selfcheck()
