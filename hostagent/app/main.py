"""JARVIS host-agent — керування Windows-хостом (PowerShell, CLI, FS).

Крутиться на хості поза Docker; контейнер tools звертається через host.docker.internal.
"""
from __future__ import annotations

import base64
import difflib
import hmac
import json
import logging
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from .config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("jarvis.hostagent")

app = FastAPI(title="JARVIS Host Agent")


def _check_token(x_hostagent_token: Annotated[str | None, Header()] = None) -> None:
    expected = settings.token
    if not expected:
        raise HTTPException(status_code=503, detail="hostagent token not configured")
    got = x_hostagent_token or ""
    if not hmac.compare_digest(got, expected):
        raise HTTPException(status_code=403, detail="forbidden")


class PowerShellRequest(BaseModel):
    script: str
    as_admin: bool = False
    timeout: float | None = None


class CliRequest(BaseModel):
    exe: str
    args: list[str] = Field(default_factory=list)
    cwd: str | None = None
    timeout: float | None = None


class FsWriteRequest(BaseModel):
    path: str
    content: str


class FsWriteBytesRequest(BaseModel):
    path: str
    data_b64: str


class FsEditRequest(BaseModel):
    """Атомарна правка файлу: search-replace АБО unified-diff (CODING_AGENT CA-1.1)."""

    path: str
    mode: str = "search_replace"  # "search_replace" | "diff"
    old_string: str = ""
    new_string: str = ""
    replace_all: bool = False
    diff: str = ""


class ClipboardWriteRequest(BaseModel):
    text: str


class UiaInvokeRequest(BaseModel):
    window: str = ""
    control_name: str = ""
    action: str = "click"


class PowerRequest(BaseModel):
    action: str
    delay_seconds: int = 60


class WolRequest(BaseModel):
    mac: str
    broadcast: str = "255.255.255.255"


class ScreenClickRequest(BaseModel):
    x: int
    y: int


class ScreenTypeRequest(BaseModel):
    text: str
    interval_ms: int = 0


class ScreenHotkeyRequest(BaseModel):
    keys: list[str] = Field(default_factory=list)


class ScreenScrollRequest(BaseModel):
    clicks: int = 0
    x: int | None = None
    y: int | None = None


def _timeout(req_timeout: float | None) -> float:
    return req_timeout if req_timeout is not None else settings.exec_timeout


def _run_powershell(script: str, as_admin: bool, timeout: float) -> dict[str, Any]:
    if as_admin:
        if not settings.allow_admin:
            raise HTTPException(status_code=403, detail="admin powershell disabled")
        return _run_powershell_admin(script, timeout)
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {"stdout": "", "stderr": f"timeout ({timeout}s)", "code": -1}
    return {"stdout": proc.stdout, "stderr": proc.stderr, "code": proc.returncode}


def _run_powershell_admin(script: str, timeout: float) -> dict[str, Any]:
    """Elevation через Start-Process -Verb RunAs (потребує UAC або pre-elevated host)."""
    if sys.platform != "win32":
        raise HTTPException(status_code=501, detail="admin powershell only on Windows")
    with tempfile.TemporaryDirectory() as tmp:
        out_path = Path(tmp) / "out.txt"
        err_path = Path(tmp) / "err.txt"
        code_path = Path(tmp) / "code.txt"
        inner = (
            f"& {{ {script} }} *> '{out_path}' 2> '{err_path}'; "
            f"$LASTEXITCODE | Out-File -Encoding ascii '{code_path}'"
        )
        ps_cmd = (
            f"Start-Process powershell -Verb RunAs -Wait -PassThru "
            f"-ArgumentList '-NoProfile','-NonInteractive','-Command',{json.dumps(inner)}"
        )
        try:
            proc = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return {"stdout": "", "stderr": f"timeout ({timeout}s)", "code": -1}
        if proc.returncode != 0:
            return {
                "stdout": proc.stdout,
                "stderr": proc.stderr or "admin elevation failed",
                "code": proc.returncode,
            }
        stdout = out_path.read_text(encoding="utf-8", errors="replace") if out_path.is_file() else ""
        stderr = err_path.read_text(encoding="utf-8", errors="replace") if err_path.is_file() else ""
        code = 0
        if code_path.is_file():
            try:
                code = int(code_path.read_text(encoding="ascii").strip() or "0")
            except ValueError:
                code = -1
        return {"stdout": stdout, "stderr": stderr, "code": code}


