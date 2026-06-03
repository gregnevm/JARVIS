"""Парсинг ALLOWED_USER_IDS → set[int]."""
from app.config import Settings


def _with_ids(raw: str) -> Settings:
    s = Settings()
    s.allowed_user_ids = raw
    return s


def test_parses_comma_list():
    assert _with_ids("1,2,3").allowed_ids == {1, 2, 3}


def test_trims_spaces():
    assert _with_ids(" 10 , 20 ,30 ").allowed_ids == {10, 20, 30}


def test_empty_is_empty_set():
    assert _with_ids("").allowed_ids == set()


def test_skips_invalid_entries():
    assert _with_ids("5,abc,7,").allowed_ids == {5, 7}
