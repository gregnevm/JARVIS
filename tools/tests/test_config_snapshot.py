"""R4 «Тонкий шлюз»: env-імена й дефолти Settings — контракт сумісності .env (S2).

Снапшот знято ДО міграції на композитні блоки jarvis_core/settings (2026-07-06).
Падає — отже, зміна конфігу торкнулась env-імен або дефолтів: або поверни як було,
або свідомо онови снапшот (`python scripts/gen_env_docs.py`) і опиши міграцію в PR.
"""
from __future__ import annotations

import json
from pathlib import Path

from jarvis_core.settings import settings_inventory

from app.config import Settings


def test_env_names_and_defaults_match_snapshot():
    snap_path = Path(__file__).parent / "data" / "env_snapshot.json"
    snap = json.loads(snap_path.read_text(encoding="utf-8"))
    assert settings_inventory(Settings) == snap
