"""R5.1 «Тонкий шлюз» — retention kaizen-паспортів (keep-N у git + архів поза git).

Паспорти (`data/artifacts/self-improve/passports/NNNN-*.json`) — аудиторський слід
kaizen-циклів; без ротації git пухне (+~200 файлів/тиждень при щоденних вікнах).
Політика: у git лишаються останні N=50; старші пакуються в
`data/artifacts/self-improve/archive/passports-<до-номера>.tar.gz` (каталог у
.gitignore — історія живе на диску і в git-історії, не в HEAD). Агрегат за весь
час — `summary.json` (його ротація не чіпає).

Порядок безпеки (спека «Ризики й відкат»): архів створюється ДО видалення;
видалення — лише якщо архів записаний і читається.

Запуск: `python scripts/passport_retention.py [--keep 50] [--dry-run]`
(kaizen-профіль кличе його наприкінці вікна — див. profiles/jarvis/profile.md).
"""
from __future__ import annotations

import argparse
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PASSPORTS = ROOT / "data" / "artifacts" / "self-improve" / "passports"
ARCHIVE_DIR = ROOT / "data" / "artifacts" / "self-improve" / "archive"
DEFAULT_KEEP = 50


def rotate(keep: int, dry_run: bool) -> int:
    files = sorted(p for p in PASSPORTS.glob("*.json") if p.is_file())
    if len(files) <= keep:
        print(f"OK: {len(files)} паспортів ≤ keep={keep} — ротація не потрібна")
        return 0
    old = files[:-keep]
    last_old = old[-1].name.split("-", 1)[0]
    archive = ARCHIVE_DIR / f"passports-{last_old}.tar.gz"
    print(f"ротація: {len(files)} -> keep {keep}; в архів {len(old)} (до {last_old}) -> {archive.name}")
    if dry_run:
        return 0

    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "w:gz") as tar:
        for p in old:
            tar.add(p, arcname=p.name)
    # Верифікація архіву ДО видалення (аудиторський слід не втрачається).
    with tarfile.open(archive, "r:gz") as tar:
        names = set(tar.getnames())
    missing = [p.name for p in old if p.name not in names]
    if missing:
        print(f"АРХІВ НЕПОВНИЙ, видалення скасовано: {missing[:3]}…", file=sys.stderr)
        return 1
    for p in old:
        p.unlink()
    print(f"OK: заархівовано і прибрано {len(old)}; у passports/ лишилось {keep}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", type=int, default=DEFAULT_KEEP)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if not PASSPORTS.is_dir():
        print(f"нема каталогу {PASSPORTS} — нічого ротувати")
        return 0
    return rotate(max(1, args.keep), args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
