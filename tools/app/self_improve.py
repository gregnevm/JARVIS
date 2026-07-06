"""Phase 7.2 — Self-improving loop: judge → human gate → curated dataset."""
from __future__ import annotations

import hashlib
import json
import logging
import re
import time
import uuid
from pathlib import Path
from typing import Any

import httpx

from .config import settings
from .dataset_export import _row_ok, iter_session_files, to_sharegpt
from .train_scheduler import mark_exported

logger = logging.getLogger("jarvis.tools.self_improve")

_JUDGE_PROMPT = """You are an evaluation judge for a personal AI assistant training dataset.
Decide if the assistant reply is on-topic, helpful, and reasonable for the user message.
Reply with exactly one line starting with PASS or FAIL, optionally followed by ": reason".

User:
{user}

Assistant:
{assistant}
"""


def _improve_dir() -> Path:
    p = Path(settings.data_dir) / "twin" / "improve"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _state_path() -> Path:
    return _improve_dir() / "state.json"


def _pending_path() -> Path:
    return _improve_dir() / "pending.jsonl"


def _approved_path() -> Path:
    return _improve_dir() / "approved.jsonl"


def _rejected_path() -> Path:
    return _improve_dir() / "rejected.jsonl"


def load_state() -> dict[str, Any]:
    p = _state_path()
    if not p.is_file():
        return {"processed": [], "last_scan_ts": 0}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"processed": [], "last_scan_ts": 0}
    except (OSError, json.JSONDecodeError):
        return {"processed": [], "last_scan_ts": 0}


def save_state(state: dict[str, Any]) -> None:
    _state_path().write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def turn_fingerprint(row: dict[str, Any]) -> str:
    raw = f"{row.get('ts')}:{row.get('user_id')}:{row.get('user', '')[:80]}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


_NEG_PASS_RE = re.compile(r"(?:\bNOT|\bNO|\bCANNOT|N'?T)\s+PASS\b")


def _parse_verdict(text: str) -> tuple[bool, str]:
    # A whitespace-only reply is truthy, so `"   ".splitlines()` is [] — guarding on the
    # STRIPPED value (not the raw `text`) avoids an IndexError that would abort scan_sessions.
    stripped = (text or "").strip()
    line = stripped.splitlines()[0] if stripped else ""
    upper = line.upper()
    if upper.startswith("PASS"):
        return True, line[4:].lstrip(": ").strip() or "pass"
    if upper.startswith("FAIL"):
        return False, line[4:].lstrip(": ").strip() or "fail"
    # Substring fallback for prose. Fail-closed for a quality gate: check FAIL first, and
    # approve only on a standalone, non-negated PASS token — so a rejection that merely
    # mentions "PASS" ("does not PASS the bar") isn't misread as approval (same class as the
    # orchestrator critic's \bAPPROVED\b + NOT-guard).
    if re.search(r"\bFAIL\b", upper):
        return False, line
    if re.search(r"\bPASS\b", upper) and not _NEG_PASS_RE.search(upper):
        return True, line
    return False, f"unparseable: {line[:120]}"


async def judge_turn(user: str, assistant: str) -> tuple[bool, str]:
    model = (settings.self_improve_judge_model or settings.ollama_model_chat).strip()
    host = settings.ollama_host.rstrip("/")
    prompt = _JUDGE_PROMPT.format(user=user.strip(), assistant=assistant.strip())
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {"temperature": 0.0, "num_predict": 64},
    }
    try:
        async with httpx.AsyncClient(timeout=settings.ollama_timeout) as cli:
            resp = await cli.post(f"{host}/api/chat", json=payload)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as exc:
        return False, f"ollama error: {exc}"
    msg = data.get("message")
    content = str(msg.get("content", "")) if isinstance(msg, dict) else ""
    return _parse_verdict(content)


