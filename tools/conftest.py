"""Кладе корінь сервісу tools у sys.path, щоб у тестах працював `import app.*`."""
import sys
from pathlib import Path

import pytest

root = Path(__file__).resolve().parent
sys.path.insert(0, str(root.parent))
sys.path.insert(0, str(root))


@pytest.fixture(autouse=True)
def _tmp_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """CI/локально немає writable /data — тести пишуть у tmp."""
    from app.config import settings

    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setattr(settings, "data_dir", str(data))