def _run_cli(exe: str, args: list[str], cwd: str | None, timeout: float) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            [exe, *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd or None,
        )
    except subprocess.TimeoutExpired:
        return {"stdout": "", "stderr": f"timeout ({timeout}s)", "code": -1}
    except OSError as exc:
        return {"stdout": "", "stderr": str(exc), "code": -1}
    return {"stdout": proc.stdout, "stderr": proc.stderr, "code": proc.returncode}


def _fs_roots() -> list[Path]:
    raw = (settings.fs_roots or "").strip()
    if not raw:
        return []
    return [Path(x.strip()).resolve() for x in raw.split(",") if x.strip()]


def _resolve_path(path: str) -> Path:
    p = Path(path).expanduser()
    if not p.is_absolute():
        raise HTTPException(status_code=400, detail="path must be absolute")
    resolved = p.resolve()
    roots = _fs_roots()
    if roots:
        ok = False
        for root in roots:
            try:
                resolved.relative_to(root)
                ok = True
                break
            except ValueError:
                continue
        if not ok:
            raise HTTPException(status_code=403, detail="path outside HOSTAGENT_FS_ROOTS")
    return resolved


_SCREEN_PS = """
Add-Type -AssemblyName System.Windows.Forms,System.Drawing
$bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
$bmp = New-Object System.Drawing.Bitmap $bounds.Width, $bounds.Height
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($bounds.Location, [System.Drawing.Point]::Empty, $bounds.Size)
$path = Join-Path $env:TEMP ('jarvis_scr_' + [guid]::NewGuid().ToString('N') + '.png')
$bmp.Save($path, [System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose(); $bmp.Dispose()
Write-Output $path
""".strip()


def _capture_screen_png() -> bytes:
    if sys.platform != "win32":
        raise HTTPException(status_code=501, detail="screenshots only on Windows")
    result = _run_powershell(_SCREEN_PS, False, 15.0)
    if int(result.get("code", -1)) != 0:
        detail = (result.get("stderr") or result.get("stdout") or "screenshot failed").strip()
        raise HTTPException(status_code=500, detail=detail[:300])
    lines = [ln.strip() for ln in (result.get("stdout") or "").splitlines() if ln.strip()]
    if not lines:
        raise HTTPException(status_code=500, detail="screenshot path empty")
    img_path = Path(lines[-1])
    if not img_path.is_file():
        raise HTTPException(status_code=500, detail=f"screenshot file missing: {img_path}")
    try:
        return img_path.read_bytes()
    finally:
        try:
            img_path.unlink(missing_ok=True)
        except OSError:
            pass


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/stack")
async def health_stack(
    _: Annotated[None, Depends(_check_token)],
) -> dict[str, bool]:
    docker_up = False
    try:
        proc = subprocess.run(
            ["docker", "ps", "-q"],
            capture_output=True,
            text=True,
            timeout=10.0,
        )
        docker_up = proc.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        docker_up = False
    return {"docker_up": docker_up}


@app.post("/powershell")
async def powershell(
    req: PowerShellRequest,
    _: Annotated[None, Depends(_check_token)],
) -> dict[str, Any]:
    script = (req.script or "").strip()
    if not script:
        raise HTTPException(status_code=400, detail="empty script")
    if len(script) > 8000:
        raise HTTPException(status_code=400, detail="script too long")
    return _run_powershell(script, req.as_admin, _timeout(req.timeout))


@app.post("/cli")
async def cli(
    req: CliRequest,
    _: Annotated[None, Depends(_check_token)],
) -> dict[str, Any]:
    exe = (req.exe or "").strip()
    if not exe:
        raise HTTPException(status_code=400, detail="empty exe")
    return _run_cli(exe, req.args, req.cwd, _timeout(req.timeout))


