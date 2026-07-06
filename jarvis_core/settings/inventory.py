"""Інтроспекція Settings → інвентар env-змінних (R4 «Тонкий шлюз», D1 машиною).

Одна логіка на всіх: `scripts/gen_env_docs.py` (генерація ENV-інвентарю і
drift-гейт CI) і по-сервісні снапшот-тести (`test_config_snapshot.py` — контракт
«env-імена й дефолти незмінні») використовують саме цю функцію.
"""
from __future__ import annotations

import json
from typing import Any

from pydantic_settings import BaseSettings


def _env_name(field_name: str, field: Any, prefix: str) -> str:
    alias = getattr(field, "validation_alias", None)
    if isinstance(alias, str):
        return alias.upper()
    return (prefix + field_name).upper()


def settings_inventory(cls: type[BaseSettings]) -> dict[str, str]:
    """{ENV_NAME: дефолт-як-JSON} для всіх полів Settings.

    Властивості (@property) не входять — вони похідні, не env. Дефолт
    серіалізується в JSON (несеріалізовне — repr), щоб порівняння снапшотів
    було текстово-стабільним."""
    prefix = str(cls.model_config.get("env_prefix", "") or "")
    out: dict[str, str] = {}
    for name, field in cls.model_fields.items():
        default = field.get_default(call_default_factory=True)
        try:
            d = json.dumps(default, ensure_ascii=False, sort_keys=True)
        except TypeError:
            d = repr(default)
        out[_env_name(name, field, prefix)] = d
    return out
