#!/usr/bin/env python3
"""Надсилає зібраний MVP APK адмінам у Telegram (Стовп C, CL-3).

Запускається на ХОСТІ після `mobile/build-apk.ps1`. Перевикористовує резолвер
артефакту й розсилку з gateway (`app.apk_artifact` / `app.bot.apk`), щоб не
дублювати логіку. Шлях до apk форсуємо на host-локацію (gateway у контейнері
бачить той самий файл як /data/artifacts/...; на хості це <repo>/data/artifacts/...).

Usage:
    python scripts/send_apk_to_admin.py            # усім ADMIN_USER_IDS
    python scripts/send_apk_to_admin.py 12345 678  # конкретним chat_id
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
GATEWAY = REPO / "gateway"
# gateway для пакета `app`, корінь репо для `jarvis_core` (на хості, поза Docker).
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(GATEWAY))
# settings читає .env з cwd — стаємо в корінь репо.
os.chdir(REPO)

from app import apk_artifact  # noqa: E402
from app.bot.apk import notify_admins_apk_ready  # noqa: E402
from app.config import settings  # noqa: E402
from app.telegram import TelegramClient  # noqa: E402

HOST_APK = REPO / "data" / "artifacts" / "jarvis-mvp.apk"


async def main(argv: list[str]) -> int:
    # Форсуємо host-шлях незалежно від DATA_DIR (=/data у Docker).
    apk_artifact.settings.apk_artifact_path = str(HOST_APK)

    info = apk_artifact.apk_info()
    if info is None:
        print(f"[!] APK not found at {HOST_APK} - run mobile/build-apk.ps1 first.", file=sys.stderr)
        return 2

    token = settings.telegram_bot_token.strip()
    if not token:
        print("[!] TELEGRAM_BOT_TOKEN is empty (.env).", file=sys.stderr)
        return 3

    targets = [int(a) for a in argv if a.lstrip("-").isdigit()]
    if not targets:
        targets = sorted(settings.admin_ids)
    if not targets:
        print("[!] No admin ids (ADMIN_USER_IDS / ALLOWED_USER_IDS empty).", file=sys.stderr)
        return 4

    print(f"[*] APK v{info.version} ({info.size_mb} MB, sha256 {info.sha256[:12]})")
    print(f"[*] sending to: {targets}")

    tg = TelegramClient(token, settings.telegram_api_base)
    try:
        delivered = await notify_admins_apk_ready(tg, targets)
    finally:
        await tg.aclose()

    print(f"[+] delivered to {delivered}/{len(targets)} recipient(s).")
    return 0 if delivered else 5


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(sys.argv[1:])))
