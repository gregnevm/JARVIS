"""clean_text — нормалізація тексту перед синтезом (XTTS/ffmpeg не тестуємо тут)."""
from app.synth import clean_text


def test_collapses_whitespace():
    assert clean_text("привіт    світ\n\nяк   справи", 800) == "привіт світ як справи"


def test_truncates_to_max():
    out = clean_text("а" * 1000, 100)
    assert len(out) == 100


def test_empty():
    assert clean_text("   \n  ", 800) == ""
    assert clean_text("", 800) == ""
