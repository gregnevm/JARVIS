"""Personal user notes (file-backed)."""
from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

from ..config import settings


def _notes_file(user_id: int) -> Path:
    d = Path(settings.data_dir) / "notes"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{int(user_id)}.jsonl"


def take_note(text: str, user_id: int) -> str:
    text = (text or "").strip()
    if not text:
        return "Порожня нотатка."
    try:
        rec = {"ts": int(time.time()), "text": text[:2000]}
        with _notes_file(user_id).open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError as exc:
        return f"Не вдалося зберегти нотатку: {exc}"
    return "Нотатку збережено ✅"


def recall_notes(user_id: int, limit: int = 10) -> str:
    limit = max(1, min(limit, 50))
    p = _notes_file(user_id)
    if not p.is_file():
        return "Нотаток поки немає."
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        return f"Не вдалося прочитати нотатки: {exc}"
    out: list[str] = []
    for ln in lines[-limit:]:
        try:
            rec = json.loads(ln)
        except json.JSONDecodeError:
            continue
        ts = datetime.fromtimestamp(int(rec.get("ts", 0))).strftime("%Y-%m-%d %H:%M")
        out.append(f"• [{ts}] {rec.get('text', '')}")
    return "\n".join(out) if out else "Нотаток поки немає."
