"""Кладе корінь hostagent і корінь репо у sys.path для тестів.

Корінь репо потрібен для `jarvis_core.*` (test_config_snapshot, R4) — так само,
як у twin/conftest.py. Локально це маскував CWD у sys.path (`python -m pytest`);
на CI (`pytest hostagent/tests`) без цього — ModuleNotFoundError."""
import sys
from pathlib import Path

root = Path(__file__).resolve().parent
sys.path.insert(0, str(root.parent))
sys.path.insert(0, str(root))
