"""Кладе корінь hostagent у sys.path для тестів."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
