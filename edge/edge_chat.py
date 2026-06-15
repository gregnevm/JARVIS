"""Мінімальний офлайн-чат через KoboldAdapter + Edge RAG."""
from __future__ import annotations

import sys
from pathlib import Path

import httpx


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _ensure_paths() -> Path:
    root = _repo_root()
    edge = root / "edge"
    for p in (str(root), str(edge)):
        if p not in sys.path:
            sys.path.insert(0, p)
    return edge


def load_system_prompt(edge_root: Path) -> str:
    for name in ("personas/active_system.txt", "personas/jarvis_system.txt"):
        p = edge_root / name
        if p.is_file():
            return p.read_text(encoding="utf-8").strip()
    return "Ти JARVIS — лаконічний україномовний помічник."


def build_prompt(system: str, rag_hits: list[dict], user: str) -> str:
    parts = [f"SYSTEM: {system}"]
    if rag_hits:
        ctx = "\n".join(f"- {h['content'][:500]}" for h in rag_hits[:3])
        parts.append(f"CONTEXT:\n{ctx}")
    parts.append(f"USER: {user}")
    parts.append("ASSISTANT:")
    return "\n\n".join(parts)


def main() -> int:
    import argparse

    from jarvis_core.llm.adapters import KoboldAdapter

    from rag import EdgeRAG

    p = argparse.ArgumentParser(description="JARVIS Edge chat (KoboldCPP)")
    p.add_argument("--kobold", default="http://127.0.0.1:5001")
    p.add_argument("--rag-db", default="data/rag.db")
    p.add_argument("--once", default="", help="single prompt, no REPL")
    args = p.parse_args()

    edge_root = _ensure_paths()
    rag = EdgeRAG(edge_root / args.rag_db)
    system = load_system_prompt(edge_root)
    llm = KoboldAdapter(args.kobold, client=httpx.Client(timeout=180.0))

    def ask(user: str) -> str:
        hits = rag.search(user, top_k=3)
        prompt = build_prompt(system, hits, user)
        return llm.generate(prompt, max_tokens=512).strip()

    try:
        if args.once:
            print(ask(args.once))
            return 0
        print("Edge chat (empty line to quit). Kobold:", args.kobold)
        while True:
            try:
                user = input("> ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if not user:
                break
            print(ask(user))
        return 0
    finally:
        rag.close()


if __name__ == "__main__":
    raise SystemExit(main())
