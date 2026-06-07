"""Edge RAG — SQLite + cosine search (без pgvector, офлайн)."""
from __future__ import annotations

import json
import math
import re
import sqlite3
import struct
from pathlib import Path
from typing import Any, Callable


def _pack_vec(vec: list[float]) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


def _unpack_vec(blob: bytes) -> list[float]:
    n = len(blob) // 4
    return list(struct.unpack(f"{n}f", blob))


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def keyword_score(query: str, content: str) -> float:
    q = {w for w in re.findall(r"\w+", query.lower()) if len(w) > 2}
    if not q:
        return 0.0
    text = content.lower()
    hits = sum(1 for w in q if w in text)
    return hits / len(q)


class EdgeRAG:
    """Локальна база знань на USB. Embeddings опційні (LAN → Twin /embed)."""

    _SCHEMA = """
    CREATE TABLE IF NOT EXISTS chunks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        content TEXT NOT NULL,
        embedding BLOB,
        meta_json TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    );
    CREATE INDEX IF NOT EXISTS idx_chunks_created ON chunks(created_at);
    """

    def __init__(
        self,
        db_path: str | Path,
        embed_fn: Callable[[str], list[float] | None] | None = None,
    ) -> None:
        self._path = Path(db_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._embed_fn = embed_fn
        self._conn = sqlite3.connect(str(self._path))
        self._conn.executescript(self._SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def store(self, content: str, meta: dict[str, Any] | None = None) -> int:
        text = content.strip()
        if not text:
            raise ValueError("empty content")
        emb: list[float] | None = None
        if self._embed_fn:
            emb = self._embed_fn(text)
        blob = _pack_vec(emb) if emb else None
        cur = self._conn.execute(
            "INSERT INTO chunks (content, embedding, meta_json) VALUES (?, ?, ?)",
            (text, blob, json.dumps(meta or {}, ensure_ascii=False)),
        )
        self._conn.commit()
        return int(cur.lastrowid or 0)

    def search(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT id, content, embedding, meta_json FROM chunks ORDER BY id DESC LIMIT 5000"
        ).fetchall()
        q_emb = self._embed_fn(query) if self._embed_fn else None
        scored: list[tuple[float, int, str, dict[str, Any]]] = []
        for _id, content, blob, meta_json in rows:
            meta = json.loads(meta_json or "{}")
            if q_emb and blob:
                score = cosine(q_emb, _unpack_vec(blob))
            else:
                score = keyword_score(query, content)
            if score > 0:
                scored.append((score, int(_id), str(content), meta))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            {"id": i, "content": c, "score": round(s, 4), "meta": m}
            for s, i, c, m in scored[: max(1, top_k)]
        ]

    def count(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) FROM chunks").fetchone()
        return int(row[0]) if row else 0
