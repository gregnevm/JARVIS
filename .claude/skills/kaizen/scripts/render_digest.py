#!/usr/bin/env python3
"""Kaizen daily-digest renderer — deterministic, pure, zero LLM tokens on layout.

Reads a run ``summary.json`` (schema: references/digest-format.md) and emits the
markdown digest, a one-line status line, and an ASCII 7-day sparkline. No network,
no model calls, reproducible: same JSON in -> same digest out (eco: form is free).

Profile-agnostic — depends only on the stable summary schema, never on loop internals
or any repo string.

Usage:
    python render_digest.py summary.json            # markdown digest (default)
    python render_digest.py summary.json --status   # one status line
    python render_digest.py summary.json --json      # validated/normalized summary
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any

_BARS = "▁▂▃▄▅▆▇█"
_CI_GLYPH = {"green": "●", "red": "●", "mixed": "◐"}


def sparkline(values: list[float]) -> str:
    """Map a series to ▁..█ by min-max. Empty/flat series degrade gracefully."""
    nums = [float(v) for v in values if isinstance(v, (int, float))]
    if not nums:
        return ""
    lo, hi = min(nums), max(nums)
    if hi == lo:
        return _BARS[len(_BARS) // 2] * len(nums)
    span = hi - lo
    return "".join(_BARS[min(len(_BARS) - 1, int((n - lo) / span * (len(_BARS) - 1)))] for n in nums)


def _signed(n: Any) -> str:
    try:
        v = int(n)
    except (TypeError, ValueError):
        return str(n)
    return f"+{v}" if v > 0 else str(v)


def status_line(s: dict[str, Any]) -> str:
    """Channel-agnostic one-liner: who > day > progress > task+phase > CI > budget > window."""
    tok = s.get("tokens", {}) or {}
    total_k = round((tok.get("total", 0) or 0) / 1000)
    ci = s.get("ci", "green")
    cur = s.get("current") or {}
    progress = cur.get("progress") or f"{s.get('iters', '?')} iters"
    task = cur.get("task", "")
    phase = cur.get("phase", "")
    task_phase = " ".join(x for x in (task, phase) if x) or "done"
    window = cur.get("window", "")
    parts = [
        "kaizen",
        f"day{s.get('day', '?')}",
        progress,
        task_phase,
        f"{_CI_GLYPH.get(ci, '●')} {ci}",
        f"{total_k}k tok",
    ]
    if window:
        parts.append(window)
    return " > ".join(parts)


def _metric_cards(s: dict[str, Any]) -> str:
    tok = s.get("tokens", {}) or {}
    split = ""
    if tok.get("inner_local") is not None and tok.get("outer_remote") is not None:
        split = f" (local {round(tok['inner_local']/1000)}k / remote {round(tok['outer_remote']/1000)}k)"
    dpct = tok.get("delta_pct")
    tok_line = f"{round((tok.get('total', 0) or 0)/1000)}k"
    if dpct is not None:
        tok_line += f" ({_signed(dpct)}%)"
    tok_line += split
    return (
        f"| kaizen-score | shipped | tests | tokens |\n"
        f"|---|---|---|---|\n"
        f"| **{s.get('kaizen_score', '?')}** ({_signed(s.get('score_delta', 0))}) "
        f"| {len(s.get('shipped', []))} | {s.get('tests_delta', '0')} | {tok_line} |"
    )


def _dots(s: dict[str, Any]) -> str:
    mk = s.get("meta_kr", {}) or {}
    felt = "🟢" if mk.get("felt") else "🟡"
    rev = "⚪" if s.get("reverted") else ""
    return f"{felt}{rev}".strip()


def render_markdown(s: dict[str, Any]) -> str:
    lines: list[str] = []
    # BLOCK 0 — meta-OKR strip
    lines.append("> Objective: ship a felt improvement daily · KR: kaizen-score trend up over 7d\n")
    # BLOCK 1 — header
    ci = s.get("ci", "green")
    lines.append(
        f"### kaizen · day {s.get('day','?')} · {s.get('run_id','?')} · "
        f"{s.get('iters','?')} iters · {s.get('duration_min','?')}m · [{_CI_GLYPH.get(ci,'●')} {ci}]\n"
    )
    # BLOCK 2 — metric cards
    lines.append(_metric_cards(s) + "\n")
    # BLOCK 3 — sparkline + dots
    spark = sparkline(s.get("score_history", []))
    if spark:
        lines.append(f"7-day score: `{spark}`  {_dots(s)}\n")
    # BLOCK 4 — what changed (mandatory before->after)
    shipped = s.get("shipped", []) or []
    if shipped:
        lines.append("**What changed today**")
        for it in shipped:
            before, after = it.get("before"), it.get("after")
            # telemetry-born task (SY-1): cite the friction passport that spawned it
            friction = f" · from telemetry: `{it['friction_ref']}`" if it.get("friction_ref") else ""
            if before and after:
                lines.append(
                    f"- {it.get('title','(item)')} — _before:_ {before} → _after:_ {after}{friction}"
                )
            else:
                # no measured before/after -> muted, drives the yellow meta-KR dot
                lines.append(f"- _{it.get('title','(item)')} (no measured before/after)_{friction}")
        lines.append("")
    # BLOCK 5 — risk / reverted + actions
    reverted = s.get("reverted", []) or []
    risks = s.get("risks", []) or []
    if reverted or risks:
        lines.append("**Risk / reverted**")
        for r in reverted:
            lines.append(f"- ~~{r.get('title','(item)')}~~ reverted — {r.get('reason','')}")
        for r in risks:
            tref = f" → {r['task']}" if r.get("task") else ""
            lines.append(f"- ⚠ {r.get('title','(risk)')}{tref}")
        lines.append("")
    lines.append("_actions:_ See full report · Run again · Explain revert")
    return "\n".join(lines).rstrip() + "\n"


def load_summary(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError("summary.json must be a JSON object")
    return data


def _force_utf8() -> None:
    """The digest carries box-drawing/● glyphs; guarantee UTF-8 stdout on any console."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass


def main(argv: list[str] | None = None) -> int:
    _force_utf8()
    ap = argparse.ArgumentParser(description="Render a kaizen daily digest from summary.json")
    ap.add_argument("summary")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--status", action="store_true", help="print the one-line status only")
    g.add_argument("--json", action="store_true", help="print the normalized summary")
    args = ap.parse_args(argv)
    try:
        s = load_summary(args.summary)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"render_digest: cannot read {args.summary}: {exc}", file=sys.stderr)
        return 2
    if args.status:
        print(status_line(s))
    elif args.json:
        print(json.dumps(s, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(s), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
