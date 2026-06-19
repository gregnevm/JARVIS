#!/usr/bin/env python3
"""Kaizen ledger — 5h-window budget + resume-pointer + summary assembly (offline, pure).

Implements the window/budget logic of engine/loop-contract.md and the L5 resume-pointer, plus a
deterministic `summary.json` builder the digest renderer consumes. No services, no LLM.

Files under ``<artifact_dir>/``:
  window.json  { window_start, window_hours, iterations:[{i,start,end,minutes,ok,note}], avg_iter_minutes }
  resume.json  { run_id, iter, task, phase, branch }
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from typing import Any

_FMT = "%Y-%m-%dT%H:%M:%S"


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _parse(ts: str) -> datetime:
    return datetime.strptime(ts.split("+")[0].split(".")[0], _FMT).replace(tzinfo=timezone.utc)


def _read(path: str) -> dict[str, Any]:
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as fh:
        data: dict[str, Any] = json.load(fh)
    return data


def _write(path: str, data: dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, path)  # atomic — a hard stop never leaves a half-written pointer


class Ledger:
    def __init__(self, artifact_dir: str, window_hours: float = 5.0) -> None:
        self.window_path = os.path.join(artifact_dir, "window.json")
        self.resume_path = os.path.join(artifact_dir, "resume.json")
        self.window_hours = window_hours

    # --- window ---
    def open_window(self, now: datetime | None = None) -> dict[str, Any]:
        w = _read(self.window_path)
        if not w:
            w = {"window_start": (now or _now()).strftime(_FMT), "window_hours": self.window_hours,
                 "iterations": [], "avg_iter_minutes": 0.0}
            _write(self.window_path, w)
        return w

    def record_iteration(self, i: int, start: datetime, end: datetime, ok: bool, note: str = "") -> dict[str, Any]:
        w = self.open_window()
        minutes = round((end - start).total_seconds() / 60, 1)
        w["iterations"].append({"i": i, "start": start.strftime(_FMT), "end": end.strftime(_FMT),
                                "minutes": minutes, "ok": ok, "note": note})
        mins = [it["minutes"] for it in w["iterations"]]
        w["avg_iter_minutes"] = round(sum(mins) / len(mins), 1)
        _write(self.window_path, w)
        return w

    def remaining_minutes(self, now: datetime | None = None) -> float:
        w = self.open_window()
        elapsed = ((now or _now()) - _parse(w["window_start"])).total_seconds() / 60
        return round(w["window_hours"] * 60 - elapsed, 1)

    def should_wind_down(self, now: datetime | None = None) -> bool:
        w = self.open_window()
        avg = w.get("avg_iter_minutes") or 0.0
        if avg <= 0:
            return False  # no burn data yet — cannot predict, keep going
        return self.remaining_minutes(now) < avg * 1.3

    # --- resume pointer (L5) ---
    def set_resume(self, run_id: str, it: int, task: str, phase: str, branch: str) -> None:
        _write(self.resume_path, {"run_id": run_id, "iter": it, "task": task, "phase": phase, "branch": branch})

    def get_resume(self) -> dict[str, Any]:
        return _read(self.resume_path)

    def clear_resume(self) -> None:
        if os.path.exists(self.resume_path):
            os.remove(self.resume_path)


def build_summary(*, run_id: str, day: int, iters: int, duration_min: float, ci: str,
                  kaizen_score: int, score_delta: int, score_history: list[int],
                  shipped: list[dict[str, Any]], tests_delta: str, tokens: dict[str, Any],
                  reverted: list[dict[str, Any]] | None = None, risks: list[dict[str, Any]] | None = None,
                  meta_kr: dict[str, Any] | None = None) -> dict[str, Any]:
    """Assemble the stable summary.json the digest renderer consumes (digest-format.md)."""
    felt = any(s.get("before") and s.get("after") for s in shipped)
    return {
        "run_id": run_id, "day": day, "iters": iters, "duration_min": duration_min, "ci": ci,
        "kaizen_score": kaizen_score, "score_delta": score_delta, "score_history": score_history,
        "shipped": shipped, "tests_delta": tests_delta, "tokens": tokens,
        "reverted": reverted or [], "risks": risks or [],
        "meta_kr": meta_kr or {"felt": felt, "green_streak": 0, "eco_no_local_violation": False, "drift": 0},
    }


def _selfcheck() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        led = Ledger(d, window_hours=5.0)
        start = _parse("2026-06-18T09:00:00")
        led.open_window(now=start)
        led.record_iteration(1, start, _parse("2026-06-18T09:18:00"), ok=True, note="blast-radius")
        w = _read(led.window_path)
        assert w["avg_iter_minutes"] == 18.0, w
        # 18-min avg, near window start -> plenty remaining -> no wind-down
        assert led.should_wind_down(now=_parse("2026-06-18T09:30:00")) is False
        # 5 min from the 5h edge with an 18-min avg -> wind down
        assert led.should_wind_down(now=_parse("2026-06-18T13:55:00")) is True
        led.set_resume("2026-06-18-1", 2, "CA-4.1", "review", "claude/kaizen")
        assert led.get_resume()["task"] == "CA-4.1"
        s = build_summary(run_id="2026-06-18-1", day=7, iters=1, duration_min=18, ci="green",
                          kaizen_score=78, score_delta=6, score_history=[72, 78],
                          shipped=[{"title": "x", "before": "a", "after": "b"}],
                          tests_delta="+24", tokens={"total": 1000})
        assert s["meta_kr"]["felt"] is True
        print("ledger self-check ok: avg=", w["avg_iter_minutes"], "remaining@13:55=", led.remaining_minutes(_parse("2026-06-18T13:55:00")))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "remaining":
        print(Ledger(sys.argv[2]).remaining_minutes())
    else:
        _selfcheck()
