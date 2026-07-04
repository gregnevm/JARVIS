"""Розвʼязання шляхів LoRA артефактів у data_dir Twin.

Безпека: `path` — з реєстру (клієнт-контрольований через POST /registry/lora),
а `download_active_lora` віддає файл через `FileResponse`. Тому резолвер
**fail-closed**: підсумковий шлях мусить лишатися всередині `data_dir`, інакше
абсолютний шлях (`/etc/passwd`) чи `../`-траверсал давали arbitrary-file-read.
"""
from __future__ import annotations

import os
from pathlib import Path


def _within(candidate: Path, root: Path) -> bool:
    """True, якщо resolved `candidate` лежить усередині `root` (containment).

    Ідіома `relative_to` в try/except — той самий патерн, що hostagent
    `_resolve_path`; працює на всіх версіях і mypy-strict-чистий."""
    try:
        candidate.relative_to(root)
        return True
    except ValueError:
        return False


def resolve_lora_path(path: str, data_dir: Path) -> Path:
    raw = (path or "").strip()
    if not raw:
        raise FileNotFoundError("empty lora path")
    root = data_dir.resolve()
    p = Path(raw)
    base = data_dir / "twin" / "lora"
    candidates = [
        base / raw.lstrip("/"),
        base / raw.strip("/").replace("/", os.sep),
        base / p.name,
        data_dir / raw.lstrip("/"),
    ]
    if p.is_absolute():
        # Абсолютний шлях легітимний, ЛИШЕ якщо він усередині data_dir
        # (containment-перевірка нижче відсіює /etc/passwd тощо).
        candidates.insert(0, p)
    for cand in candidates:
        resolved = cand.resolve()
        if not _within(resolved, root):
            continue  # шлях поза data_dir — ніколи не віддаємо (fail-closed)
        if resolved.exists():
            return resolved
    raise FileNotFoundError(f"lora artifact not found: {raw} (data_dir={data_dir})")
