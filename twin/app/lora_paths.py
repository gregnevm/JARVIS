"""Розвʼязання шляхів LoRA артефактів у data_dir Twin."""
from __future__ import annotations

import os
from pathlib import Path


def resolve_lora_path(path: str, data_dir: Path) -> Path:
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
        data_dir / raw.lstrip("/"),
    ):
        if cand.exists():
            return cand.resolve()
    raise FileNotFoundError(f"lora artifact not found: {raw} (data_dir={data_dir})")
