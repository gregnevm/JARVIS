"""Кладе корінь сервісу memory + корінь репо у sys.path: щоб у тестах
працював і `import app.*`, і `import jarvis_core.*` (memory/app залежить від
jarvis_core — як у gateway/tools conftest)."""
import sys
from pathlib import Path

root = Path(__file__).resolve().parent
sys.path.insert(0, str(root.parent))  # корінь репо → import jarvis_core
sys.path.insert(0, str(root))         # корінь сервісу → import app.*
