"""Кладе корінь сервісу gateway у sys.path, щоб у тестах працював `import app.*`."""
import sys
from pathlib import Path

import pytest

root = Path(__file__).resolve().parent
sys.path.insert(0, str(root.parent))
sys.path.insert(0, str(root))


@pytest.fixture(autouse=True)
def _disable_reply_keyboard_by_default(monkeypatch):
    """Reply Keyboard вмикають лише тести, що перевіряють його явно."""
    from app.config import settings

    monkeypatch.setattr(settings, "telegram_reply_keyboard", False)
