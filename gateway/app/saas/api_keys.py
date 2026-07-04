"""Керовані API-ключі (AP-1): `sk-jarvis-…` з create/list/revoke + verify.

Безпека (S-принципи Стовпа A):
- **Ключ ніколи не зберігається** — лише `prefix` (для пошуку) + `sha256(key)` hash.
- **Показ один раз**: повний ключ повертається тільки при створенні.
- **Constant-time** порівняння хешу (`hmac.compare_digest`).
- Revoke — soft (прапор `revoked`), verify відхиляє відкликані.
- **Verify не пише запис ключа.** `last_used_at` живе в окремому side-ключі:
  read-modify-write повного запису на кожен запит гонявся з revoke() — verify,
  що встиг прочитати запис ДО відкликання, записував `revoked: false` назад,
  назавжди воскрешаючи відкликаний ключ (auth-bypass).

Сховище — Redis (ін'єктується для тестів). Self-hosted: один synthetic org;
per-org розшарування додасться зверху (SAAS tenant context) без зміни API.

Чому sha256, а не bcrypt: ключ — високоентропійний (256-bit random), тож
повільний bcrypt непотрібен; sha256 + constant-time — стандарт для API-токенів.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
import uuid
from typing import Any, Protocol

_PREFIX = "sk-jarvis-"
_PREFIX_LEN = len(_PREFIX) + 8  # 'sk-jarvis-' + 8 символів для пошуку
_REC_KEY = "jarvis:apikey:rec:{id}"
_PFX_KEY = "jarvis:apikey:pfx:{prefix}"
_USED_KEY = "jarvis:apikey:used:{id}"  # side-ключ: verify пише лише сюди, ніколи в rec
_INDEX = "jarvis:apikey:ids"
_DEFAULT_SCOPES = ("chat", "models", "embeddings", "jobs")
_VALID_SCOPES = frozenset({"chat", "embeddings", "jobs", "models"})


class _Redis(Protocol):
    async def set(self, key: str, value: str) -> Any: ...
    async def get(self, key: str) -> Any: ...
    async def delete(self, *keys: str) -> Any: ...
    async def sadd(self, key: str, *values: str) -> Any: ...
    async def srem(self, key: str, *values: str) -> Any: ...
    async def smembers(self, key: str) -> Any: ...


def _hash_key(full_key: str) -> str:
    return hashlib.sha256(full_key.encode("utf-8")).hexdigest()


def generate_key() -> tuple[str, str, str]:
    """Повертає (full_key, prefix, hash). full_key показуємо лише раз."""
    full = _PREFIX + secrets.token_urlsafe(32)
    return full, full[:_PREFIX_LEN], _hash_key(full)


def _normalize_scopes(scopes: list[str] | None) -> list[str]:
    if not scopes:
        return list(_DEFAULT_SCOPES)
    out = [s for s in scopes if s in _VALID_SCOPES]
    return out or list(_DEFAULT_SCOPES)


def _public(rec: dict[str, Any]) -> dict[str, Any]:
    """Метадані без секретів (без hash)."""
    return {
        "id": rec.get("id"),
        "name": rec.get("name", ""),
        "prefix": rec.get("prefix", ""),
        "scopes": rec.get("scopes", []),
        "created_at": rec.get("created_at"),
        "revoked": bool(rec.get("revoked", False)),
        "last_used_at": rec.get("last_used_at"),
    }


class ApiKeyStore:
    def __init__(self, redis: _Redis) -> None:
        self._r = redis

    async def create(self, name: str = "", scopes: list[str] | None = None) -> dict[str, Any]:
        """Створює ключ; повертає публічні метадані + `key` (повний, один раз)."""
        full, prefix, h = generate_key()
        key_id = uuid.uuid4().hex[:16]
        rec = {
            "id": key_id,
            "name": (name or "").strip()[:120],
            "prefix": prefix,
            "hash": h,
            "scopes": _normalize_scopes(scopes),
            "created_at": int(time.time()),
            "revoked": False,
            "last_used_at": None,  # legacy-поле: оновлення живуть у side-ключі _USED_KEY
        }
        await self._r.set(_REC_KEY.format(id=key_id), json.dumps(rec))
        await self._r.set(_PFX_KEY.format(prefix=prefix), key_id)
        await self._r.sadd(_INDEX, key_id)
        out = _public(rec)
        out["key"] = full  # показуємо ОДИН раз
        return out

    async def _load(self, key_id: str) -> dict[str, Any] | None:
        raw = await self._r.get(_REC_KEY.format(id=key_id))
        if not raw:
            return None
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else None
        except (ValueError, TypeError):
            return None

    async def _with_used(self, rec: dict[str, Any]) -> dict[str, Any]:
        """Публічні метадані + `last_used_at` із side-ключа (fallback — legacy-поле в rec)."""
        out = _public(rec)
        used = await self._r.get(_USED_KEY.format(id=rec.get("id")))
        if used is not None:
            try:
                out["last_used_at"] = int(used)
            except (ValueError, TypeError):
                pass  # зіпсований side-ключ → лишаємо legacy-значення з rec
        return out

    async def get(self, key_id: str) -> dict[str, Any] | None:
        rec = await self._load(key_id)
        return await self._with_used(rec) if rec else None

    async def list(self) -> list[dict[str, Any]]:
        ids = await self._r.smembers(_INDEX)
        out: list[dict[str, Any]] = []
        for kid in sorted(str(x) for x in (ids or [])):
            rec = await self._load(kid)
            if rec:
                out.append(await self._with_used(rec))
        out.sort(key=lambda r: r.get("created_at") or 0, reverse=True)
        return out

    async def revoke(self, key_id: str) -> bool:
        rec = await self._load(key_id)
        if rec is None:
            return False
        if not rec.get("revoked"):
            rec["revoked"] = True
            await self._r.set(_REC_KEY.format(id=key_id), json.dumps(rec))
        return True

    async def verify(self, full_key: str) -> dict[str, Any] | None:
        """Повертає публічний запис, якщо ключ валідний і не відкликаний; інакше None."""
        key = (full_key or "").strip()
        if not key.startswith(_PREFIX):
            return None
        prefix = key[:_PREFIX_LEN]
        key_id = await self._r.get(_PFX_KEY.format(prefix=prefix))
        if not key_id:
            return None
        rec = await self._load(str(key_id))
        if rec is None or rec.get("revoked"):
            return None
        if not hmac.compare_digest(str(rec.get("hash", "")), _hash_key(key)):
            return None
        # Read-path без запису запису (лише side-ключ): full-record SET тут гонявся
        # з revoke() і воскрешав відкликаний ключ (revoked:false поверх revoked:true).
        now = int(time.time())
        await self._r.set(_USED_KEY.format(id=rec["id"]), str(now))
        out = _public(rec)
        out["last_used_at"] = now
        return out
