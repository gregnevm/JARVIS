"""Gateway: admin confirm markers."""
from app.bot.computer import parse_admin_confirm, parse_confirm


def test_parse_admin_confirm():
    text = "[[COMPUTER_ADMIN_CONFIRM:abc123]] PowerShell [admin]: test"
    c = parse_admin_confirm(text)
    assert c and c["code"] == "abc123"


def test_parse_normal_confirm():
    text = "[[COMPUTER_CONFIRM:def456]] CLI: git status"
    c = parse_confirm(text)
    assert c and c["code"] == "def456"
