"""Projection-lock: кожен read-шлях паспортів селектить усі колонки, які читає його мапер.

Клас дефекту, який лочимо: **SELECT дрейфнув від спільного мапера**. `DB._context_json`
(`app/db.py`) — єдине місце, що знає проєкцію паспорта (P7), і він fail-fast: читає
`r["sensitivity"]`, `r["ref"]`, `r["event_ts"]`. Якщо чийсь SELECT цих колонок не просить —
`asyncpg.Record` кидає `KeyError` → 500. Саме так `/context/ledger` (E3, журнал прозорості)
віддавав 500 на будь-якому непорожньому журналі, а gateway маскував це під
`error=memory_unreachable` — тобто симптом брехав про причину.

Тести чисті: без мережі й БД. Fake-pool парсить список колонок із самого SQL і віддає рядок
**рівно з цими** ключами, тому тест ловить дрейф, а не фіксує сьогоднішній текст запиту.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

import pytest
from app.db import DB

# ----------------------------------------------------------------- SQL-парсер

_IDENT_TAIL = re.compile(r"[A-Za-z_][A-Za-z_0-9]*$")


def _split_top_level(body: str) -> list[str]:
    """Розбити список виразів по комах, ігноруючи коми в дужках (COALESCE(source,'—'))."""
    parts: list[str] = []
    depth = 0
    cur: list[str] = []
    for ch in body:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    parts.append("".join(cur))
    return [p.strip() for p in parts if p.strip()]


def select_columns(sql: str) -> list[str]:
    """Імена колонок/аліасів, які віддає SELECT (`... AS score` → `score`)."""
    upper = sql.upper()
    body = sql[upper.index("SELECT") + len("SELECT") : upper.index(" FROM ")]
    out: list[str] = []
    for expr in _split_top_level(body):
        low = expr.lower()
        if " as " in low:
            out.append(expr[low.rindex(" as ") + 4 :].strip())
            continue
        m = _IDENT_TAIL.search(expr)
        out.append(m.group(0) if m else expr)
    return out


# ------------------------------------------------------------- значення колонок

_VALUES: dict[str, Any] = {
    "id": 7,
    "kind": "message",
    "source": "telegram",
    "summary": "коротко про подію",
    "tags": ["kind:message", "person:mom"],
    "sensitivity": "normal",
    "ref": "tg:42",
    "event_ts": datetime(2026, 7, 27, 10, 0, tzinfo=timezone.utc),
    "created_at": datetime(2026, 7, 27, 11, 0, tzinfo=timezone.utc),
    "score": 0.75,
    "c": 3,
    "payload": '{"raw": "текст"}',
}


class _StrictRow(dict[str, Any]):
    """Семантика `asyncpg.Record`: відсутня колонка → KeyError (як у продакшені)."""


class _RecorderRow(dict[str, Any]):
    """Ніколи не кидає: логує кожен прочитаний ключ, щоб асертити SELECT ⊇ reads."""

    def __init__(self, data: dict[str, Any], reads: set[str]) -> None:
        super().__init__(data)
        self._reads = reads

    def __getitem__(self, key: str) -> Any:
        self._reads.add(key)
        return self.get(key, _VALUES.get(key))


class _Query:
    def __init__(self, sql: str) -> None:
        self.sql = sql
        self.cols = select_columns(sql)
        self.reads: set[str] = set()

    @property
    def missing(self) -> set[str]:
        return self.reads - set(self.cols)


class _Con:
    def __init__(self, *, rows: int, strict: bool) -> None:
        self.rows = rows
        self.strict = strict
        self.queries: list[_Query] = []

    async def fetch(self, sql: str, *args: object) -> list[dict[str, Any]]:
        q = _Query(sql)
        self.queries.append(q)
        data = {c: _VALUES.get(c) for c in q.cols}
        if self.strict:
            return [_StrictRow(data) for _ in range(self.rows)]
        return [_RecorderRow(data, q.reads) for _ in range(self.rows)]

    async def fetchval(self, sql: str, *args: object) -> int:
        return self.rows


class _Acquire:
    def __init__(self, con: _Con) -> None:
        self._con = con

    async def __aenter__(self) -> _Con:
        return self._con

    async def __aexit__(self, *exc: object) -> None:
        return None


class _Pool:
    def __init__(self, con: _Con) -> None:
        self._con = con

    def acquire(self) -> _Acquire:
        return _Acquire(self._con)


def _db(*, rows: int = 1, strict: bool = True) -> tuple[DB, _Con]:
    con = _Con(rows=rows, strict=strict)
    db = DB.__new__(DB)  # без реального конекту
    db._pool = _Pool(con)  # type: ignore[assignment]
    return db, con


# ------------------------------------------------------- 1. репро самого дефекту


async def test_ledger_returns_full_passport_projection() -> None:
    """E3-журнал віддає ПОВНУ проєкцію паспорта (до фіксу тут був KeyError → 500)."""
    db, _ = _db(rows=1)

    out = await db.context_ledger(1, recent_limit=5)

    assert out["total"] == 1
    item = out["recent"][0]
    for field in ("id", "kind", "source", "summary", "tags", "sensitivity", "ref"):
        assert field in item, f"ledger не віддає {field} — проєкція розійшлася з /search і /recent"
    assert item["sensitivity"] == "normal"
    assert item["ref"] == "tg:42"
    assert item["event_ts"] == "2026-07-27T10:00:00+00:00"
    assert item["created_at"] == "2026-07-27T11:00:00+00:00"


async def test_ledger_empty_recent_is_empty_list() -> None:
    db, _ = _db(rows=0)

    out = await db.context_ledger(1, recent_limit=5)

    assert out == {"total": 0, "by_kind": {}, "by_source": {}, "recent": []}


# --------------------------------------------- 2. інваріант: SELECT ⊇ що читає мапер


async def _call_search(db: DB) -> object:
    return await db.search_context(1, [0.1, 0.2], 3)


async def _call_recent(db: DB) -> object:
    return await db.recent_context(1, 20)


async def _call_ledger(db: DB) -> object:
    return await db.context_ledger(1, recent_limit=5)


@pytest.mark.parametrize(
    "name,call",
    [
        ("search_context", _call_search),
        ("recent_context", _call_recent),
        ("context_ledger", _call_ledger),
    ],
)
async def test_read_path_selects_cover_mapper_fields(name: str, call: Any) -> None:
    """Будь-який read-шлях, що мапиться `_context_json`, мусить селектити всі його поля."""
    db, con = _db(rows=1, strict=False)

    await call(db)

    for q in con.queries:
        assert not q.missing, (
            f"{name}: SELECT не просить колонок {sorted(q.missing)}, які читає мапер "
            f"(це KeyError у рантаймі) — SQL: {q.sql}"
        )


async def test_mapper_reads_full_passport_shape() -> None:
    """Лок на сам мапер: якщо він почне читати нове поле, воно мусить бути в кожному SELECT."""
    db, con = _db(rows=1, strict=False)

    await db.recent_context(1, 5)

    assert con.queries[0].reads == {
        "id",
        "kind",
        "source",
        "summary",
        "tags",
        "sensitivity",
        "ref",
        "event_ts",
        "created_at",
    }


async def test_pending_context_has_its_own_projection() -> None:
    """`pending_context` мапиться інлайн (id/summary/tags/payload), тож поза параметризацією."""
    db, con = _db(rows=1, strict=True)

    out = await db.pending_context(1, 10)

    assert set(out[0]) == {"id", "summary", "tags", "payload"}
    assert out[0]["payload"] == {"raw": "текст"}  # JSON-рядок розпакований
    assert set(con.queries[0].cols) == {"id", "summary", "tags", "payload"}
