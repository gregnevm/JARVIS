"""Кладе корінь сервісу gateway у sys.path, щоб у тестах працював `import app.*`."""
import sys
from pathlib import Path

root = Path(__file__).resolve().parent
sys.path.insert(0, str(root.parent))
sys.path.insert(0, str(root))