@app.get("/fs/list")
async def fs_list(
    path: Annotated[str, Query()],
    _: Annotated[None, Depends(_check_token)],
) -> dict[str, Any]:
    p = _resolve_path(path)
    if not p.is_dir():
        raise HTTPException(status_code=404, detail="not a directory")
    entries: list[dict[str, str]] = []
    try:
        for child in sorted(p.iterdir())[:500]:
            kind = "dir" if child.is_dir() else "file"
            entries.append({"name": child.name, "kind": kind})
    except OSError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"path": str(p), "entries": entries}


@app.get("/fs/read")
async def fs_read(
    path: Annotated[str, Query()],
    _: Annotated[None, Depends(_check_token)],
) -> dict[str, Any]:
    p = _resolve_path(path)
    if not p.is_file():
        raise HTTPException(status_code=404, detail="not a file")
    try:
        data = p.read_bytes()
    except OSError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    truncated = len(data) > settings.max_bytes
    if truncated:
        data = data[: settings.max_bytes]
    text = data.decode("utf-8", errors="replace")
    return {"path": str(p), "content": text, "truncated": truncated}


@app.post("/fs/write")
async def fs_write(
    req: FsWriteRequest,
    _: Annotated[None, Depends(_check_token)],
) -> dict[str, str]:
    p = _resolve_path(req.path)
    content = req.content or ""
    if len(content.encode("utf-8")) > settings.max_bytes:
        raise HTTPException(status_code=400, detail="content too large")
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    except OSError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"path": str(p), "status": "ok"}


def _apply_search_replace(
    content: str, old: str, new: str, *, replace_all: bool
) -> tuple[str, int]:
    """Search-replace у LF-просторі; вимагає унікального збігу, якщо не replace_all.

    Повертає (новий_вміст, кількість_замін). 4xx при відсутності/неоднозначності.
    """
    if not old:
        raise HTTPException(status_code=400, detail="old_string required for search_replace")
    count = content.count(old)
    if count == 0:
        raise HTTPException(status_code=422, detail="old_string not found")
    if count > 1 and not replace_all:
        raise HTTPException(
            status_code=422,
            detail=f"old_string not unique ({count} matches); add context or set replace_all",
        )
    if replace_all:
        return content.replace(old, new), count
    return content.replace(old, new, 1), 1


def _parse_hunks(diff: str) -> list[tuple[str, str]]:
    """Розбиває unified-diff на пари (before_block, after_block) у LF-просторі."""
    lines = diff.replace("\r\n", "\n").split("\n")
    hunks: list[tuple[list[str], list[str]]] = []
    before: list[str] = []
    after: list[str] = []
    in_hunk = False
    for ln in lines:
        if ln.startswith("@@"):
            if in_hunk:
                hunks.append((before, after))
            before, after, in_hunk = [], [], True
            continue
        if not in_hunk:
            continue  # пропускаємо ---/+++ заголовки
        if ln.startswith("+"):
            after.append(ln[1:])
        elif ln.startswith("-"):
            before.append(ln[1:])
        elif ln.startswith(" "):
            before.append(ln[1:])
            after.append(ln[1:])
        elif ln.startswith("\\"):
            continue  # "\ No newline at end of file"
        else:  # порожній рядок діфу = контекст-порожній
            before.append(ln)
            after.append(ln)
    if in_hunk:
        hunks.append((before, after))
    return [("\n".join(b), "\n".join(a)) for b, a in hunks]


def _apply_unified_diff(content: str, diff: str) -> str:
    """Аплає кожен hunk як search-replace його контекстного блоку (стійко до зсуву рядків)."""
    hunks = _parse_hunks(diff)
    if not hunks:
        raise HTTPException(status_code=400, detail="no hunks parsed from diff")
    out = content
    for i, (before, after) in enumerate(hunks):
        if before == after:
            continue
        occ = out.count(before)
        if occ == 0:
            raise HTTPException(
                status_code=422, detail=f"hunk #{i + 1} context not found in file"
            )
        if occ > 1:
            raise HTTPException(
                status_code=422, detail=f"hunk #{i + 1} context not unique ({occ})"
            )
        out = out.replace(before, after, 1)
    return out


