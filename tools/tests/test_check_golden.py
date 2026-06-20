"""Golden trace (CA-3 part): інтерпретація виводу раннерів → структурований підсумок.

Детермінований шар CA-3.5 (зламаний тест → структурований FAIL зі списком впалих);
live-fix-цикл моделлю — окремо в eval, не тут.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.tools.check_tools import _summarize_lint, _summarize_pytest

_GOLDEN = json.loads(
    (Path(__file__).parent / "golden" / "check_output.json").read_text(encoding="utf-8")
)


@pytest.mark.parametrize("case", _GOLDEN, ids=lambda c: c["id"])
def test_check_output_golden(case: dict) -> None:
    if case["kind"] == "tests":
        out = _summarize_pytest(case["stdout"], "", case["code"])
    else:
        out = _summarize_lint(case["framework"], case["stdout"], "", case["code"])
    for sub in case["expect_substrings"]:
        assert sub in out, f"{case['id']}: missing {sub!r} in:\n{out}"
    for sub in case.get("expect_absent", []):
        assert sub not in out, f"{case['id']}: unexpected {sub!r} in:\n{out}"
