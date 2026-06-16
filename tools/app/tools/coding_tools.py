"""Рідні repo-aware coding-інструменти (Стовп B / CODING_AGENT_ROADMAP).

Read-only інтелект про репозиторій поверх host-agent FS — НЕ мутує код:

* ``repo_tree``    (CA-2.1) — gitignore-aware дерево файлів (через ``rg --files``).
* ``repo_grep``    (CA-2.2) — ripgrep по workspace з лімітом результатів.
* ``code_read``    (CA-1.4) — читання файлу з line-range (економія токенів vs весь файл).
* ``repo_symbols`` (CA-2.3) — outline символів файлу (Python ``ast``; regex-фолбек для решти).

**Безпека.** Усі три рідуть на тому самому trust-кордоні, що `run_cli`/`fs_read`:
owner-gate (`COMPUTER_OWNER_USER_IDS`) + `ENABLE_COMPUTER_USE` — перевіряється у
`toolkit.dispatch` (набір `_CODING_TOOLS`). Додатково за прапором `ENABLE_CODING_TOOLS`
(нова фіча за прапором, дефолт false — AGENTS.md §5). `rg` за дефолтом пропускає
hidden/.gitignore, АЛЕ `rg -g '.env'` РЕ-ВКЛЮЧАЄ ignored-файл — тож проти витоку
секретів додаємо трейлінг deny-глоби (`_SECRET_DENY`), які user-glob не може перебити.

`repo_tree`/`repo_grep` ходять через host-agent `/cli` (owner-trusted, як `run_cli`);
`code_read` — через `/fs/read` (скоупиться `HOSTAGENT_FS_ROOTS`).
"""
from __future__ import annotations

import re
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


# Захист від витоку секретів: `rg -g '<name>'` РЕ-ВКЛЮЧАЄ навіть .gitignore-файл
# (перевірено емпірично). Тож після будь-якого user-glob додаємо ці exclude-глоби —
# у ripgrep останній glob виграє, отже user не може їх перебити.
_SECRET_DENY: tuple[str, ...] = (
    ".env", ".env.*", "*.env",
    ".git", ".jarvis_backup",
    "*.pem", "*.key", "*.pfx", "*.p12", "*.crt",
    "id_rsa", "id_rsa.*", "id_ed25519", "id_ed25519.*",
    "*.secret", "*secrets*",
    "*.pyc",
)


def _deny_globs() -> list[str]:
    out: list[str] = []
    for pat in _SECRET_DENY:
        out += ["-g", f"!{pat}"]
    return out


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

    data = await _cli("rg", ["--files", *_deny_globs()], root)
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
    args += _deny_globs()  # після user-glob → виграє (немає витоку .env/ключів)
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


# --- repo_refs (CA-4.5 foundation / CB3) -------------------------------------

# Ідентифікатор або dotted-модуль (tools.app.agent) — без regex-метасимволів,
# тож безпечно віддати ripgrep як -w слово.
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$")
_IMPORT_LINE_RE = re.compile(r"^\s*(?:from\s+\S+\s+import\b|import\s+)")


def _split_grep_row(row: str) -> tuple[str, str]:
    """'path:line:content' → (locator='path:line', content). Стійко до ':' у вмісті."""
    parts = row.split(":", 2)
    if len(parts) == 3:
        return f"{parts[0]}:{parts[1]}", parts[2]
    return row, row


async def repo_refs(
    name: str,
    *,
    path: str = "",
    glob: str = "",
    max_results: int = 0,
    user_id: int = 0,
) -> str:
    """Крос-файлові посилання на символ/модуль (read-only). Розділяє import-рядки
    й usage-рядки — основа для rename/move рефактора (CA-4.5) та огляду залежностей."""
    msg = _disabled_message()
    if msg:
        return msg
    ident = (name or "").strip()
    if not ident or not _IDENT_RE.match(ident):
        return (
            "repo_refs: name має бути ідентифікатором або dotted-модулем "
            "(напр. AgentRunner або tools.app.agent)."
        )
    seg = ident.split(".")[-1]  # останній сегмент ловить `mod.attr` і `from mod import attr`
    root = (path or "").strip() or "."
    limit = int(max_results) if max_results else settings.coding_grep_max_results
    limit = max(1, min(limit, 500))

    args = ["--line-number", "--no-heading", "--color", "never", "--max-columns", "200", "-w"]
    g = (glob or "").strip()
    args += ["-g", g] if g else ["-g", "*.py"]  # дефолт — Python
    args += _deny_globs()
    args += ["--", seg]

    data = await _cli("rg", args, root)
    if "error" in data:
        return str(data["error"])
    code = int(data.get("code", -1))
    stdout = str(data.get("stdout", ""))
    if code == 1 and not stdout.strip():
        return f"repo_refs: посилань на {ident!r} не знайдено у {root}."
    if code not in (0, 1) and not stdout.strip():
        stderr = str(data.get("stderr", "")).strip()
        return f"repo_refs: rg помилка (code={code}). {stderr[:200]}"

    rows = [ln for ln in stdout.splitlines() if ln.strip()]
    imports: list[str] = []
    usages: list[str] = []
    for ln in rows:
        _loc, content = _split_grep_row(ln)
        (imports if _IMPORT_LINE_RE.match(content) else usages).append(ln)

    parts_out: list[str] = [
        f"repo_refs {ident!r} у {root}: {len(rows)} посилань "
        f"(import={len(imports)}, usage={len(usages)})"
    ]
    if imports:
        parts_out.append("— import-сайти:")
        parts_out += [f"  {ln}" for ln in imports[:limit]]
    if usages:
        shown = usages[: max(0, limit - len(imports[:limit]))]
        parts_out.append(f"— usage-сайти{' (зрізано)' if len(usages) > len(shown) else ''}:")
        parts_out += [f"  {ln}" for ln in shown]
    return _clip("\n".join(parts_out))


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