def _backup_original(p: Path, original: str) -> str:
    """Зберігає оригінал у <parent>/.jarvis_backup/<name>.<ts>.bak (git-safety CA-1.3)."""
    stamp = f"{time.strftime('%Y%m%d_%H%M%S')}_{time.time_ns() % 100000:05d}"
    backup_dir = p.parent / ".jarvis_backup"
    backup_dir.mkdir(parents=True, exist_ok=True)
    dest = backup_dir / f"{p.name}.{stamp}.bak"
    dest.write_text(original, encoding="utf-8")
    return str(dest)


@app.post("/fs/edit")
async def fs_edit(
    req: FsEditRequest,
    _: Annotated[None, Depends(_check_token)],
) -> dict[str, Any]:
    """Атомарна правка коду: search-replace / unified-diff + .jarvis_backup перед записом."""
    p = _resolve_path(req.path)
    if not p.is_file():
        raise HTTPException(status_code=404, detail="not a file")
    try:
        original = p.read_text(encoding="utf-8")
    except OSError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    # CRLF → працюємо у LF-просторі, відновлюємо стиль на запис.
    crlf = "\r\n" in original
    base = original.replace("\r\n", "\n")

    mode = (req.mode or "search_replace").strip().lower()
    if mode == "diff":
        if not req.diff.strip():
            raise HTTPException(status_code=400, detail="diff required for mode=diff")
        new_lf = _apply_unified_diff(base, req.diff)
        occurrences = 1
    elif mode == "search_replace":
        old = req.old_string.replace("\r\n", "\n")
        new = req.new_string.replace("\r\n", "\n")
        new_lf, occurrences = _apply_search_replace(base, old, new, replace_all=req.replace_all)
    else:
        raise HTTPException(status_code=400, detail=f"unknown mode {mode!r}")

    if new_lf == base:
        raise HTTPException(status_code=422, detail="edit produced no change")
    if len(new_lf.encode("utf-8")) > settings.max_bytes:
        raise HTTPException(status_code=400, detail="result too large")

    preview = "".join(
        difflib.unified_diff(
            base.splitlines(keepends=True),
            new_lf.splitlines(keepends=True),
            fromfile=p.name,
            tofile=p.name,
            n=2,
        )
    )
    new_content = new_lf.replace("\n", "\r\n") if crlf else new_lf
    try:
        backup = _backup_original(p, original)
        p.write_text(new_content, encoding="utf-8")
    except OSError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {
        "path": str(p),
        "status": "ok",
        "mode": mode,
        "occurrences": occurrences,
        "backup": backup,
        "diff": preview[:4000],
    }


def _screen_click_ps(x: int, y: int) -> str:
    return f"""
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class WinMouse {{
  [DllImport("user32.dll")] public static extern bool SetCursorPos(int X, int Y);
  [DllImport("user32.dll")] public static extern void mouse_event(uint f, uint dx, uint dy, uint d, uint e);
}}
"@
[WinMouse]::SetCursorPos({x}, {y}) | Out-Null
Start-Sleep -Milliseconds 80
[WinMouse]::mouse_event(0x0002, 0, 0, 0, 0)
[WinMouse]::mouse_event(0x0004, 0, 0, 0, 0)
""".strip()


@app.post("/screen/click")
async def screen_click(
    req: ScreenClickRequest,
    _: Annotated[None, Depends(_check_token)],
) -> dict[str, str]:
    """T4 — клік по координатах екрана (останній резерв)."""
    if sys.platform != "win32":
        raise HTTPException(status_code=501, detail="windows only")
    x, y = int(req.x), int(req.y)
    if x < 0 or y < 0 or x > 10000 or y > 10000:
        raise HTTPException(status_code=400, detail="bad coordinates")
    ps = _screen_click_ps(x, y)
    result = _run_powershell(ps, False, 10.0)
    if int(result.get("code", -1)) != 0:
        raise HTTPException(
            status_code=500,
            detail=(result.get("stderr") or "click failed")[:200],
        )
    return {"status": "ok", "x": str(x), "y": str(y)}


