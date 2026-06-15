"""LoRA → Ollama live deploy (Phase 3.2): symlink active + ollama create."""
from __future__ import annotations

import logging
import os
import platform
import subprocess
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger("jarvis.tools.lora_deploy")

_DEFAULT_MODELFILE = """FROM {base_model}
ADAPTER {adapter_path}
PARAMETER temperature 0.7
PARAMETER num_ctx 8192
"""


def resolve_lora_path(path: str, data_dir: Path) -> Path:
    """Розвʼязує шлях з registry (abs, relative, або імʼя версії)."""
    raw = (path or "").strip()
    if not raw:
        raise FileNotFoundError("empty lora path")
    p = Path(raw)
    if p.is_absolute() and p.exists():
        return p.resolve()
    base = data_dir / "twin" / "lora"
    for cand in (
        base / raw.lstrip("/"),
        base / raw.strip("/").replace("/", os.sep),
        base / p.name,
    ):
        if cand.exists():
            return cand.resolve()
    raise FileNotFoundError(f"lora artifact not found: {raw} (data_dir={data_dir})")


def _link_dir_junction(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() or target.is_symlink():
        if target.is_dir() and not target.is_symlink():
            import shutil

            shutil.rmtree(target)
        else:
            target.unlink()
    if platform.system() == "Windows":
        subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(target), str(source)],
            check=True,
            capture_output=True,
            text=True,
        )
    else:
        os.symlink(source, target, target_is_directory=True)


def link_active(source: Path, active_dir: Path) -> Path:
    """Blue-Green symlink/junction active → source. Повертає шлях ADAPTER для Modelfile."""
    source = source.resolve()
    if not source.exists():
        raise FileNotFoundError(str(source))
    if source.is_dir():
        _link_dir_junction(source, active_dir)
        ggufs = sorted(active_dir.glob("*.gguf"))
        if ggufs:
            return ggufs[0].resolve()
        return active_dir.resolve()
    active_dir.parent.mkdir(parents=True, exist_ok=True)
    adapter = active_dir if active_dir.suffix == ".gguf" else active_dir / source.name
    if adapter.exists() or adapter.is_symlink():
        adapter.unlink()
    if platform.system() == "Windows":
        subprocess.run(
            ["cmd", "/c", "mklink", str(adapter), str(source)],
            check=True,
            capture_output=True,
            text=True,
        )
    else:
        os.symlink(source, adapter)
    return adapter.resolve()


def build_modelfile(base_model: str, adapter_path: Path, template: str | None = None) -> str:
    tpl = (template or _DEFAULT_MODELFILE).strip() + "\n"
    adapter = str(adapter_path).replace("\\", "/")
    return tpl.format(base_model=base_model.strip(), adapter_path=adapter)


async def ollama_create(
    host: str,
    model_name: str,
    modelfile: str,
    *,
    client: httpx.AsyncClient | None = None,
    timeout: float = 180.0,
) -> dict[str, Any]:
    url = f"{host.rstrip('/')}/api/create"
    owns = client is None
    cli = client or httpx.AsyncClient(timeout=timeout)
    try:
        r = await cli.post(url, json={"name": model_name, "modelfile": modelfile, "stream": False})
        r.raise_for_status()
        data = r.json()
        return {"ok": True, "model": model_name, "response": data}
    except httpx.HTTPError as exc:
        detail = str(exc)
        if isinstance(exc, httpx.HTTPStatusError) and exc.response is not None:
            detail = exc.response.text[:400]
        return {"ok": False, "model": model_name, "error": detail}
    finally:
        if owns:
            await cli.aclose()


async def deploy_lora(
    *,
    version: str,
    path: str,
    data_dir: Path,
    ollama_host: str,
    base_model: str,
    model_prefix: str,
    active_dir: Path,
    modelfile_template: str | None = None,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Symlink active artifact + `ollama create` для версії."""
    try:
        source = resolve_lora_path(path, data_dir)
    except FileNotFoundError as exc:
        return {"ok": False, "version": version, "error": str(exc)}

    try:
        adapter = link_active(source, active_dir)
    except (OSError, subprocess.CalledProcessError) as exc:
        return {"ok": False, "version": version, "error": f"link active failed: {exc}"}

    model_name = f"{model_prefix.strip()}:{version}"
    modelfile = build_modelfile(base_model, adapter, modelfile_template)
    ollama = await ollama_create(ollama_host, model_name, modelfile, client=client)
    out: dict[str, Any] = {
        "ok": bool(ollama.get("ok")),
        "version": version,
        "source": str(source),
        "active": str(active_dir),
        "adapter": str(adapter),
        "model": model_name,
        "ollama": ollama,
    }
    if not ollama.get("ok"):
        out["error"] = ollama.get("error", "ollama create failed")
    return out


async def fetch_active_from_twin(twin_url: str, client: httpx.AsyncClient | None = None) -> dict[str, Any]:
    owns = client is None
    cli = client or httpx.AsyncClient(timeout=15.0)
    try:
        r = await cli.get(f"{twin_url.rstrip('/')}/latest/lora")
        r.raise_for_status()
        data = r.json()
        if not data.get("version"):
            return {"ok": False, "error": "no active lora in twin registry"}
        return {"ok": True, **data}
    except httpx.HTTPError as exc:
        return {"ok": False, "error": str(exc)}
    finally:
        if owns:
            await cli.aclose()


async def sync_active_from_twin(
    twin_url: str,
    *,
    data_dir: Path,
    ollama_host: str,
    base_model: str,
    model_prefix: str,
    active_dir: Path,
    modelfile_template: str | None = None,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """GET /latest/lora з Twin → deploy у Ollama."""
    owns = client is None
    cli = client or httpx.AsyncClient(timeout=180.0)
    try:
        active = await fetch_active_from_twin(twin_url, client=cli)
        if not active.get("ok"):
            return active
        return await deploy_lora(
            version=str(active["version"]),
            path=str(active.get("path") or ""),
            data_dir=data_dir,
            ollama_host=ollama_host,
            base_model=base_model,
            model_prefix=model_prefix,
            active_dir=active_dir,
            modelfile_template=modelfile_template,
            client=cli,
        )
    finally:
        if owns:
            await cli.aclose()