# --- repo_symbols (CA-2.3) ---------------------------------------------------

def _py_symbols(content: str) -> list[str]:
    """Outline .py-файлу через stdlib ``ast`` (точно: сигнатури, вкладеність, рядки)."""
    import ast

    tree = ast.parse(content)
    out: list[str] = []
    imports: list[str] = []

    def sig(node: ast.AST, depth: int) -> None:
        pad = "  " * depth
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            kw = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
            try:
                argstr = ast.unparse(node.args)
            except Exception:
                argstr = "…"
            ret = ""
            if node.returns is not None:
                try:
                    ret = f" -> {ast.unparse(node.returns)}"
                except Exception:
                    ret = ""
            out.append(f"L{node.lineno}\t{pad}{kw} {node.name}({argstr}){ret}")
        elif isinstance(node, ast.ClassDef):
            try:
                bases = ", ".join(ast.unparse(b) for b in node.bases)
            except Exception:
                bases = ""
            head = f"{node.name}({bases})" if bases else node.name
            out.append(f"L{node.lineno}\t{pad}class {head}")
        for child in getattr(node, "body", []):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                sig(child, depth + 1)

    for node in tree.body:
        if isinstance(node, ast.Import):
            imports += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            imports += [f"{mod}.{a.name}" for a in node.names]
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            sig(node, 0)
    if imports:
        out.append("imports: " + ", ".join(imports[:40]))
    return out


# Regex-фолбек для не-Python (одне визначення на рядок; евристика, не парсер).
_DEF_RE = re.compile(
    r"^\s*(?:export\s+)?(?:default\s+)?(?:public\s+|private\s+|protected\s+|static\s+)*"
    r"(?:async\s+)?(?:function|func|class|interface|type|struct|enum|def|fn|impl|trait)\b"
    r".*",
)


def _regex_symbols(content: str) -> list[str]:
    out: list[str] = []
    for i, line in enumerate(content.splitlines(), start=1):
        if _DEF_RE.match(line):
            out.append(f"L{i}\t{line.strip()[:160]}")
    return out


async def repo_symbols(path: str, *, pattern: str = "", user_id: int = 0) -> str:
    msg = _disabled_message()
    if msg:
        return msg
    target = (path or "").strip()
    if not target:
        return "path обов'язковий для repo_symbols."

    from ..computer import _request

    data = await _request("GET", "/fs/read", params={"path": target})
    if "error" in data:
        return str(data["error"])
    content = str(data.get("content", ""))

    is_py = target.lower().endswith((".py", ".pyi"))
    if is_py:
        try:
            symbols = _py_symbols(content)
        except SyntaxError as exc:
            return f"repo_symbols: не вдалося розпарсити Python ({exc.msg}, рядок {exc.lineno})."
    else:
        symbols = _regex_symbols(content)

    pat = (pattern or "").strip()
    if pat:
        try:
            rx = re.compile(pat)
            symbols = [s for s in symbols if rx.search(s)]
        except re.error as exc:
            return f"repo_symbols: невалідний pattern ({exc})."

    if not symbols:
        kind = "Python ast" if is_py else "regex"
        return f"repo_symbols ({kind}): символів не знайдено у {target}."
    kind = "ast" if is_py else "regex"
    header = f"Символи {data.get('path', target)} ({kind}, {len(symbols)}):"
    return _clip(f"{header}\n" + "\n".join(symbols))
