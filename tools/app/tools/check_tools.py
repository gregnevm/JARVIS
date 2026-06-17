"""Тест/лінт-раннери зі структурованим виводом (Стовп B / CA-3.1, CA-3.3).

`run_tests`/`run_lint` запускають раннер через host-agent ``/cli`` і повертають
**структурований** підсумок (passed/failed/errors + хвіст), щоб модель могла вести
fix-цикл (CA-3.2) у наявному ReAct-лупі: run_tests → code_edit → run_tests.

**Безпека.** Той самий owner+`ENABLE_COMPUTER_USE`+`ENABLE_CODING_TOOLS` кордон, що й
repo-інструменти (набір `_CODING_TOOLS` у dispatch). `exe` обмежено алловлистом
раннерів (блокує прямий `rm`/`curl` як exe), args — списком (без шелу → без ін'єкції).
⚠️ Це НЕ пісочниця: інтерпретатори в алловлисті (`python -c`, `node -e`, `npx …`)
можуть виконати довільний код — але це в межах того ж owner-trust, що `run_cli`/
`code_exec`, які власник уже має; ескалації capability немає.
"""
from __future__ import annotations

import re
from pathlib import PureWindowsPath
from typing import Any

from . import fix_loop
from .coding_tools import _cli, _clip, _disabled_message

# Дозволені раннери (basename, lower) — не довільний exe.
_TEST_RUNNERS = frozenset({
    "python", "python.exe", "python3", "py", "py.exe",
    "pytest", "pytest.exe", "tox",
    "npm", "npm.cmd", "npx", "npx.cmd", "node", "yarn", "pnpm",
    "jest", "vitest", "go", "cargo",
})
_LINT_RUNNERS = frozenset({
    "python", "python.exe", "python3", "py", "py.exe",
    "mypy", "ruff", "flake8", "black", "isort", "pyright",
    "npx", "npx.cmd", "tsc", "eslint", "node",
})


def _basename(exe: str) -> str:
    # PureWindowsPath трактує і '/', і '\' як роздільники → коректно для
    # exe-шляхів від Windows host-agent навіть коли tools крутиться на Linux.
    return PureWindowsPath(exe.strip().strip('"')).name.lower()


def _coerce_args(raw: Any) -> list[str]:
    if isinstance(raw, list):
        return [str(a) for a in raw]
    if isinstance(raw, str) and raw.strip():
        return raw.split()
    return []


def _tail(text: str, n: int = 25) -> str:
    lines = [ln for ln in text.splitlines() if ln.strip()]
    return "\n".join(lines[-n:])


# --- parsers -----------------------------------------------------------------

def _summarize_pytest(stdout: str, stderr: str, code: int) -> str:
    blob = stdout + "\n" + stderr

    def _count(word: str) -> int:
        m = re.search(rf"(\d+)\s+{word}", blob)
        return int(m.group(1)) if m else 0

    passed, failed = _count("passed"), _count("failed")
    errors, skipped = _count("error"), _count("skipped")
    failed_names = re.findall(r"^FAILED\s+(\S+)", blob, re.MULTILINE)[:20]
    verdict = "✅ PASS" if (code == 0 and failed == 0 and errors == 0) else "❌ FAIL"
    head = (
        f"pytest {verdict} — passed={passed} failed={failed} "
        f"errors={errors} skipped={skipped} (exit {code})"
    )
    parts = [head]
    if failed_names:
        parts.append("failed:\n" + "\n".join(f"  {n}" for n in failed_names))
    parts.append("---\n" + _tail(blob))
    return "\n".join(parts)


def _summarize_lint(tool: str, stdout: str, stderr: str, code: int) -> str:
    blob = stdout + "\n" + stderr
    if tool == "mypy":
        if "Success: no issues" in blob:
            return f"mypy ✅ PASS (exit {code})\n{_tail(blob, 4)}"
        m = re.search(r"Found (\d+) error", blob)
        n = m.group(1) if m else "?"
        return f"mypy ❌ {n} errors (exit {code})\n---\n{_tail(blob)}"
    if tool == "ruff":
        m = re.search(r"Found (\d+) error", blob)
        if code == 0 and not m:
            return f"ruff ✅ PASS (exit {code})\n{_tail(blob, 4)}"
        n = m.group(1) if m else "?"
        return f"ruff ❌ {n} issues (exit {code})\n---\n{_tail(blob)}"
    verdict = "✅ PASS" if code == 0 else "❌ FAIL"
    return f"{tool} {verdict} (exit {code})\n---\n{_tail(blob)}"


def _detect(exe: str, args: list[str], hint: str) -> str:
    if hint and hint != "auto":
        return hint
    joined = (exe + " " + " ".join(args)).lower()
    for k in ("pytest", "mypy", "ruff", "jest", "vitest", "eslint", "tsc", "go", "cargo"):
        if k in joined:
            return k
    return "generic"


# --- public tools ------------------------------------------------------------

async def run_tests(
    exe: str,
    *,
    args: Any = None,
    path: str = "",
    framework: str = "auto",
    user_id: int = 0,
) -> str:
    msg = _disabled_message()
    if msg:
        return msg
    e = (exe or "").strip()
    if not e:
        return "exe обов'язковий (напр. 'pytest' або 'python')."
    if _basename(e) not in _TEST_RUNNERS:
        return f"run_tests: '{_basename(e)}' не дозволений раннер тестів."
    arglist = _coerce_args(args)
    data = await _cli(e, arglist, (path or "").strip() or None)
    if "error" in data:
        return str(data["error"])
    stdout, stderr = str(data.get("stdout", "")), str(data.get("stderr", ""))
    code = int(data.get("code", -1))
    fw = _detect(e, arglist, framework)
    blob = stdout + "\n" + stderr
    if fw == "pytest":
        summary = _summarize_pytest(stdout, stderr, code)
        ok = "✅ PASS" in summary
        failed_names = sorted(re.findall(r"^FAILED\s+(\S+)", blob, re.MULTILINE))
        sig = "" if ok else fix_loop.fail_signature(failed_names or [_tail(blob, 6)])
    else:
        ok = code == 0
        verdict = "✅ PASS" if ok else "❌ FAIL"
        summary = f"{fw} {verdict} (exit {code})\n---\n{_tail(blob)}"
        sig = "" if ok else fix_loop.fail_signature([str(code), _tail(blob, 6)])
    note = await fix_loop.note_test_result(user_id, ok=ok, signature=sig)
    return _clip(summary) + note


async def run_lint(
    exe: str,
    *,
    args: Any = None,
    path: str = "",
    tool: str = "auto",
    user_id: int = 0,
) -> str:
    msg = _disabled_message()
    if msg:
        return msg
    e = (exe or "").strip()
    if not e:
        return "exe обов'язковий (напр. 'mypy' або 'ruff')."
    if _basename(e) not in _LINT_RUNNERS:
        return f"run_lint: '{_basename(e)}' не дозволений лінтер."
    arglist = _coerce_args(args)
    data = await _cli(e, arglist, (path or "").strip() or None)
    if "error" in data:
        return str(data["error"])
    stdout, stderr = str(data.get("stdout", "")), str(data.get("stderr", ""))
    code = int(data.get("code", -1))
    t = _detect(e, arglist, tool)
    return _clip(_summarize_lint(t, stdout, stderr, code))
