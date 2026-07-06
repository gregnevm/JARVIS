#!/usr/bin/env python3
"""Task-success eval — перевірка кінцевого стану live-стека, не формату тексту.

Закриває прогалину «eval міряє формат/стиль, не користь» (DESIGN §9.3;
`docs/COMPETITIVE_ANALYSIS.md` §3.7 — паттерн Terminal-Bench: сценарій →
перевірка end-state, метрика = % resolved + latency). Доповнює run_eval.py
(формат) і gate.py (LoRA-промоушен): цей харнес ганяє **живі** HTTP-контракти
сервісів — health, tool-контракти, security-контракти (guard/sandbox/authority).

Сценарії read-only/ідемпотентні — безпечно ганяти на робочому персональному
стеку. Мутуючі task-сценарії додаються лише зі своїм teardown.

Usage:
  python training/eval/task_success.py                     # increment: increm
  python training/eval/task_success.py --min-pass-pct 90   # gate-режим (exit 1)
  python training/eval/task_success.py --only security     # одна категорія
Бази сервісів: TOOLS_URL/GATEWAY_URL/MEMORY_URL/TWIN_URL або --tools-url тощо.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import httpx

SCENARIOS_PATH = Path(__file__).resolve().parent / "task_scenarios.json"

_DEFAULT_BASES = {
    "tools": os.environ.get("TOOLS_URL", "http://127.0.0.1:8200"),
    "gateway": os.environ.get("GATEWAY_URL", "http://127.0.0.1:8000"),
    "memory": os.environ.get("MEMORY_URL", "http://127.0.0.1:8100"),
    "twin": os.environ.get("TWIN_URL", "http://127.0.0.1:8765"),
}


def load_scenarios(path: Path = SCENARIOS_PATH) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("task_scenarios.json: очікується список сценаріїв")
    return data


def _extract_text(body: Any, field: str) -> str:
    if field == "*":
        return json.dumps(body, ensure_ascii=False)
    if isinstance(body, dict):
        return str(body.get(field, ""))
    return str(body)


def check(expect: dict[str, Any], response: httpx.Response) -> tuple[bool, str]:
    """Один expect-блок → (ok, reason). Невідомий тип — fail-closed."""
    kind = str(expect.get("type", ""))
    if kind == "status":
        want = int(expect.get("code", 200))
        ok = response.status_code == want
        return ok, f"status {response.status_code} (очік. {want})"
    try:
        body = response.json()
    except ValueError:
        body = response.text
    if kind == "json_key":
        key = str(expect.get("key", ""))
        ok = isinstance(body, dict) and key in body
        return ok, f"json-ключ '{key}' {'є' if ok else 'відсутній'}"
    if kind == "contains_any":
        field = str(expect.get("field", "*"))
        text = _extract_text(body, field)
        needles = [str(n) for n in expect.get("any", [])]
        hit = next((n for n in needles if n in text), None)
        return hit is not None, (
            f"'{hit}' у полі '{field}'" if hit else f"жодного з {needles} у полі '{field}'"
        )
    return False, f"невідомий тип перевірки '{kind}' (fail-closed)"


def run_scenario(
    sc: dict[str, Any], client: httpx.Client, bases: dict[str, str]
) -> dict[str, Any]:
    req = sc["request"]
    base = bases[str(req.get("service", "tools"))]
    url = base + str(req["path"])
    started = time.perf_counter()
    try:
        response = client.request(
            str(req.get("method", "GET")), url, json=req.get("json"), timeout=30.0
        )
    except httpx.HTTPError as exc:
        return {"id": sc["id"], "ok": False, "latency_ms": None, "reason": f"HTTP: {exc}"}
    latency_ms = round((time.perf_counter() - started) * 1000)
    reasons: list[str] = []
    ok = True
    for expect in sc.get("expect", [{"type": "status"}]):
        passed, reason = check(expect, response)
        reasons.append(reason)
        ok = ok and passed
    return {"id": sc["id"], "ok": ok, "latency_ms": latency_ms, "reason": "; ".join(reasons)}


def run_all(
    scenarios: list[dict[str, Any]],
    bases: dict[str, str] | None = None,
    *,
    only: str = "",
    client: httpx.Client | None = None,
) -> list[dict[str, Any]]:
    bases = {**_DEFAULT_BASES, **(bases or {})}
    if only:
        scenarios = [s for s in scenarios if s.get("category") == only]
    own_client = client is None
    cl = client or httpx.Client()
    try:
        return [run_scenario(sc, cl, bases) for sc in scenarios]
    finally:
        if own_client:
            cl.close()


def summarize(results: list[dict[str, Any]]) -> tuple[float, str]:
    total = len(results)
    passed = sum(1 for r in results if r["ok"])
    pct = (100.0 * passed / total) if total else 0.0
    lines = [
        f"{'✅' if r['ok'] else '❌'} {r['id']:<28} "
        f"{(str(r['latency_ms']) + 'ms').rjust(7) if r['latency_ms'] is not None else '   —   '}  {r['reason']}"
        for r in results
    ]
    lines.append(f"task-success: {passed}/{total} passed ({pct:.1f}%)")
    return pct, "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-pass-pct", type=float, default=0.0, help="gate: <pct → exit 1")
    ap.add_argument("--only", default="", help="лише категорія (health/tools/security/authority/ops)")
    ap.add_argument("--tools-url", default="")
    ap.add_argument("--gateway-url", default="")
    ap.add_argument("--memory-url", default="")
    ap.add_argument("--twin-url", default="")
    args = ap.parse_args()
    bases = {
        k: v
        for k, v in {
            "tools": args.tools_url,
            "gateway": args.gateway_url,
            "memory": args.memory_url,
            "twin": args.twin_url,
        }.items()
        if v
    }
    results = run_all(load_scenarios(), bases, only=args.only)
    pct, report = summarize(results)
    print(report)
    if args.min_pass_pct and pct < args.min_pass_pct:
        print(f"GATE FAIL: {pct:.1f}% < {args.min_pass_pct}%")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