def _append_jsonl(path: Path, rec: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    out: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            out.append(row)
    return out


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


async def scan_sessions(
    *,
    user_id: int | None = None,
    limit: int = 50,
    with_judge: bool = True,
) -> dict[str, Any]:
    """Сканує нові session turns → judge → pending queue (human gate)."""
    if not settings.self_improve_enabled:
        return {"enabled": False, "scanned": 0}

    state = load_state()
    processed = set(state.get("processed") or [])
    scanned = 0
    queued = 0
    rejected = 0
    errors = 0

    for path in iter_session_files(user_id):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            if scanned >= limit > 0:
                break
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(row, dict) or not _row_ok(row, min_assist=20):
                continue
            fp = turn_fingerprint(row)
            if fp in processed:
                continue
            scanned += 1
            processed.add(fp)

            if with_judge:
                ok, reason = await judge_turn(str(row.get("user", "")), str(row.get("assistant", "")))
            else:
                ok, reason = True, "judge skipped"

            if ok:
                item = {
                    "id": uuid.uuid4().hex[:12],
                    "fingerprint": fp,
                    "status": "pending",
                    "judge_pass": True,
                    "judge_reason": reason[:500],
                    "ts": row.get("ts"),
                    "user_id": row.get("user_id"),
                    "mode": row.get("mode"),
                    "user": row.get("user"),
                    "assistant": row.get("assistant"),
                    "created_at": int(time.time()),
                }
                _append_jsonl(_pending_path(), item)
                queued += 1
            else:
                _append_jsonl(
                    _rejected_path(),
                    {"fingerprint": fp, "reason": reason, "ts": row.get("ts"), "user_id": row.get("user_id")},
                )
                rejected += 1

    state["processed"] = sorted(processed)[-50000:]
    state["last_scan_ts"] = int(time.time())
    save_state(state)

    from .train_scheduler import retrain_status

    sched = retrain_status(user_id)
    return {
        "enabled": True,
        "scanned": scanned,
        "queued": queued,
        "rejected": rejected,
        "errors": errors,
        "pending_total": len(list_pending()),
        "retrain": sched,
    }


def list_pending(*, status: str = "pending", limit: int = 100) -> list[dict[str, Any]]:
    rows = _read_jsonl(_pending_path())
    if status:
        rows = [r for r in rows if str(r.get("status", "pending")) == status]
    rows.sort(key=lambda r: int(r.get("created_at") or 0), reverse=True)
    return rows[: max(1, limit)]


def review_items(item_ids: list[str], action: str, *, reviewer: str = "") -> dict[str, Any]:
    """approve | reject — human gate."""
    action = (action or "").strip().lower()
    if action not in ("approve", "reject"):
        raise ValueError("action must be approve or reject")
    want = set(item_ids)
    pending = _read_jsonl(_pending_path())
    kept: list[dict[str, Any]] = []
    approved_n = 0
    rejected_n = 0
    now = int(time.time())

    for row in pending:
        iid = str(row.get("id") or "")
        if iid not in want:
            kept.append(row)
            continue
        if action == "approve":
            row["status"] = "approved"
            row["reviewed_at"] = now
            row["reviewer"] = reviewer[:80]
            _append_jsonl(_approved_path(), row)
            approved_n += 1
        else:
            row["status"] = "rejected"
            row["reviewed_at"] = now
            row["reviewer"] = reviewer[:80]
            _append_jsonl(
                _rejected_path(),
                {
                    "id": iid,
                    "fingerprint": row.get("fingerprint"),
                    "reason": "human_reject",
                    "reviewer": reviewer,
                },
            )
            rejected_n += 1

    _write_jsonl(_pending_path(), kept)
    return {
        "action": action,
        "approved": approved_n,
        "rejected": rejected_n,
        "pending_remaining": len(kept),
    }


def export_approved_to_sharegpt(
    dest: Path | None = None,
    *,
    user_id: int | None = None,
) -> dict[str, Any]:
    """Merge approved human-gate rows у ShareGPT export."""
    approved = _read_jsonl(_approved_path())
    if user_id is not None:
        approved = [r for r in approved if int(r.get("user_id") or 0) == int(user_id)]
    rows = [
        {
            "user_id": r.get("user_id"),
            "mode": r.get("mode"),
            "ts": r.get("ts"),
            "user": r.get("user"),
            "assistant": r.get("assistant"),
        }
        for r in approved
    ]
    if not rows:
        return {"exported": 0, "note": "no approved rows"}

    out = dest or (Path(settings.data_dir) / "twin" / "export" / "sharegpt_improve.jsonl")
    out.parent.mkdir(parents=True, exist_ok=True)
    dataset = to_sharegpt(rows)
    with out.open("w", encoding="utf-8") as f:
        for rec in dataset:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    mark = mark_exported(user_id)
    return {"exported": len(dataset), "path": str(out), "retrain": mark}


def improve_status(user_id: int | None = None) -> dict[str, Any]:
    from .train_scheduler import retrain_status

    state = load_state()
    return {
        "enabled": settings.self_improve_enabled,
        "last_scan_ts": state.get("last_scan_ts", 0),
        "processed_count": len(state.get("processed") or []),
        "pending": len(list_pending()),
        "approved_total": len(_read_jsonl(_approved_path())),
        "rejected_total": len(_read_jsonl(_rejected_path())),
        "retrain": retrain_status(user_id),
    }
