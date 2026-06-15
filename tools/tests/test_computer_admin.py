"""C5 admin PowerShell gate + double confirm."""
import pytest

from app.computer_access import admin_powershell_denied_message
from app.computer_confirm import (
    ADMIN_CONFIRM_MARKER,
    audit_tier,
    execute_confirmed,
    save_pending,
)
from app.config import settings


@pytest.fixture
def admin_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "enable_computer_use", True)
    monkeypatch.setattr(settings, "computer_owner_user_ids", "1")
    monkeypatch.setattr(settings, "admin_user_ids", "1")
    monkeypatch.setattr(settings, "computer_allow_admin", True)
    monkeypatch.setattr(settings, "computer_require_confirm", True)


def test_admin_denied_not_admin(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "computer_allow_admin", True)
    monkeypatch.setattr(settings, "admin_user_ids", "99")
    msg = admin_powershell_denied_message(1)
    assert msg and "ADMIN" in msg


def test_audit_tier_admin():
    assert audit_tier("run_powershell", {"as_admin": True}) == "admin"


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self.store.get(key)

    async def setex(self, key: str, ttl: int, val: str) -> None:
        self.store[key] = val

    async def delete(self, key: str) -> None:
        self.store.pop(key, None)


async def test_admin_second_confirm(admin_env, monkeypatch: pytest.MonkeyPatch):
    import re

    fr = FakeRedis()
    monkeypatch.setattr("app.computer_confirm.get_redis", lambda: fr)
    monkeypatch.setattr("app.computer_rate_limit.get_redis", lambda: fr)

    code = await save_pending(1, "run_powershell", {"script": "Write-Output 1", "as_admin": True})
    result, _origin = await execute_confirmed(1, code)
    assert "COMPUTER_ADMIN_CONFIRM" in result
    m = re.search(r"COMPUTER_ADMIN_CONFIRM:([a-f0-9]+)", result)
    assert m
