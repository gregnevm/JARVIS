"""split_message — розбивка довгих повідомлень Telegram (ліміт 4096)."""
from app.telegram import TELEGRAM_MAX_LEN, split_message


def test_short_text_single_chunk():
    assert split_message("привіт") == ["привіт"]


def test_empty_text():
    assert split_message("") == [""]


def test_splits_on_line_boundaries():
    line = "x" * 1000 + "\n"
    text = line * 5
    chunks = split_message(text, limit=1500)
    assert all(len(c) <= 1500 for c in chunks)
    assert "".join(chunks) == text  # нічого не загубили


def test_hard_split_of_overlong_line():
    text = "y" * 5000  # один рядок, довший за ліміт → ріжемо жорстко
    chunks = split_message(text, limit=2000)
    assert all(len(c) <= 2000 for c in chunks)
    assert "".join(chunks) == text
    assert len(chunks) == 3


def test_default_limit_constant():
    assert TELEGRAM_MAX_LEN == 4096
