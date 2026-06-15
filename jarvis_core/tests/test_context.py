"""RequestContext / tenant-ґрунт (PR#1, SAAS_DEEP_DIVE §2.2)."""
from dataclasses import FrozenInstanceError

import pytest

from jarvis_core.context import (
    DEFAULT_ORG_ID,
    VALID_PLANS,
    VALID_ROLES,
    RequestContext,
    redis_key,
    synthetic_context,
)


def test_synthetic_context_self_hosted_defaults():
    ctx = synthetic_context(12345)
    assert ctx.org_id == DEFAULT_ORG_ID
    assert ctx.user_id == "12345"  # internal user_id = str(Telegram id) у self-hosted
    assert ctx.legacy_uid == 12345
    assert ctx.role == "owner" and ctx.role in VALID_ROLES
    assert ctx.plan == "studio" and ctx.plan in VALID_PLANS
    assert ctx.via == "telegram"


def test_synthetic_context_overrides():
    ctx = synthetic_context(7, via="basic", request_id="req-1")
    assert ctx.via == "basic"
    assert ctx.request_id == "req-1"


def test_request_context_is_frozen():
    ctx = synthetic_context(1)
    with pytest.raises(FrozenInstanceError):
        ctx.org_id = "tampered"  # type: ignore[misc]


def test_to_headers_full():
    h = synthetic_context(99, via="telegram", request_id="rid").to_headers()
    assert h["X-JARVIS-Org-Id"] == DEFAULT_ORG_ID
    assert h["X-JARVIS-User-Id"] == "99"
    assert h["X-JARVIS-Role"] == "owner"
    assert h["X-JARVIS-Plan"] == "studio"
    assert h["X-JARVIS-Legacy-Uid"] == "99"
    assert h["X-Request-ID"] == "rid"
    # `via` навмисно НЕ header (SAAS §2.3 — рівно 6 headers, via серед них немає)
    assert "X-JARVIS-Via" not in h


def test_to_headers_omits_optional_when_absent():
    ctx = RequestContext(
        org_id="o", user_id="u", role="member", plan="free", legacy_uid=None, via="jwt"
    )
    h = ctx.to_headers()
    assert "X-JARVIS-Legacy-Uid" not in h
    assert "X-Request-ID" not in h


def test_redis_key_org_scoped():
    assert redis_key("org1", "bgjob", "abc") == "jarvis:org1:bgjob:abc"


def test_redis_key_without_org_matches_legacy():
    # None org → поточний self-hosted формат (безшовна міграція до PR#3 backfill)
    assert redis_key(None, "bgjob", "abc") == "jarvis:bgjob:abc"
