"""Edge RAG + mode_detect."""
from __future__ import annotations

import sys
from pathlib import Path

EDGE = Path(__file__).resolve().parents[1]
if str(EDGE) not in sys.path:
    sys.path.insert(0, str(EDGE))

from rag import EdgeRAG, cosine, keyword_score  # noqa: E402


def test_keyword_search(tmp_path: Path):
    db = tmp_path / "rag.db"
    rag = EdgeRAG(db)
    rag.store("JARVIS PortableAI на USB флешці")
    rag.store("Something else entirely")
    hits = rag.search("USB JARVIS", top_k=2)
    assert hits
    assert "USB" in hits[0]["content"]
    rag.close()


def test_cosine_identical():
    v = [1.0, 0.0, 0.0]
    assert cosine(v, v) == 1.0


def test_keyword_score_partial():
    assert keyword_score("jarvis usb", "JARVIS on USB stick") > 0.5


def test_mode_offline_when_unreachable():
    from mode_detect import detect_mode

    assert detect_mode("http://127.0.0.1:1", timeout=0.2) == "OFFLINE"
