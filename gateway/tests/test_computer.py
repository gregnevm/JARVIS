"""Gateway Computer Use confirm parsing."""
from app.bot.computer import parse_confirm


def test_parse_confirm_marker():
    text = "[[COMPUTER_CONFIRM:abc123]] Set-Content file.txt: hello"
    got = parse_confirm(text)
    assert got == {"code": "abc123", "desc": "Set-Content file.txt: hello"}


def test_parse_confirm_missing():
    assert parse_confirm("plain text") is None
