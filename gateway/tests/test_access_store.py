"""Динамічний whitelist: черга, approve, revoke."""
import pytest

from app.access_store import AccessStore, UserRecord


def _rec(uid: int) -> UserRecord:
    return UserRecord(user_id=uid, username="u", first_name="A", last_name=None)


@pytest.fixture
def store(tmp_path):
    return AccessStore(tmp_path / "users.json")


@pytest.mark.asyncio
async def test_pending_and_approve(store: AccessStore) -> None:
    assert await store.add_pending(_rec(10))
    assert not await store.add_pending(_rec(10))
    assert 10 in store.pending_ids

    ok, _, rec = await store.approve(10, by_admin=1)
    assert ok and rec is not None
    assert 10 in store.approved_ids
    assert 10 not in store.pending_ids

    await store.load()
    assert 10 in store.approved_ids


@pytest.mark.asyncio
async def test_deny_and_revoke(store: AccessStore) -> None:
    await store.add_pending(_rec(20))
    ok, _ = await store.deny(20)
    assert ok
    assert 20 not in store.pending_ids

    await store.approve(30, by_admin=1)
    ok, _ = await store.revoke(30)
    assert ok
    assert 30 not in store.approved_ids
