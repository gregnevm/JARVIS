"""MVP APK артефакт (Стовп C, CL-3).

Єдиний резолвер шляху/метаданих зібраного Android-клієнта. Використовується і
ботом (`/apk`), і авто-нотифікацією адміна після білду — щоб не дублювати логіку
пошуку файлу (S3: бізнес-логіка не в каналі).

Build-pipeline (`mobile/build-apk.ps1`) кладе apk у `data/artifacts/` — а оскільки
в Compose `./data:/data`, gateway бачить його за `{DATA_DIR}/artifacts/...`.
Опційний sidecar `<apk>.meta.json` несе `version`/`built_at`/`git` (паспорт артефакту, P9).
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path

from .config import settings

logger = logging.getLogger("jarvis.gateway.apk")

DEFAULT_REL = "artifacts/jarvis-mvp.apk"


def apk_path() -> Path:
    """Абсолютний шлях до APK.

    `APK_ARTIFACT_PATH` (явний) → інакше `{DATA_DIR}/artifacts/jarvis-mvp.apk`.
    """
    raw = (settings.apk_artifact_path or "").strip()
    if raw:
        return Path(raw)
    return Path(settings.data_dir) / DEFAULT_REL


@dataclass(frozen=True)
class ApkInfo:
    """Паспорт зібраного APK (для caption і нотифікацій)."""

    path: Path
    size: int
    sha256: str
    version: str
    built_at: str
    filename: str

    @property
    def size_mb(self) -> float:
        return round(self.size / (1024 * 1024), 2)


def _sidecar_meta(p: Path) -> dict[str, str]:
    """Читає `<apk>.meta.json` поряд із apk (best-effort, ніколи не кидає)."""
    meta_path = p.with_suffix(p.suffix + ".meta.json")
    try:
        if meta_path.is_file():
            data = json.loads(meta_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return {str(k): str(v) for k, v in data.items()}
    except (OSError, ValueError) as exc:  # pragma: no cover - захист від битого sidecar
        logger.warning("apk meta sidecar unreadable: %s", exc)
    return {}


def _sha256_of(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def apk_info() -> ApkInfo | None:
    """Метадані APK або None, якщо файл ще не зібрано."""
    p = apk_path()
    if not p.is_file():
        return None
    try:
        size = p.stat().st_size
        digest = _sha256_of(p)
    except OSError as exc:
        logger.error("apk stat/hash failed for %s: %s", p, exc)
        return None
    meta = _sidecar_meta(p)
    version = meta.get("version") or settings.apk_version or "0.0.0"
    built_at = meta.get("built_at", "")
    filename = f"jarvis-mvp-{version}.apk"
    return ApkInfo(
        path=p,
        size=size,
        sha256=digest,
        version=version,
        built_at=built_at,
        filename=filename,
    )


def read_apk_bytes() -> bytes | None:
    """Сирі байти APK для `send_document`. None, якщо файлу немає/не читається."""
    p = apk_path()
    try:
        return p.read_bytes()
    except OSError as exc:
        logger.error("apk read failed for %s: %s", p, exc)
        return None
