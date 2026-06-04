"""JARVIS host-agent — керування Windows-хостом (PowerShell, CLI, FS).

Крутиться на хості поза Docker; контейнер tools звертається через host.docker.internal.
"""
from __future__ import annotations

import base64
import hmac
import json
import logging
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query
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


@app.post("/screen/capture")
async def screen_capture(
    _: Annotated[None, Depends(_check_token)],
) -> dict[str, str]:
    """Знімок основного екрана (read-only, Windows)."""
    data = _capture_screen_png()
    return {"format": "png", "data_b64": base64.b64encode(data).decode("ascii")}


logger.info(
    "Host agent ready. bind=%s:%s allow_admin=%s",
    settings.bind_host,
    settings.port,
    settings.allow_admin,
)
