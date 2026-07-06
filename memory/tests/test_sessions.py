"""list_sessions DB helper."""
import pytest
from app.db import DB


@pytest.mark.asyncio
async def test_list_sessions_empty(monkeypatch: pytest.MonkeyPatch):
    class FakeCon:
        async def fetch(self, *args, **kwargs):
            return []

    class FakeAcquire:
        async def __aenter__(self):
            return FakeCon()

        async def __aexit__(self, *a):
            return None

    class FakePool:
        def acquire(self):
            return FakeAcquire()

    db = DB("postgresql://x")
    db._pool = FakePool()  # type: ignore[assignment]
    out = await db.list_sessions(1, 5)
    assert out == []
