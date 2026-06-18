"""JsonlLog — re-export канонічної реалізації з jarvis_core (SSOT).

Історично twin тримав власну копію JsonlLog із додатковим ``read_from``. Тепер
єдине джерело правди — :mod:`jarvis_core.llm.jsonl_log`. Цей модуль лишено як
тонкий re-export, щоб не ламати наявні імпорти ``from app.session_log import
JsonlLog`` (DESIGN §6.1 SessionLogger).
"""
from __future__ import annotations

from jarvis_core.llm.jsonl_log import JsonlLog

__all__ = ["JsonlLog"]