@app.post("/screen/capture")
async def screen_capture(
    _: Annotated[None, Depends(_check_token)],
) -> dict[str, str]:
    """Знімок основного екрана (read-only, Windows)."""
    data = _capture_screen_png()
    return {"format": "png", "data_b64": base64.b64encode(data).decode("ascii")}


@app.post("/screen/type")
async def screen_type(
    req: ScreenTypeRequest,
    _: Annotated[None, Depends(_check_token)],
) -> dict[str, str]:
    """T4 — введення тексту з клавіатури."""
    if sys.platform != "win32":
        raise HTTPException(status_code=501, detail="windows only")
    from .screen_input import build_type_ps

    text = req.text or ""
    if len(text.encode("utf-8")) > settings.max_bytes:
        raise HTTPException(status_code=400, detail="text too large")
    ps = build_type_ps(text, req.interval_ms)
    result = _run_powershell(ps, False, 15.0)
    if int(result.get("code", -1)) != 0:
        raise HTTPException(
            status_code=500,
            detail=(result.get("stderr") or "type failed")[:200],
        )
    return {"status": "ok", "chars": str(len(text))}


@app.post("/screen/hotkey")
async def screen_hotkey(
    req: ScreenHotkeyRequest,
    _: Annotated[None, Depends(_check_token)],
) -> dict[str, str]:
    """T4 — комбінація клавіш (ctrl+s, alt+tab тощо)."""
    if sys.platform != "win32":
        raise HTTPException(status_code=501, detail="windows only")
    if not req.keys:
        raise HTTPException(status_code=400, detail="keys required")
    from .screen_input import build_hotkey_ps

    ps = build_hotkey_ps(req.keys)
    result = _run_powershell(ps, False, 10.0)
    if int(result.get("code", -1)) != 0:
        raise HTTPException(
            status_code=500,
            detail=(result.get("stderr") or "hotkey failed")[:200],
        )
    return {"status": "ok", "keys": "+".join(req.keys)}


@app.post("/screen/scroll")
async def screen_scroll(
    req: ScreenScrollRequest,
    _: Annotated[None, Depends(_check_token)],
) -> dict[str, str]:
    """T4 — прокрутка колеса миші (+ вгору, - вниз)."""
    if sys.platform != "win32":
        raise HTTPException(status_code=501, detail="windows only")
    from .screen_input import build_scroll_ps

    ps = build_scroll_ps(req.clicks, req.x, req.y)
    result = _run_powershell(ps, False, 10.0)
    if int(result.get("code", -1)) != 0:
        raise HTTPException(
            status_code=500,
            detail=(result.get("stderr") or "scroll failed")[:200],
        )
    return {"status": "ok", "clicks": str(req.clicks)}


@app.get("/fs/download")
async def fs_download(
    path: Annotated[str, Query()],
    _: Annotated[None, Depends(_check_token)],
) -> Response:
    p = _resolve_path(path)
    if not p.is_file():
        raise HTTPException(status_code=404, detail="not a file")
    try:
        data = p.read_bytes()
    except OSError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if len(data) > settings.max_download_bytes:
        raise HTTPException(status_code=413, detail="file too large")
    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{p.name}"'},
    )


@app.post("/fs/write_bytes")
async def fs_write_bytes(
    req: FsWriteBytesRequest,
    _: Annotated[None, Depends(_check_token)],
) -> dict[str, str]:
    p = _resolve_path(req.path)
    try:
        raw = base64.b64decode(req.data_b64 or "", validate=True)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail="invalid base64") from exc
    if len(raw) > settings.max_download_bytes:
        raise HTTPException(status_code=413, detail="content too large")
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(raw)
    except OSError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"path": str(p), "status": "ok", "bytes": str(len(raw))}


