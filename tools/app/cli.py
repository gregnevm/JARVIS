"""jarvis code — локальний CLI проти tools-агента (CA-6.1/6.2).

Тонкий клієнт до tools REST (/agent, /agent/code/{plan,review,fix}). База —
``JARVIS_TOOLS_URL`` (default http://127.0.0.1:8001); auth — Bearer
``JARVIS_API_KEY`` (опційно, CA-6.2); user — ``JARVIS_USER_ID``.

Підкоманди:
  jarvis-code run   "<task>"                 → /agent (agent-режим)
  jarvis-code plan  "<task>"                 → /agent/code/plan (file-targeted)
  jarvis-code review --diff-file path.diff   → /agent/code/review
  jarvis-code fix   --exe pytest [-- args]   → /agent/code/fix (fix-orchestration)
  jarvis-code edit  --file f.py --instruction "…"  → /agent/code/edit (inline diff; IDE-міст)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

import httpx


def _base_url() -> str:
    return os.environ.get("JARVIS_TOOLS_URL", "http://127.0.0.1:8001").rstrip("/")


def _headers() -> dict[str, str]:
    key = os.environ.get("JARVIS_API_KEY", "").strip()
    return {"Authorization": f"Bearer {key}"} if key else {}


def _user_id() -> int:
    try:
        return int(os.environ.get("JARVIS_USER_ID", "0"))
    except ValueError:
        return 0


async def _post(path: str, payload: dict[str, Any], *, timeout: float = 180.0) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(f"{_base_url()}{path}", json=payload, headers=_headers())
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, dict) else {"result": data}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="jarvis-code", description="JARVIS coding agent CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="agent turn проти задачі")
    p_run.add_argument("task", nargs="+")

    p_plan = sub.add_parser("plan", help="code-plan із file-targets")
    p_plan.add_argument("task", nargs="+")

    p_review = sub.add_parser("review", help="self-review unified diff")
    p_review.add_argument("--diff-file", required=True)

    p_fix = sub.add_parser("fix", help="fix-orchestration: тест→правка→тест")
    p_fix.add_argument("--exe", required=True)
    p_fix.add_argument("--path", default="")
    p_fix.add_argument("--task", default="")
    p_fix.add_argument("--max-rounds", type=int, default=None)
    p_fix.add_argument(
        "--no-confirm",
        "--apply",
        dest="no_confirm",
        action="store_true",
        help="headless: застосовувати правки без інтерактивного confirm (за CODING_HEADLESS_APPLY)",
    )
    p_fix.add_argument(
        "--review",
        dest="review",
        action="store_true",
        help="self-review + авто-fix зауважень перед звітом (за CODING_REVIEW_AFTER_FIX)",
    )
    p_fix.add_argument("rest", nargs="*", help="аргументи раннера (після --)")

    p_edit = sub.add_parser("edit", help="запропонувати inline-diff для файлу (IDE-міст)")
    p_edit.add_argument("--file", required=True, help="шлях до файлу (вміст читається локально)")
    p_edit.add_argument("--instruction", required=True, help="що змінити")
    p_edit.add_argument(
        "--apply",
        dest="apply",
        action="store_true",
        help="записати запропонований вміст назад у файл (інакше — лише показати diff)",
    )
    return parser


async def dispatch(ns: argparse.Namespace) -> dict[str, Any]:
    uid = _user_id()
    if ns.cmd == "run":
        return await _post("/agent", {"user_id": uid, "text": " ".join(ns.task), "mode": "agent"})
    if ns.cmd == "plan":
        return await _post("/agent/code/plan", {"user_id": uid, "text": " ".join(ns.task)})
    if ns.cmd == "review":
        diff = Path(ns.diff_file).read_text(encoding="utf-8")
        return await _post("/agent/code/review", {"user_id": uid, "diff": diff})
    if ns.cmd == "fix":
        return await _post(
            "/agent/code/fix",
            {
                "user_id": uid,
                "exe": ns.exe,
                "args": list(ns.rest or []),
                "path": ns.path,
                "task": ns.task,
                "max_rounds": ns.max_rounds,
                "no_confirm": bool(getattr(ns, "no_confirm", False)),
                "review": bool(getattr(ns, "review", False)),
            },
        )
    if ns.cmd == "edit":
        src = Path(ns.file)
        content = src.read_text(encoding="utf-8") if src.exists() else ""
        data = await _post(
            "/agent/code/edit",
            {"user_id": uid, "path": ns.file, "instruction": ns.instruction, "content": content},
        )
        if getattr(ns, "apply", False) and data.get("changed"):
            src.write_text(str(data.get("proposed") or ""), encoding="utf-8")
            data["_applied"] = True
        return data
    raise SystemExit(2)


def format_result(cmd: str, data: dict[str, Any]) -> str:
    if cmd == "run":
        return str(data.get("text") or data)
    if cmd == "plan":
        steps = data.get("steps") or []
        lines = [f"План {data.get('id', '?')}: {data.get('summary', '')}"]
        for s in steps:
            if isinstance(s, dict):
                tag = s.get("file") or s.get("title") or ""
                lines.append(f"  • {tag}: {s.get('action') or s.get('detail') or ''}")
        return "\n".join(lines)
    if cmd == "review":
        out = [f"verdict: {data.get('verdict', '?')} — {data.get('summary', '')}"]
        for f in data.get("findings") or []:
            if isinstance(f, dict):
                out.append(f"  [{f.get('severity')}] {f.get('file')}:{f.get('line')} {f.get('comment')}")
        return "\n".join(out)
    if cmd == "fix":
        head = f"status: {data.get('status', '?')} (rounds={data.get('rounds', 0)})\n{data.get('report', '')}"
        rv = data.get("review")
        if isinstance(rv, dict) and rv.get("verdict") not in (None, "skip"):
            extra = f"\n— review: {rv.get('verdict')} — {rv.get('summary', '')}"
            if rv.get("fix_attempted"):
                extra += f" (авто-fix → tests {rv.get('tests_after_fix', '?')})"
            head += extra
        return head
    if cmd == "edit":
        if not data.get("changed"):
            return f"(без змін) {data.get('path', '')}"
        diff = str(data.get("diff") or "")
        tail = "\n— застосовано до файлу" if data.get("_applied") else "\n— diff не застосовано (--apply щоб записати)"
        return diff + tail
    return json.dumps(data, ensure_ascii=False)


def main(argv: list[str] | None = None) -> int:
    ns = build_parser().parse_args(argv)
    try:
        data = asyncio.run(dispatch(ns))
    except httpx.HTTPError as exc:
        print(f"jarvis-code: HTTP error: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"jarvis-code: {exc}", file=sys.stderr)
        return 1
    print(format_result(ns.cmd, data))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
