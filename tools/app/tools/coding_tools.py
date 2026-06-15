"""Рідні repo-aware coding-інструменти (Стовп B / CODING_AGENT_ROADMAP).

Read-only інтелект про репозиторій поверх host-agent FS — НЕ мутує код:

* ``repo_tree``  (CA-2.1) — gitignore-aware дерево файлів (через ``rg --files``).
* ``repo_grep``  (CA-2.2) — ripgrep по workspace з лімітом результатів.
* ``code_read``  (CA-1.4) — читання файлу з line-range (економія токенів vs весь файл).

**Безпека.** Усі три рідуть на тому самому trust-кордоні, що `run_cli`/`fs_read`:
owner-gate (`COMPUTER_OWNER_USER_IDS`) + `ENABLE_COMPUTER_USE` — перевіряється у
`toolkit.dispatch` (набір `_CODING_TOOLS`). Додатково за прапором `ENABLE_CODING_TOOLS`
(нова фіча за прапором, дефолт false — AGENTS.md §5). `rg --files`/`rg` за дефолтом
**пропускають hidden і .gitignore**, тож `.env`/`.git` не потрапляють у вивід.

`repo_tree`/`repo_grep` ходять через host-agent `/cli` (owner-trusted, як `run_cli`);
`code_read` — через `/fs/read` (скоупиться `HOSTAGENT_FS_ROOTS`).
"""
from __future__ import annotations

from typing import Any

from ..config import settings


def enabled() -> bool:
    """Інструменти активні лише за обома прапорами (фіча + computer-кордон)."""
    return bool(settings.enable_coding_tools and settings.enable_computer_use)


def _disabled_message() -> str | None:
    if not settings.enable_computer_use:
        return "Coding-інструменти потребують ENABLE_COMPUTER_USE=true."
    if not settings.enable_coding_tools:
        return "Coding-інструменти вимкнено (ENABLE_CODING_TOOLS=false)."
    return None


async def _cli(exe: str, args: list[str], cwd: str | None) -> dict[str, Any]:
    """Сирий виклик host-agent ``/cli`` (повертає stdout/stderr/code чи {'error'})."""
    from ..computer import _request

    return await _request("POST", "/cli", json={"exe": exe, "args": args, "cwd": cwd})


def _clip(text: str) -> str:
    from ..computer import _truncate

    return _truncate(text)


# --- repo_tree (CA-2.1) ------------------------------------------------------

def _build_tree(rel_paths: list[str], *, max_depth: int, max_entries: int) -> tuple[str, bool]:
    """Будує відступне дерево з плаского списку gitignore-aware шляхів.

    Повертає (текст, truncated). Шляхи з ``rg --files`` (cwd=root) — відносні.
    """
    # Нормалізуємо роздільники (Windows rg віддає '\') і фільтруємо за глибиною.
    norm: list[list[str]] = []
    for raw in rel_paths:
        parts = [p for p in raw.replace("\\", "/").split("/") if p]
        if parts:
            norm.append(parts)
    norm.sort()

    lines: list[str] = []
    seen_dirs: set[str] = set()
    truncated = False
    for parts in norm:
        if len(lines) >= max_entries:
            truncated = True
            break
        depth = len(parts) - 1  # глибина каталогу файлу
        # Вивести проміжні каталоги (до max_depth) один раз.
        for d in range(min(depth, max_depth)):
            prefix = "/".join(parts[: d + 1])
            if prefix not in seen_dirs:
                seen_dirs.add(prefix)
                lines.append(f"{'  ' * d}{parts[d]}/")
                if len(lines) >= max_entries:
                    truncated = True
                    break
        if truncated:
            break
        if depth <= max_depth:
            indent = "  " * depth
            lines.append(f"{indent}{parts[-1]}")
    return "\n".join(lines), truncated