_CLIPBOARD_READ_PS = (
    "Add-Type -AssemblyName System.Windows.Forms; "
    "[System.Windows.Forms.Clipboard]::GetText()"
)
_CLIPBOARD_WRITE_PS = (
    "Add-Type -AssemblyName System.Windows.Forms; "
    "param($t); [System.Windows.Forms.Clipboard]::SetText($t)"
)


@app.get("/clipboard")
async def clipboard_read(
    _: Annotated[None, Depends(_check_token)],
) -> dict[str, str]:
    if sys.platform != "win32":
        raise HTTPException(status_code=501, detail="clipboard only on Windows")
    result = _run_powershell(_CLIPBOARD_READ_PS, False, 10.0)
    text = (result.get("stdout") or "").strip()
    return {"text": text}


@app.post("/clipboard")
async def clipboard_write(
    req: ClipboardWriteRequest,
    _: Annotated[None, Depends(_check_token)],
) -> dict[str, str]:
    if sys.platform != "win32":
        raise HTTPException(status_code=501, detail="clipboard only on Windows")
    text = req.text or ""
    if len(text.encode("utf-8")) > settings.max_bytes:
        raise HTTPException(status_code=400, detail="text too large")
    escaped = json.dumps(text)
    script = f"$t = {escaped}; Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.Clipboard]::SetText($t)"
    result = _run_powershell(script, False, 10.0)
    if int(result.get("code", -1)) != 0:
        detail = (result.get("stderr") or "clipboard write failed").strip()
        raise HTTPException(status_code=500, detail=detail[:200])
    return {"status": "ok"}


@app.get("/window/list")
async def window_list(
    _: Annotated[None, Depends(_check_token)],
) -> dict[str, Any]:
    if sys.platform != "win32":
        raise HTTPException(status_code=501, detail="windows only")
    ps = (
        "Get-Process | Where-Object { $_.MainWindowTitle } "
        "| Select-Object Id, ProcessName, MainWindowTitle "
        "| ConvertTo-Json -Compress"
    )
    result = _run_powershell(ps, False, 15.0)
    raw = (result.get("stdout") or "").strip()
    windows: list[dict[str, Any]] = []
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                parsed = [parsed]
            if isinstance(parsed, list):
                windows = parsed
        except json.JSONDecodeError:
            pass
    return {"windows": windows[:100]}


@app.post("/window/focus")
async def window_focus(
    title: Annotated[str, Query()],
    _: Annotated[None, Depends(_check_token)],
) -> dict[str, str]:
    if sys.platform != "win32":
        raise HTTPException(status_code=501, detail="windows only")
    if not title.strip():
        raise HTTPException(status_code=400, detail="empty title")
    escaped = json.dumps(title.strip())
    ps = (
        f"$t = {escaped}; "
        "(Add-Type @'\\nusing System;\\nusing System.Runtime.InteropServices;\\n"
        "public class Win32 { [DllImport(\\\"user32.dll\\\")] public static extern bool SetForegroundWindow(IntPtr hWnd); }\\n'@ -PassThru); "
        "$p = Get-Process | Where-Object {{ $_.MainWindowTitle -like \\\"*${{t}}*\\\" }} | Select-Object -First 1; "
        "if (-not $p) {{ exit 2 }}; [Win32]::SetForegroundWindow($p.MainWindowHandle); $p.MainWindowTitle"
    )
    result = _run_powershell(ps, False, 15.0)
    if int(result.get("code", -1)) == 2:
        raise HTTPException(status_code=404, detail="window not found")
    if int(result.get("code", -1)) != 0:
        raise HTTPException(status_code=500, detail=(result.get("stderr") or "focus failed")[:200])
    return {"title": (result.get("stdout") or "").strip(), "status": "ok"}


