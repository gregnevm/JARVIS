"""Авто-доставка свіжого APK у Telegram через бот — без GitHub-секретів.

Збірка APK переїхала в CI (хмара), тож локальний `data/artifacts/jarvis-mvp.apk`
на хості більше не оновлюється сам — і `/apk` слав застарілий файл. Цей модуль
повертає «само працює»: gateway періодично дивиться публічний `apk-latest` реліз;
якщо там новіша версія за локальну — качає її в `data/artifacts` і DM-ить адмінам
через бот (`notify_admins_apk_ready`, з токеном із `.env`, який у gateway уже є).

Опт-ін: `APK_AUTO_DELIVER=true`. Дедуп — щоб не слати ту саму версію двічі: трекаємо
останню доставлену версію в Redis (без Redis — орієнтуємось на локальний файл).
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import httpx
import redis.asyncio as aioredis

from .apk_artifact import apk_info, apk_path
from .bot.apk import notify_admins_apk_ready
from .config import settings
from .telegram import TelegramClient

logger = logging.getLogger("jarvis.gateway.apk_autodeliver")

_DELIVERED_KEY = "jarvis:apk:autodeliver:version"


async def _fetch_remote_version(client: httpx.AsyncClient) -> str | None:
    """Версія APK у публічному релізі (з meta.json паспорта). None — недоступно."""
    try:
        r = await client.get(settings.apk_release_meta_url, timeout=15.0, follow_redirects=True)
        r.raise_for_status()
        version = str(r.json().get("version") or "").strip()
        return version or None
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("apk meta fetch failed: %s", exc)
        return None


async def _download(client: httpx.AsyncClient, url: str, dest: Path) -> bool:
    try:
        r = await client.get(url, timeout=120.0, follow_redirects=True)
        r.raise_for_status()
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(r.content)
        return True
    except (httpx.HTTPError, OSError) as exc:
        logger.error("apk download failed (%s): %s", url, exc)
        return False


async def _last_delivered(redis: aioredis.Redis | None, local_version: str | None) -> str | None:
    """Остання доставлена версія: з Redis, інакше — локальний файл як маркер."""
    if redis is None:
        return local_version
    try:
        val = await redis.get(_DELIVERED_KEY)
        return val.decode() if isinstance(val, (bytes, bytearray)) else val
    except Exception:  # noqa: BLE001 — Redis недоступний → fallback на локальний файл
        return local_version


async def check_once(tg: TelegramClient, redis: aioredis.Redis | None) -> bool:
    """Одна перевірка релізу. True — нову версію доставлено адмінам."""
    admins = sorted(settings.admin_ids)
    if not admins:
        logger.debug("apk autodeliver: no admin ids — skip")
        return False
    if not settings.telegram_bot_token.strip():
        return False

    async with httpx.AsyncClient() as client:
        remote_v = await _fetch_remote_version(client)
        if not remote_v:
            return False

        local = apk_info()
        local_v = local.version if local else None
        delivered_v = await _last_delivered(redis, local_v)
        if remote_v == delivered_v:
            return False  # цю версію вже слали — без спаму

        # Підтягуємо свіжий файл у локальний data/artifacts (щоб і /apk віддавав новий).
        if local_v != remote_v:
            dest = apk_path()
            if not await _download(client, settings.apk_release_apk_url, dest):
                return False
            await _download(
                client,
                settings.apk_release_meta_url,
                dest.with_suffix(dest.suffix + ".meta.json"),
            )

    delivered_n = await notify_admins_apk_ready(tg, admins)
    if delivered_n and redis is not None:
        try:
            await redis.set(_DELIVERED_KEY, remote_v)
        except Exception:  # noqa: BLE001
            pass
    logger.info("apk autodeliver: v%s → %s/%s admin(s)", remote_v, delivered_n, len(admins))
    return bool(delivered_n)


async def apk_autodeliver_loop(
    tg: TelegramClient, redis: aioredis.Redis | None, interval: float
) -> None:
    """Фонова петля: перевірка на старті + кожні `interval` секунд."""
    logger.info("APK autodeliver started (every %.0fs)", interval)
    while True:
        try:
            await check_once(tg, redis)
        except asyncio.CancelledError:
            logger.info("APK autodeliver stopped")
            raise
        except Exception as exc:  # noqa: BLE001 — не валимо петлю на разовому збої
            logger.warning("apk autodeliver check failed: %s", exc)
        await asyncio.sleep(interval)
