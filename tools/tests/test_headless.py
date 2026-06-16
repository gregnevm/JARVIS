"""CA-6.4 headless apply policy gate (AM-4)."""
from __future__ import annotations

import pytest

from app import headless
from app.config import settings


async def test_no_confirm_false_is_passthrough(monkeypatch: pytest.MonkeyPatch) -> None:
    granted: list = []
    monkeypatch.setattr("app.computer_trust.grant_trust", lambda *a, **k: granted.append(a))
    out = await headless.authorize_headless_apply(1, no_confirm=False)
    assert out is None and granted == []  # інтерактив — gate не втручається


async def test_denied_when_policy_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "coding_headless_apply", False)
    out = await headless.authorize_headless_apply(1, no_confirm=True)
    assert out is not None and "політикою" in out


async def test_allowed_grants_trust_when_policy_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "coding_headless_apply", True)
    monkeypatch.setattr(settings, "coding_headless_trust_ttl", 600)
    calls: list[tuple] = []

    async def _grant(user_id, ttl=None, *, full=False):  # noqa: ANN001
        calls.append((user_id, ttl, full))

    monkeypatch.setattr("app.computer_trust.grant_trust", _grant)
    out = await headless.authorize_headless_apply(7, no_confirm=True)
    assert out is None  # дозволено
    assert calls and calls[0][0] == 7 and calls[0][1] == 600  # session-trust видано


async def test_rejects_invalid_user(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "coding_headless_apply", True)
    out = await headless.authorize_headless_apply(0, no_confirm=True)
    assert out is not None and "user_id" in out