@app.post("/uia/invoke")
async def uia_invoke(
    req: UiaInvokeRequest,
    _: Annotated[None, Depends(_check_token)],
) -> dict[str, str]:
    """UI Automation lite — фокус вікна + Enter (SendKeys fallback)."""
    if sys.platform != "win32":
        raise HTTPException(status_code=501, detail="windows only")
    control = (req.control_name or "").strip()
    if not control:
        raise HTTPException(status_code=400, detail="control_name required")
    if req.window.strip():
        title = req.window.strip()
        escaped = json.dumps(title)
        focus_ps = (
            f"$t = {escaped}; "
            "$p = Get-Process | Where-Object { $_.MainWindowTitle -like \"*$($t)*\" } | Select-Object -First 1; "
            "if (-not $p) { exit 2 }; "
            "(Add-Type @'\nusing System;\nusing System.Runtime.InteropServices;\n"
            "public class Win32 { [DllImport(\"user32.dll\")] public static extern bool SetForegroundWindow(IntPtr hWnd); }\n'@ -PassThru); "
            "[Win32]::SetForegroundWindow($p.MainWindowHandle)"
        )
        focus = _run_powershell(focus_ps, False, 15.0)
        if int(focus.get("code", -1)) == 2:
            raise HTTPException(status_code=404, detail="window not found")
    action = (req.action or "click").lower()
    if action != "click":
        raise HTTPException(status_code=400, detail="only click supported")
    ps = (
        "Add-Type -AssemblyName System.Windows.Forms; "
        "Start-Sleep -Milliseconds 200; "
        "[System.Windows.Forms.SendKeys]::SendWait('{ENTER}')"
    )
    result = _run_powershell(ps, False, 15.0)
    if int(result.get("code", -1)) != 0:
        raise HTTPException(status_code=500, detail=(result.get("stderr") or "uia failed")[:200])
    return {"status": "ok", "control": control}


@app.post("/power")
async def power_action(
    req: PowerRequest,
    _: Annotated[None, Depends(_check_token)],
) -> dict[str, str]:
    if not settings.allow_power:
        raise HTTPException(status_code=403, detail="power actions disabled")
    if sys.platform != "win32":
        raise HTTPException(status_code=501, detail="windows only")
    action = (req.action or "").lower().strip()
    delay = max(0, min(int(req.delay_seconds), 300))
    scripts = {
        "lock": "rundll32.exe user32.dll,LockWorkStation",
        "sleep": "Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.Application]::SetSuspendState('Suspend', $false, $false)",
        "restart": f"shutdown /r /t {delay}",
        "shutdown": f"shutdown /s /t {delay}",
    }
    if action not in scripts:
        raise HTTPException(status_code=400, detail="bad action")
    result = _run_powershell(scripts[action], False, 15.0)
    if int(result.get("code", -1)) != 0 and action in ("lock", "sleep"):
        raise HTTPException(status_code=500, detail=(result.get("stderr") or "power failed")[:200])
    return {"status": "ok", "action": action, "delay": str(delay)}


@app.post("/wol")
async def wake_on_lan(
    req: WolRequest,
    _: Annotated[None, Depends(_check_token)],
) -> dict[str, str]:
    mac = (req.mac or "").replace("-", ":").replace(".", ":").upper()
    if len(mac.split(":")) != 6:
        raise HTTPException(status_code=400, detail="invalid mac")
    ps = (
        f"$mac = '{mac}'; $macBytes = ($mac -split ':') | ForEach-Object {{ [byte]('0x' + $_) }}; "
        f"$packet = [byte[]](,0xFF * 6) + ($macBytes * 16); "
        f"$udp = New-Object System.Net.Sockets.UdpClient; "
        f"$udp.Connect('{req.broadcast}', 9); $udp.Send($packet, $packet.Length) | Out-Null; $udp.Close()"
    )
    result = _run_powershell(ps, False, 10.0)
    if int(result.get("code", -1)) != 0:
        raise HTTPException(status_code=500, detail=(result.get("stderr") or "wol failed")[:200])
    return {"status": "ok", "mac": mac}


logger.info(
    "Host agent ready. bind=%s:%s allow_admin=%s",
    settings.bind_host,
    settings.port,
    settings.allow_admin,
)
