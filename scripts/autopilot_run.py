#!/usr/bin/env python3
"""One-shot прогін авто-корутини під наглядом (без зовнішніх сервісів).

Крутить ОДИН цикл `run_cycle` локальним диспатчем (`make_local_dispatch`):
реальний pytest + знімок репо + git diff; code/refactor — зафіксований план.
Зберігає OKR, run-log і дашборд у `<data-dir>`, друкує трасу.

Приклад:
    python scripts/autopilot_run.py --repo . --data-dir data \
        --tests jarvis_core/tests/test_okr.py gateway/tests/test_auto_coroutine.py
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "gateway"))
sys.path.insert(0, str(REPO_ROOT))

from app.auto_coroutine import (  # noqa: E402
    load_okr,
    make_local_dispatch,
    render_dashboard,
    run_cycle,
    save_dashboard,
    save_okr,
)
from app.auto_coroutine import append_run_log  # noqa: E402


async def _main() -> int:
    ap = argparse.ArgumentParser(description="Run one autopilot cycle locally")
    ap.add_argument("--repo", default=".", help="корінь репо для test/analyze фаз")
    ap.add_argument("--data-dir", default="data", help="де лежить okr/okr.json і пишуться артефакти")
    ap.add_argument("--user-id", type=int, default=42)
    ap.add_argument("--tests", nargs="*", default=None, help="pytest-таргети для test-фази")
    ap.add_argument("--bypass", action="store_true", help="режим Bypass permissions (auto, без підтверджень)")
    ap.add_argument("--ultracode", action="store_true", help="режим ULTRACODE (max-effort code/refactor)")
    args = ap.parse_args()

    okr = load_okr(args.data_dir)
    if not okr.objectives:
        print(f"❌ OKR порожній: немає {args.data_dir}/okr/okr.json")
        return 2

    dispatch = make_local_dispatch(args.repo, test_targets=args.tests, ultracode=args.ultracode)
    mode = "🔓 bypass" if args.bypass else "🔒 supervised"
    if args.ultracode:
        mode += " · ⚡ ULTRACODE"
    print(f"▶️  Старт циклу · режим={mode} · cycle={okr.cycle} · objectives={len(okr.objectives)}")

    new_okr, result = await run_cycle(
        okr, dispatch, user_id=args.user_id, repo_path=args.repo
    )
    if result is None:
        print("💤 Немає actionable-цілей — усі досягнуті/паузовані.")
        return 0

    print(f"\n🎯 Ціль: {result.objective_id} — {result.objective_title}")
    for stage_id, ok, summary in result.stages:
        print(f"  {'✅' if ok else '⚠️ '} {stage_id:<9} {summary}")

    save_okr(args.data_dir, new_okr)
    append_run_log(args.data_dir, result)
    save_dashboard(args.data_dir, new_okr, [result], bypass=args.bypass, ultracode=args.ultracode)

    print(f"\n📊 OKR прогрес: {okr.progress * 100:.0f}% → {new_okr.progress * 100:.0f}% · cycle={new_okr.cycle}")
    print(f"📝 run-log: {args.data_dir}/autopilot/run_log.md")
    print(f"📈 dashboard: {args.data_dir}/autopilot/dashboard.md")

    ok_all = result.ok_count == len(result.stages)
    print(f"\n{'🟢 Цикл зелений' if ok_all else '🟡 Цикл доїхав з попередженнями'}: {result.ok_count}/{len(result.stages)}")
    _ = render_dashboard  # експорт для тестів/REPL
    return 0 if ok_all else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
