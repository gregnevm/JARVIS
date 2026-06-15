"""RequestContext — tenant/identity-контекст одного запиту (SAAS_DEEP_DIVE §2.2).

Спільний дім для multi-tenant ґрунту (AGENTS.md §5: «готуємо ґрунт під Стовп A
навіть зараз»). У self-hosted (`SAAS_MODE=false`) org синтетичний, а існуючий
Telegram `user_id` стає `legacy_uid` — Telegram-flow не змінюється (принцип S2:
self-hosted ніколи не ламається).

Framework-нейтральний (без FastAPI) — на відміну від `http_helpers`. Можна
імпортувати будь-де, включно з офлайн Edge.

Споживачі по фазах:
  * PR#1 (зараз): `resolve_context()` у gateway, `whoami`-відповідь.
  * PR#3: `redis_key(org_id, …)` — org-префіксовані Redis-ключі у tools-сторах.
  * PR#4: `to_headers()` — `X-JARVIS-*` propagation gateway→tools.
"""
from __future__ import annotations

from dataclasses import dataclass

# Синтетичний org для self-hosted backfill (SAAS_DEEP_DIVE §3.3, §13.1).
DEFAULT_ORG_ID = "00000000-0000-0000-0000-000000000001"

# RBAC-ролі та плани — канонічні набори (валідація на межах, не магічні рядки).
VALID_ROLES = frozenset({"owner", "admin", "member", "viewer"})
VALID_PLANS = frozenset({"free", "pro", "team", "studio", "enterprise"})


@dataclass(frozen=True)
class RequestContext:
    """Хто і в межах якого tenant робить запит. Immutable — передається по стеку як є."""

    org_id: str
    user_id: str
    role: str
    plan: str
    legacy_uid: int | None
    via: str
    request_id: str | None = None

    def to_headers(self) -> dict[str, str]:
        """Internal `X-JARVIS-*` headers для propagation gateway→tools→memory (PR#4).

        Рівно набір із SAAS_DEEP_DIVE §2.3 — `via` навмисно НЕ пропагується (це
        gateway-локальний спосіб входу для whoami, не tenant-ідентифікатор). Якщо
        downstream-сервісам знадобиться спосіб auth, додавати разом у spec §2.3 + код (D1)."""
        headers = {
            "X-JARVIS-Org-Id": self.org_id,
            "X-JARVIS-User-Id": self.user_id,
            "X-JARVIS-Role": self.role,
            "X-JARVIS-Plan": self.plan,
        }
        if self.legacy_uid is not None:
            headers["X-JARVIS-Legacy-Uid"] = str(self.legacy_uid)
        if self.request_id:
            headers["X-Request-ID"] = self.request_id
        return headers


def synthetic_context(
    legacy_uid: int,
    *,
    via: str = "telegram",
    role: str = "owner",
    plan: str = "studio",
    request_id: str | None = None,
) -> RequestContext:
    """Контекст для self-hosted: один synthetic org, internal user_id = Telegram id.

    Дефолт `owner`/`studio` — self-hosted власник має повний доступ (Edition matrix:
    self-hosted == Studio). Коли постане SaaS (PR#6), реальний `resolve_context`
    візьме org/role/plan із JWT/api_key замість синтетичних.
    """
    return RequestContext(
        org_id=DEFAULT_ORG_ID,
        user_id=str(legacy_uid),
        role=role,
        plan=plan,
        legacy_uid=int(legacy_uid),
        via=via,
        request_id=request_id,
    )


def redis_key(org_id: str | None, *parts: str) -> str:
    """Org-префіксований Redis-ключ: `jarvis:{org_id}:{parts...}` (SAAS_DEEP_DIVE §1.4).

    `org_id=None` (поточний self-hosted до PR#3 backfill) → `jarvis:{parts...}` —
    збігається з наявними ключами, тож міграція безшовна. Споживається у PR#3."""
    suffix = ":".join(str(p) for p in parts)
    if org_id:
        return f"jarvis:{org_id}:{suffix}"
    return f"jarvis:{suffix}"
