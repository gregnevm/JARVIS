"""Pre-commit lint gate (CA-5.5) — turnkey P10 post_tool-хук.

Після кожної успішної правки коду (`code_edit`/`code_edit_batch`, у т.ч. mode
`rename_symbol`) автоматично ганяє lint і дописує підсумок до результату, який бачить
агент. Так проблеми спливають ОДРАЗУ після правки — до того, як агент закомітить.

Вмикається одним прапором `CODING_PRECOMMIT_GATE=true` (built-in, без копіювання
файлів у `data/hooks/`). Лінтер — `CODING_PRECOMMIT_LINT_EXE`/`_ARGS`/`_PATH`.
Хук read-only (лінт нічого не пише) і ніколи не валить tool-результат: помилка
гейта → повертаємо результат без змін.
"""
from __future__ import annotations

import logging
from typing import Any

from .config import settings

logger = logging.getLogger("jarvis.tools.precommit_gate")

# `rename_symbol` — це mode `code_edit`/`code_edit_batch`, не окремий tool-name,
# тож у `ctx["tool"]` він не з'являється (dispatch має лише ці два хендлери).
_EDIT_TOOLS = frozenset({"code_edit", "code_edit_batch"})


def _edit_succeeded(result: str) -> bool:
    """Правку застосовано (а не confirm-маркер / помилка / dry-run)?"""
    r = result or ""
    if "[[COMPUTER_CONFIRM:" in r or "Dry-run" in r:
        return False
    return "✅" in r


async def run(ctx: dict[str, Any]) -> dict[str, Any] | None:
    """P10 post_tool-хук: лінт-гейт після правок коду. None = без змін."""
    if not settings.coding_precommit_gate:
        return None
    tool = str(ctx.get("tool") or "")
    if tool not in _EDIT_TOOLS:
        return None
    result = str(ctx.get("result") or "")
    if not _edit_succeeded(result):
        return None
    try:
        from .tools.check_tools import run_lint

        args = [a for a in settings.coding_precommit_lint_args.split() if a]
        summary = await run_lint(
            settings.coding_precommit_lint_exe,
            args=args,
            path=settings.coding_precommit_path,
            user_id=int(ctx.get("user_id") or 0),
        )
    except Exception as exc:  # noqa: BLE001 — гейт не має валити основний результат
        logger.warning("precommit gate lint failed: %s", exc)
        return None
    gated = f"{result}\n\n— pre-commit gate (lint) —\n{summary}"
    return {**ctx, "result": gated}
