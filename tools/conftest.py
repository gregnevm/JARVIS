"""Кладе корінь сервісу tools у sys.path, щоб у тестах працював `import app.*`."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