async def repo_tree(path: str, *, max_depth: int = 3, user_id: int = 0) -> str:
    msg = _disabled_message()
    if msg:
        return msg
    root = (path or "").strip()
    if not root:
        return "path обов'язковий для repo_tree."
    depth = max(1, min(int(max_depth or 3), 8))

    data = await _cli("rg", ["--files"], root)
    if "error" in data:
        return str(data["error"])
    code = int(data.get("code", -1))
    stdout = str(data.get("stdout", ""))
    if code != 0 and not stdout.strip():
        stderr = str(data.get("stderr", "")).strip()
        return f"repo_tree: rg не повернув файлів (code={code}). {stderr[:200]}"

    rel = [ln for ln in stdout.splitlines() if ln.strip()]
    total = len(rel)
    tree, truncated = _build_tree(
        rel, max_depth=depth, max_entries=settings.coding_tree_max_entries
    )
    note = (
        f" [показано {settings.coding_tree_max_entries} з {total}; звузь path/max_depth]"
        if truncated
        else ""
    )
    header = f"Дерево {root} (файлів: {total}, depth≤{depth}){note}"
    return _clip(f"{header}\n{tree}" if tree else f"{header}\n(порожньо)")


# --- repo_grep (CA-2.2) ------------------------------------------------------

async def repo_grep(
    pattern: str,
    *,
    path: str = "",
    glob: str = "",
    max_results: int = 0,
    user_id: int = 0,
) -> str:
    msg = _disabled_message()
    if msg:
        return msg
    pat = (pattern or "").strip()
    if not pat:
        return "pattern обов'язковий для repo_grep."
    root = (path or "").strip() or "."
    limit = int(max_results) if max_results else settings.coding_grep_max_results
    limit = max(1, min(limit, 500))

    args = ["--line-number", "--no-heading", "--color", "never", "--max-columns", "200"]
    g = (glob or "").strip()
    if g:
        args += ["-g", g]
    args += ["--", pat]

    data = await _cli("rg", args, root)
    if "error" in data:
        return str(data["error"])
    code = int(data.get("code", -1))
    stdout = str(data.get("stdout", ""))
    if code == 1 and not stdout.strip():
        return f"repo_grep: немає збігів для {pat!r} у {root}."
    if code not in (0, 1) and not stdout.strip():
        stderr = str(data.get("stderr", "")).strip()
        return f"repo_grep: rg помилка (code={code}). {stderr[:200]}"

    rows = [ln for ln in stdout.splitlines() if ln.strip()]
    shown = rows[:limit]
    note = f" [показано {limit} з {len(rows)}+; звузь pattern/glob]" if len(rows) > limit else ""
    header = f"repo_grep {pat!r} у {root}{note}"
    return _clip(f"{header}\n" + "\n".join(shown))


# --- code_read (CA-1.4) ------------------------------------------------------

async def code_read(
    path: str,
    *,
    start_line: int = 0,
    end_line: int = 0,
    user_id: int = 0,
) -> str:
    msg = _disabled_message()
    if msg:
        return msg
    target = (path or "").strip()
    if not target:
        return "path обов'язковий для code_read."

    from ..computer import _request

    data = await _request("GET", "/fs/read", params={"path": target})
    if "error" in data:
        return str(data["error"])
    content = str(data.get("content", ""))
    lines = content.splitlines()
    n = len(lines)

    start = int(start_line) if start_line else 1
    end = int(end_line) if end_line else n
    start = max(1, start)
    end = min(n, end) if end else n
    if start > n:
        return f"code_read: файл має лише {n} рядків (start_line={start})."
    if end < start:
        end = start

    width = len(str(end))
    numbered = [f"{i:>{width}}\t{lines[i - 1]}" for i in range(start, end + 1)]
    trunc = " [обрізано host-agent]" if data.get("truncated") else ""
    header = f"Файл {data.get('path', target)} рядки {start}–{end} з {n}{trunc}"
    return _clip(f"{header}\n" + "\n".join(numbered))
