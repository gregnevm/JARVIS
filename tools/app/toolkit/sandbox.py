"""Kernel-sandbox для code_exec — bwrap-ізоляція процесу (fail-closed).

Закриває guardrail-борг «`subprocess -I` не повний sandbox» (AGENTS.md §5)
паттерном поля 2026 — OS-native sandbox за замовчуванням, відмова замість
мовчазного виконання поза пісочницею (`docs/COMPETITIVE_ANALYSIS.md` §3.5:
QwenPaw Bubblewrap/Landlock, Open Interpreter fail-closed).

Три рівні деградації (керує `CODE_EXEC_REQUIRE_SANDBOX`, default true):
  1. bwrap є → повна ізоляція: RO-биндимо лише /usr (+системні симлінки),
     tmpfs-/tmp як cwd, `--unshare-all` (без мережі), `--clearenv` (секрети
     .env-процесу невидимі), `--die-with-parent`.
  2. bwrap нема, require_sandbox=true → ВІДМОВА з поясненням (fail-closed).
  3. bwrap нема, require_sandbox=false → legacy `python -I` + rlimits
     (свідомий opt-out оператора; guard-скринінг лишається чинним).

Rlimits (CPU/AS/FSIZE/NPROC) ставляться в обох виконуваних режимах — усередині
bwrap вони успадковуються через preexec, тож таймаут не єдина стеля.

Примітка docker: дефолтний seccomp-профіль може блокувати user namespaces —
тоді bwrap падає на старті; ловимо і чесно повертаємо відмову (рівень 2), а не
тихий фолбек. Опції: compose-override seccomp або свідомий opt-out (рівень 3).
"""
from __future__ import annotations

import resource
import shutil
import subprocess
import sys

from ..config import settings

# --ro-bind-try терпить відсутні шляхи (musl/alpine vs debian). /usr покриває
# і /usr/local (python:slim). Жодного bind /app, /data, $HOME — код їх не бачить.
_BWRAP_ARGS: tuple[str, ...] = (
    "--ro-bind", "/usr", "/usr",
    "--ro-bind-try", "/lib", "/lib",
    "--ro-bind-try", "/lib64", "/lib64",
    "--ro-bind-try", "/bin", "/bin",
    "--ro-bind-try", "/sbin", "/sbin",
    "--proc", "/proc",
    "--dev", "/dev",
    "--tmpfs", "/tmp",
    "--unshare-all",
    "--die-with-parent",
    "--new-session",
    "--clearenv",
    "--setenv", "PATH", "/usr/local/bin:/usr/bin:/bin",
    "--setenv", "PYTHONDONTWRITEBYTECODE", "1",
    "--chdir", "/tmp",
)

SANDBOX_UNAVAILABLE = (
    "Пісочниця недоступна (bwrap не знайдено або заблоковано), а "
    "CODE_EXEC_REQUIRE_SANDBOX=true — виконання відхилено (fail-closed). "
    "Встанови bubblewrap у tools-образі або свідомо вимкни прапор."
)


def bwrap_path() -> str | None:
    return shutil.which("bwrap")


def build_argv(code: str, *, bwrap: str | None) -> list[str]:
    """argv для запуску `code`; з bwrap — обгорнутий, без — legacy `-I`."""
    python_cmd = [sys.executable, "-I", "-c", code]
    if bwrap:
        return [bwrap, *_BWRAP_ARGS, *python_cmd]
    return python_cmd


def _set_rlimits() -> None:
    mem = max(64, int(settings.code_exec_memory_mb)) * 1024 * 1024
    cpu = max(1, int(settings.code_exec_timeout) + 1)
    resource.setrlimit(resource.RLIMIT_AS, (mem, mem))
    resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
    resource.setrlimit(resource.RLIMIT_FSIZE, (8 * 1024 * 1024, 8 * 1024 * 1024))
    try:
        resource.setrlimit(resource.RLIMIT_NPROC, (64, 64))
    except (ValueError, OSError):
        pass  # у контейнері поточний usage може перевищувати стелю — не критично


def run_python(code: str) -> subprocess.CompletedProcess[str] | str:
    """Виконати код у найсуворішому доступному режимі; str = причина відмови."""
    bwrap = bwrap_path()
    if bwrap is None and settings.code_exec_require_sandbox:
        return SANDBOX_UNAVAILABLE
    argv = build_argv(code, bwrap=bwrap)
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=settings.code_exec_timeout,
            preexec_fn=_set_rlimits,
        )
    except subprocess.TimeoutExpired:
        return f"Таймаут ({settings.code_exec_timeout}s)."
    # bwrap не стартував (docker seccomp блокує namespaces) — fail-closed, не фолбек.
    if bwrap and proc.returncode != 0 and "bwrap:" in (proc.stderr or ""):
        if settings.code_exec_require_sandbox:
            return SANDBOX_UNAVAILABLE
        return subprocess.run(
            build_argv(code, bwrap=None),
            capture_output=True,
            text=True,
            timeout=settings.code_exec_timeout,
            preexec_fn=_set_rlimits,
        )
    return proc
