"""is_allowed з динамічним store."""
import pytest

from app.access_store import AccessStore, UserRecord
from app.auth import bind_access_store, is_allowed


@pytest.mark.asyncio
async def test_dynamic_allowed(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("app.config.settings.allowed_user_ids", "1")
    store = AccessStore(tmp_path / "users.json")
    bind_access_store(store)
    await store.add_pending(UserRecord(2, None, "B", None))
    await store.approve(2, by_admin=1)

    assert is_allowed(1)
    assert is_allowed(2)
    assert not is_allowed(99)

    bind_access_store(None)
