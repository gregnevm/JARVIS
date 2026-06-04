"""Перевірки перед promote LoRA."""
from __future__ import annotations

from typing import Any


def eval_promote_denied(row: dict[str, Any], min_eval: float) -> str | None:
    if min_eval <= 0:
        return None
    score = row.get("eval_score")
    if score is None:
        return f"eval_score missing; required >= {min_eval}"
    try:
        val = float(score)
    except (TypeError, ValueError):
        return f"invalid eval_score: {score!r}"
    if val < min_eval:
        return f"eval_score {val} < min_eval_promote {min_eval}"
    return None
